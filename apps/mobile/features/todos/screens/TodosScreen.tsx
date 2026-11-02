import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactElement } from "react";
import { Redirect, useLocalSearchParams, useNavigation } from "expo-router";
import { Keyboard, Pressable, Text, View } from "react-native";
import { useTranslation } from "react-i18next";

import { AddFab } from "@/ui/controls/AddFab";
import { SkeletonList } from "@/ui/feedback/SkeletonLoader";
import { HeaderButton } from "@/ui/controls/HeaderButton";
import { plainHeaderItems, StackBackButton } from "@/ui/controls/StackBackButton";
import { TodosListHeader } from "@/features/todos/components/TodosListHeader";
import { TodoDetailMenu } from "@/features/todos/components/TodoDetailMenu";
import { TodoEditorSheet, type TodoEditorHandle } from "@/features/todos/components/TodoEditorSheet";
import { TodoSelectionBar } from "@/features/todos/components/TodoSelectionBar";
import { TodosScrollList } from "@/features/todos/components/TodosScrollList";
import { TodosViewMenu } from "@/features/todos/components/TodosViewMenu";
import { makeTodosStyles } from "@/features/todos/components/todosStyles";
import { useTodosActions } from "@/features/todos/hooks/useTodosActions";
import { useAccountViewOwner } from "@/hooks/useAccountViewOwner";
import { useReconnectRefresh } from "@/hooks/useReconnectRefresh";
import { useActionFeedbackOptional } from "@/contexts/actionFeedbackCore";
import { useAuth } from "@/contexts/AuthContext";
import { useTodos } from "@/features/todos/context/TodosContext";
import { buildTodoListRows } from "@/features/todos/model/todoListRows";
import { todosForView, type TodoView, viewForNewTodo } from "@/features/todos/model/todoListFilter";
import { useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";
import { confirmDialog } from "@/ui/overlay/dialogs";

export default function TodosScreen() {
  const view = useAccountViewOwner();
  return <TodosContent key={view.key} isCurrentView={view.isCurrent} />;
}

function TodosContent({ isCurrentView }: { isCurrentView: () => boolean }) {
  const { token, user, updateUser } = useAuth();
  const { t } = useTranslation();
  const feedback = useActionFeedbackOptional();
  const C = useTheme();
  const s = useMemo(() => makeTodosStyles(C), [C]);
  const navigation = useNavigation();
  const { highlight } = useLocalSearchParams<{
    highlight?: string;
  }>();
  const {
    todos,
    setTodos,
    loading,
    error,
    refresh,
    markSeenIds,
    getTodos,
    isCurrentSession,
    readTodosAt,
    olderCompleted,
    showOlderCompleted,
    now,
  } = useTodos();
  const [editorOpen, setEditorOpen] = useState(false);
  const [pullRefreshing, setPullRefreshing] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [detailMenu, setDetailMenu] = useState(false);
  const editRef = useRef<TodoEditorHandle>(null);
  /** Header ⋮ — both the list menu and the detail menu drop from it. */
  const menuAnchorRef = useRef<View>(null);
  const [view, setView] = useState<TodoView>("today");
  const [selecting, setSelecting] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const refreshingRef = useRef(false);

  const showTodosEmptyHero = todos.length === 0;

  const actions = useTodosActions({
    token,
    userId: user?.id,
    todos,
    getTodos,
    isCurrentSession,
    isCurrentView,
    markSeenIds,
    setTodos,
    refresh,
  });
  const leaveSelection = useCallback(() => {
    setSelecting(false);
    setSelectedIds([]);
  }, []);

  const openedHighlight = useRef<string | null>(null);
  const highlightId = Array.isArray(highlight) ? highlight[0] : highlight;
  useEffect(() => {
    if (!highlightId || openedHighlight.current === highlightId || !isCurrentView()) return;
    const todo = todos.find((item) => item.id === highlightId);
    if (!todo) return;
    openedHighlight.current = highlightId;
    setMenuOpen(false);
    setDetailMenu(false);
    setEditorOpen(false);
    actions.openTodoEditor(todo);
  }, [highlightId, todos, actions, isCurrentView]);

  const editingId = actions.editingTodo?.id ?? null;
  const closeEditor = actions.closeTodoEditor;
  useEffect(() => {
    if (!editingId) return;
    if (!todos.some((row) => row.id === editingId)) {
      setDetailMenu(false);
      closeEditor();
    }
  }, [editingId, todos, closeEditor]);

  const detailOpen = editingId != null;
  const leaveDetail = useCallback(() => {
    setDetailMenu(false);
    editRef.current?.leave();
  }, []);
  // The native header keeps the first button it mounted. Route the press
  // through a ref so that button still opens this page's menu.
  const headerRightAction = useRef<() => void>(() => {});
  const headerBackAction = useRef<() => void>(() => {});
  headerBackAction.current = leaveDetail;
  useEffect(() => {
    if (!detailOpen) return;
    return navigation.addListener("beforeRemove", (event) => {
      const type = event.data.action.type;
      if (type !== "GO_BACK" && type !== "POP") return;
      event.preventDefault();
      leaveDetail();
    });
  }, [navigation, detailOpen, leaveDetail]);
  headerRightAction.current = () => {
    Keyboard.dismiss();
    if (detailOpen && editingId) {
      setDetailMenu((open) => !open);
      return;
    }
    if (selecting) {
      leaveSelection();
      return;
    }
    setMenuOpen((open) => !open);
  };

  useLayoutEffect(() => {
    const headerLeftElement = detailOpen ? (
      <HeaderButton
        icon="arrow-left"
        variant="plain"
        accessibilityLabel={t("common.back")}
        onPress={() => headerBackAction.current()}
      />
    ) : (
      <StackBackButton />
    );
    let headerRightElement: ReactElement | null = null;
    if (!(detailOpen && !editingId)) {
      headerRightElement = !detailOpen && selecting ? (
        <Pressable
          onPress={() => headerRightAction.current()}
          accessibilityRole="button"
          accessibilityLabel={t("todos.selection_done")}
          hitSlop={12}
        >
          <Text style={[Type.body, { color: C.primary }]}>{t("todos.selection_done")}</Text>
        </Pressable>
      ) : (
        <HeaderButton
          ref={menuAnchorRef}
          icon="more-horizontal"
          variant="plain"
          accessibilityLabel={detailOpen ? t("todos.detail_menu") : t("todos.menu")}
          onPress={() => headerRightAction.current()}
        />
      );
    }
    navigation.setOptions({
      title: t("drawer.reminders"),
      headerStyle: { backgroundColor: detailOpen ? C.surface : C.bg },
      headerShadowVisible: false,
      headerLeft: () => headerLeftElement,
      unstable_headerLeftItems: () => plainHeaderItems(headerLeftElement),
      headerRight: () => headerRightElement,
      unstable_headerRightItems: () => plainHeaderItems(headerRightElement),
    });
  }, [navigation, t, selecting, detailOpen, editingId, C.primary, C.surface, C.bg]);

  const onPullRefresh = useCallback(async () => {
    if (!isCurrentView() || refreshingRef.current) return;
    refreshingRef.current = true;
    setPullRefreshing(true);
    try {
      await refresh({ silent: true, force: true });
    }
    finally {
      refreshingRef.current = false;
      if (isCurrentView()) setPullRefreshing(false);
    }
  }, [refresh, isCurrentView]);

  const retry = useCallback(() => {
    if (isCurrentView()) void refresh({ force: true });
  }, [refresh, isCurrentView]);
  // The API back after an outage: the list read again, unless a read landed since the connection
  // was lost, or it is within its stale window.
  useReconnectRefresh(() => void refresh(), { onScreen: isCurrentView, readAt: readTodosAt });

  const listHeader = useMemo(
    () => (
      <TodosListHeader
        error={Boolean(error)}
        onRetry={retry}
        showEmpty={showTodosEmptyHero}
      />
    ),
    [error, retry, showTodosEmptyHero],
  );

  // `now` moves on as reminders fall due, so a to-do moves to Overdue while the list is open.
  const visibleTodos = useMemo(() => todosForView(todos, view, now), [todos, view, now]);
  const rows = useMemo(() => buildTodoListRows(visibleTodos, now), [visibleTodos, now]);
  const selected = useMemo(() => new Set(selectedIds), [selectedIds]);
  // Every row takes these: a new function each render redrew every row on any change (a toggle).
  const openTodoEditor = actions.openTodoEditor;
  const openTodo = useCallback((todo: Parameters<typeof openTodoEditor>[0]) => {
    if (!isCurrentView()) return;
    setMenuOpen(false);
    setDetailMenu(false);
    setEditorOpen(false);
    openTodoEditor(todo);
  }, [isCurrentView, openTodoEditor]);
  const toggleSelected = useCallback((todo: { id: string }) => {
    setSelectedIds((current) =>
      current.includes(todo.id) ? current.filter((id) => id !== todo.id) : [...current, todo.id],
    );
  }, []);
  if (!token) return <Redirect href="/login" />;

  if (loading && todos.length === 0) {
    return <SkeletonList />;
  }

  const openEditor = () => {
    if (!isCurrentView()) return;
    setMenuOpen(false);
    setDetailMenu(false);
    actions.closeTodoEditor();
    setEditorOpen(true);
  };

  const deleteSelected = () => {
    if (selectedIds.length === 0) return;
    void confirmDialog({
      title: t("todos.delete_selected", { count: selectedIds.length }),
      cancelLabel: t("common.cancel"),
      confirmLabel: t("common.delete"),
      destructive: true,
    }).then((ok) => {
      if (!ok) return;
      void actions.handleDeleteMany(selectedIds);
      leaveSelection();
    });
  };

  return (
    // The root layout already provides GestureHandlerRootView — a nested one
    // here steals gesture routing (see lessons: drawer pan vs mic press).
    <View style={s.root}>
      {detailOpen ? null : (
      <TodosScrollList
        rows={rows}
        now={now}
        showEmpty={showTodosEmptyHero}
        error={Boolean(error)}
        listHeader={listHeader}
        refreshing={pullRefreshing}
        onRefresh={onPullRefresh}
        highlight={highlight}
        busyTodoIds={actions.busyTodoIds}
        onToggle={actions.handleToggle}
        onOpen={openTodo}
        onDeleteItem={actions.handleDeleteItem}
        selecting={selecting}
        selectedIds={selected}
        onSelect={toggleSelected}
        onShowOlder={olderCompleted && !selecting && (view === "all" || view === "completed")
          ? () => void showOlderCompleted()
          : undefined}
      />
      )}

      <TodosViewMenu
        visible={menuOpen && !selecting && !detailOpen}
        anchorRef={menuAnchorRef}
        view={view}
        onView={(next) => {
          setView(next);
          leaveSelection();
        }}
        onSelect={() => {
          setSelectedIds([]);
          setSelecting(true);
        }}
        onClose={() => setMenuOpen(false)}
      />

      {selecting ? (
        <TodoSelectionBar
          count={selectedIds.length}
          onComplete={() => {
            void actions.handleMarkDone(selectedIds);
            leaveSelection();
          }}
          onDelete={deleteSelected}
        />
      ) : detailOpen ? null : (
        <AddFab
          wave
          onPress={openEditor}
          accessibilityLabel={t("todos.add_todo")}
        />
      )}

      <TodoEditorSheet
        visible={editorOpen}
        saving={actions.savingTodo}
        todos={todos}
        onClose={() => { if (isCurrentView()) setEditorOpen(false); }}
        onSave={(content, dueDate, recurrence, topic) =>
          void actions.handleCreateTodo(
            content,
            dueDate,
            () => {
              if (!isCurrentView()) return;
              setEditorOpen(false);
              // A to-do the current view would hide: show the view that lists it.
              const shown = viewForNewTodo(view, dueDate);
              if (shown === view) return;
              setView(shown);
              feedback?.info(t("todos.added_shown_open"));
            },
            recurrence,
            topic,
          )
        }
      />

      <TodoEditorSheet
        page
        ref={editRef}
        visible={actions.editingTodo != null}
        editTodo={actions.editingTodo}
        savedTodo={todos.find((todo) => todo.id === actions.editingTodo?.id) ?? null}
        readOnly={todos.find((todo) => todo.id === actions.editingTodo?.id)?.checked ?? actions.editingTodo?.checked ?? false}
        saving={
          actions.editingTodo
            ? actions.busyTodoIds.has(actions.editingTodo.id)
            : false
        }
        todos={todos}
        leadMinutes={user?.reminder_lead_minutes}
        onChangeLead={(minutes) => updateUser({ reminder_lead_minutes: minutes })}
        onClose={actions.closeTodoEditor}
        onSave={(content, dueDate, recurrence, topic) => {
          const target = actions.editingTodo;
          if (target) void actions.handleUpdateTodo(target, content, dueDate, recurrence, topic);
        }}
      />

      <TodoDetailMenu
        visible={detailMenu && actions.editingTodo != null}
        anchorRef={menuAnchorRef}
        checked={todos.find((todo) => todo.id === actions.editingTodo?.id)?.checked ?? actions.editingTodo?.checked ?? false}
        onMarkDone={() => {
          const current = todos.find((todo) => todo.id === actions.editingTodo?.id) ?? actions.editingTodo;
          setDetailMenu(false);
          if (!current) return;
          const draft = editRef.current?.pending() ?? null;
          void (async () => {
            if (draft) {
              const saved = await actions.handleUpdateTodo(
                current,
                draft.content,
                draft.dueDate,
                draft.recurrence,
                draft.topic,
                false,
              );
              if (!saved) return;
            }
            await actions.handleToggle(current);
          })();
        }}
        onDelete={() => {
          const current = todos.find((todo) => todo.id === actions.editingTodo?.id) ?? actions.editingTodo;
          setDetailMenu(false);
          if (current) actions.handleDeleteItem(current);
        }}
        onClose={() => setDetailMenu(false)}
      />
    </View>
  );
}

/** Its route's error view: a crash here leaves the rest of the app working. */
export { ScreenErrorBoundary as ErrorBoundary } from "@/components/ScreenErrorBoundary";
