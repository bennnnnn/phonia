import { useMemo } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { useTranslation } from "react-i18next";

import { Icon } from "@/ui/icons/Icon";
import { useAuth } from "@/contexts/AuthContext";
import { useTodos } from "@/features/todos/context/TodosContext";
import type { HomeUrgentTodo } from "@/lib/api";
import { describeDueAt } from "@/features/todos/model/dueDate";
import { homeGreeting } from "@/features/home/model/homeWelcome";
import { filterHomeNudgeTodos } from "@/features/todos/model/homeReminderNudges";
import { firstOverdueHomeTodo, listHomeUrgentTodos } from "@/features/todos/model/homeUrgentTodos";
import { tap } from "@/lib/haptics";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { Theme, useTheme, withAlpha } from "@/lib/theme";
import { IconSize } from "@/ui/icons/sizes";
import { Type, Weight } from "@/lib/type";

function OverdueReminderRow({
  todo,
  onDismiss,
  styles: s,
  theme,
}: {
  todo: HomeUrgentTodo;
  onDismiss: (todoId: string) => void;
  styles: ReturnType<typeof makeStyles>;
  theme: Theme;
}) {
  const { t } = useTranslation();
  const router = useRouter();
  const due = describeDueAt(todo.due_at);

  return (
    <View style={s.urgentBlock}>
      <Text style={[s.sectionLabel, s.sectionLabelUrgent]} accessibilityRole="header">{t("chat.home.overdue")}</Text>
      <View style={s.urgentCardWrap}>
        <Pressable
          style={s.urgentCard}
          onPress={() => {
            tap();
            // Same target as a due-reminder push: Schedule with the row lit up.
            router.push({
              pathname: "/todos",
              params: { highlight: todo.id },
            });
          }}
          accessibilityRole="button"
          accessibilityLabel={todo.content}
        >
              <Icon name="alert-circle" size={IconSize.sm} color={theme.danger} />
          <View style={s.urgentMain}>
            <Text style={s.urgentTitle} numberOfLines={2}>
              {todo.content}
            </Text>
            {due ? (
              <Text style={s.urgentDue} numberOfLines={1}>
                {due.label}
              </Text>
            ) : null}
          </View>
          <Icon name="chevron-right" size={IconSize.xs} color={theme.danger} />
        </Pressable>
        <Pressable
          style={s.urgentDismiss}
          onPress={() => {
            tap();
            onDismiss(todo.id);
          }}
          accessibilityRole="button"
          accessibilityLabel={t("chat.home.dismiss_reminder")}
        >
          <View style={s.urgentDismissCircle}>
            <Icon name="close" size={IconSize.xxs} color={theme.textSecondary} />
          </View>
        </Pressable>
      </View>
    </View>
  );
}

type Props = {
  /** The composer holds a draft: the empty-chat canvas stays clear. The chat passes it. */
  composerActive: boolean;
};

export function HomeStarters({ composerActive }: Props) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const { user } = useAuth();
  const {
    todos,
    loading: todosLoading,
    remindersReady,
    homeNudgeDismissed,
    dismissReminderNudge,
    now,
  } = useTodos();

  const overdueTodo = useMemo(() => {
    // Wait until todos + nudge-state are in sync. Silent refreshes used to paint
    // red urgent cards for a frame before persisted dismissals caught up.
    if (todosLoading || !remindersReady) return undefined;
    // `now` moves on as reminders go out and fall due: one that does while the app is open
    // shows here, at the to-do's notify_at, as push and the phone's alert do.
    const urgent = listHomeUrgentTodos(todos, now);
    return firstOverdueHomeTodo(
      filterHomeNudgeTodos(urgent, { dismissed: homeNudgeDismissed }),
    );
  }, [
    todos,
    todosLoading,
    remindersReady,
    homeNudgeDismissed,
    now,
  ]);

  // Once typing begins, leave the empty-chat canvas clear and focused.
  if (composerActive) return null;

  return (
    <View style={s.wrap}>
      <Text style={s.greeting} accessibilityRole="header">{homeGreeting(user?.name)}</Text>

      {overdueTodo ? (
        <OverdueReminderRow
          todo={overdueTodo}
          onDismiss={(id) => void dismissReminderNudge(id)}
          styles={s}
          theme={theme}
        />
      ) : null}
    </View>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    wrap: { width: "100%", paddingHorizontal: Space.gutter, gap: Space.sm },
    greeting: {
      ...Type.display,
      color: t.text,
      textAlign: "center",
    },
    sectionLabel: {
      ...Type.overline,
      color: t.textTertiary,
      marginBottom: Space.xs,
    },
    sectionLabelUrgent: {
      color: t.danger,
    },
    urgentBlock: { width: "100%", gap: Space.xs, marginTop: Space.xxs },
    urgentCardWrap: {
      position: "relative",
    },
    urgentCard: {
      flexDirection: "row",
      alignItems: "center",
      gap: Space.sm,
      // An 8% danger tint, the card it was in amber: at 12% the due time was 4.35:1 in light
      // mode, and the theme's dangerLight well is 1.04:1 on the page, an outline, not a card.
      backgroundColor: withAlpha(t.danger, 0.08),
      borderRadius: Radius.lg,
      paddingHorizontal: Space.md,
      paddingVertical: Space.sm,
      paddingRight: Space.xl + Space.xxs,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: t.danger,
    },
    urgentDismiss: {
      position: "absolute",
      // 44×44 touch target; negative offsets keep the visible 24px circle at
      // its old center (top 6 + 12).
      top: -4,
      right: -4,
      width: Space.minTouch,
      height: Space.minTouch,
      alignItems: "center",
      justifyContent: "center",
    },
    urgentDismissCircle: {
      width: Space.lg,
      height: Space.lg,
      borderRadius: Radius.md,
      backgroundColor: t.surface,
      alignItems: "center",
      justifyContent: "center",
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: t.border,
    },
    urgentMain: { flex: 1, gap: 2 },
    urgentTitle: { ...Type.navTitle, color: t.text },
    urgentDue: { ...Type.caption, ...Weight.semibold, color: t.danger },
  });
}
