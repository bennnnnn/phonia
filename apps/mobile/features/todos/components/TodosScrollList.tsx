import { useMemo, type ReactElement } from "react";
import { RefreshControl, Text, View } from "react-native";
import { FlashList } from "@shopify/flash-list";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTranslation } from "react-i18next";

import { TodoRow } from "@/features/todos/components/TodoRow";
import { makeTodosStyles } from "@/features/todos/components/todosStyles";
import type { Todo } from "@/lib/api";
import { formatDate } from "@/lib/datetime/format";
import { clashClusters, groupBySameTime, type ClashCluster } from "@/features/todos/model/reminderOverlap";
import {
  todoListRowKey,
  type TodoListRow,
  type TodoSection,
} from "@/features/todos/model/todoListRows";
import { useTheme } from "@/lib/theme";
import { addFabClearance } from "@/ui/controls/addFabLayout";
import { Button } from "@/ui/controls/Button";

type Props = {
  rows: TodoListRow[];
  /** The to-do clock (useReminderClock): a time it has passed reads as overdue. */
  now: Date;
  showEmpty: boolean;
  error: boolean;
  listHeader: ReactElement;
  refreshing?: boolean;
  onRefresh?: () => void;
  highlight?: string;
  busyTodoIds: ReadonlySet<string>;
  onToggle: (todo: Todo) => void;
  onOpen: (todo: Todo) => void;
  onDeleteItem: (todo: Todo) => void;
  selecting?: boolean;
  selectedIds?: ReadonlySet<string>;
  onSelect?: (todo: Todo) => void;
  /** Completed to-dos from before the last 30 days were left out: read them. */
  onShowOlder?: () => void;
};

/**
 * One list cell: a day's heading, or one card of to-dos due at the same time. A
 * cell per card, not per day, so FlashList mounts only the cards on screen: a day
 * of 300 to-dos used to be one cell that mounted all 300 rows.
 */
type TodoListItem =
  | { kind: "heading"; key: string; section: TodoSection; dayKey?: string }
  | { kind: "card"; key: string; section: TodoSection; todos: Todo[] };

/** The heading of a later day: its local noon (`localDateKey` read the day in the user's zone). */
function futureDayLabel(dayKey: string): string {
  const date = new Date(`${dayKey}T12:00:00`);
  if (!Number.isFinite(date.getTime())) return dayKey;
  return formatDate(date, "longWeekdayDate");
}

function itemsFromRows(rows: TodoListRow[]): TodoListItem[] {
  const items: TodoListItem[] = [];
  let heading: Extract<TodoListRow, { kind: "heading" }> | null = null;
  let todos: Todo[] = [];
  const flush = () => {
    if (heading && todos.length) {
      const { section, dayKey } = heading;
      items.push({ kind: "heading", key: todoListRowKey(heading), section, dayKey });
      for (const group of groupBySameTime(todos)) {
        items.push({ kind: "card", key: todoListRowKey({ kind: "todo", todo: group[0]! }), section, todos: group });
      }
    }
    todos = [];
  };
  for (const row of rows) {
    if (row.kind === "heading") {
      flush();
      heading = row;
      continue;
    }
    if (heading) todos.push(row.todo);
  }
  flush();
  return items;
}

function joinNames(names: string[], locale: string): string {
  try {
    return new Intl.ListFormat(locale, { type: "conjunction", style: "long" }).format(names);
  } catch {
    return names.join(", ");
  }
}

function clashLines(clusters: ClashCluster[], locale: string, t: (key: string, options?: Record<string, string>) => string): string[] {
  return clusters.map((cluster) => {
    const time = formatDate(new Date(cluster.at), "time");
    if (cluster.names.length === 2) {
      return t("todos.day_clash_pair", {
        first: cluster.names[0] ?? "",
        second: cluster.names[1] ?? "",
        time,
      });
    }
    return t("todos.day_clash_many", { names: joinNames(cluster.names, locale), time });
  });
}

/** Virtualized To-do list: each day's heading, then its cards of same-time to-dos. */
export function TodosScrollList({
  rows,
  now,
  showEmpty,
  error,
  listHeader,
  refreshing = false,
  onRefresh,
  highlight,
  busyTodoIds,
  onToggle,
  onOpen,
  onDeleteItem,
  selecting = false,
  selectedIds,
  onSelect,
  onShowOlder,
}: Props) {
  const { t, i18n } = useTranslation();
  const C = useTheme();
  const s = useMemo(() => makeTodosStyles(C), [C]);
  const items = useMemo(() => itemsFromRows(rows), [rows]);
  // The last row scrolls clear of the bottom-right add FAB.
  const insets = useSafeAreaInsets();

  return (
    <FlashList
      data={items}
      keyExtractor={(item) => item.key}
      getItemType={(item) => item.kind}
      style={s.list}
      contentContainerStyle={[
        showEmpty && !error ? s.listEmpty : undefined,
        s.listContent,
        { paddingBottom: addFabClearance(insets.bottom) },
      ]}
      extraData={selecting ? [...(selectedIds ?? [])].join(",") : highlight ?? "browse"}
      keyboardShouldPersistTaps="handled"
      refreshControl={
        onRefresh ? (
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={C.primary} />
        ) : undefined
      }
      ListHeaderComponent={listHeader}
      ListFooterComponent={
        onShowOlder ? (
          <View style={s.olderFooter}>
            <Button variant="ghost" size="sm" title={t("todos.show_older_completed")} onPress={onShowOlder} />
          </View>
        ) : null
      }
      ListEmptyComponent={
        !showEmpty && !error ? (
          <Text style={s.filterEmpty}>{t("todos.filter_empty")}</Text>
        ) : null
      }
      renderItem={({ item, index }) => {
        if (item.kind === "heading") {
          const title = item.section === "date" && item.dayKey
            ? futureDayLabel(item.dayKey)
            : t(`todos.group_${item.section}`);
          const prominent = item.section === "today" || item.section === "overdue";
          return (
            <View style={[s.sectionHeader, index === 0 && s.sectionHeaderFirst]}>
              <Text style={prominent ? s.dayHeading : s.sectionHeading}>{title}</Text>
            </View>
          );
        }
        const lines = clashLines(clashClusters(item.todos), i18n.language, t);
        return (
          <View>
            <View style={s.daySheet}>
              {lines.length ? (
                <View style={s.dayClash}>
                  {lines.map((line) => (
                    <Text key={line} style={s.dayClashText}>
                      {line}
                    </Text>
                  ))}
                </View>
              ) : null}
              {item.todos.map((todo, todoIndex) => (
                <View key={todoListRowKey({ kind: "todo", todo })}>
                  {todoIndex > 0 ? <View style={s.sheetRule} /> : null}
                  <TodoRow
                    todo={todo}
                    section={item.section}
                    pastDue={todo.due_at != null && Date.parse(todo.due_at) < now.getTime()}
                    highlighted={highlight === todo.id}
                    busy={busyTodoIds.has(todo.id)}
                    onToggle={onToggle}
                    onOpen={onOpen}
                    onDelete={onDeleteItem}
                    selecting={selecting}
                    selected={selectedIds?.has(todo.id) ?? false}
                    onSelect={onSelect}
                  />
                </View>
              ))}
            </View>
          </View>
        );
      }}
    />
  );
}
