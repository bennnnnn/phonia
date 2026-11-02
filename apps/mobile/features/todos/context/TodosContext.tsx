import { createContext, useContext, useEffect, useMemo, useSyncExternalStore, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useAuthOptional } from "@/contexts/AuthContext";
import { useTodosList } from "@/features/todos/hooks/useTodosList";
import { useTodoReminderState } from "@/features/todos/hooks/useTodoReminderState";
import { useReminderClock } from "@/features/todos/hooks/useReminderClock";
import { getSessionGeneration } from "@/lib/auth";
import { onAppEvent } from "@/lib/appEvents";
import type { User } from "@/lib/api";
import { userTimeZone, userUses24HourClock } from "@/lib/datetime/format";
import { remotePushRegistered, subscribeRemotePushRegistered } from "@/features/notifications/model/pushRegistration";
import { syncTodoReminders } from "@/features/todos/model/todoReminders";

/** The profile fields a to-do's notify_at is worked out from (its time zone for quiet hours). */
const REMINDER_TIME_FIELDS: ReadonlySet<keyof User> = new Set<keyof User>([
  "reminder_lead_minutes", "quiet_hours_enabled", "quiet_hours_start_minute", "quiet_hours_end_minute", "timezone",
]);

type TodosContextValue = ReturnType<typeof useTodosList> & ReturnType<typeof useTodoReminderState> & {
  /** The time the to-do views read: it moves on as reminders fall due (useReminderClock). */
  now: Date;
};
const TodosContext = createContext<TodosContextValue | null>(null);

export function TodosProvider({ children }: { children: ReactNode }) {
  const auth = useAuthOptional();
  const list = useTodosList(auth?.token, auth?.user?.id);
  // Reminders come from the server only to a device whose push token it holds.
  const remotePush = useSyncExternalStore(subscribeRemotePushRegistered, remotePushRegistered);
  const remindersEnabled = auth?.user?.push_reminders_enabled ?? true;
  const now = useReminderClock(list.todos);
  const reminders = useTodoReminderState({ userId: auth?.user?.id, now,
    todos: list.todos, retainedOpenIds: list.retainedOpenIds, getTodos: list.getTodos, isCurrentSession: list.isCurrentSession });
  const session = getSessionGeneration();
  // The alerts are written in the app's language, the phone's 12/24-hour clock and its zone.
  // A change of one re-renders this provider (lib/i18n binds both events to useTranslation)
  // and the sync below writes each alert again.
  const { i18n } = useTranslation();
  const alertFormat = `${i18n.language}|${userUses24HourClock() ? "h23" : "h12"}|${userTimeZone() ?? ""}`;
  const {
    todos, loading, error, loaded, retainedOpenIds, olderCompleted, showOlderCompleted, setTodos, getTodos, refresh,
    isCurrentSession, readTodosAt,
  } = list;
  useEffect(() => {
    if (!loaded || !isCurrentSession()) return;
    // Each alert goes at the to-do's notify_at, which the server works out: nothing here
    // reads the lead time or quiet hours.
    void syncTodoReminders(todos, { remotePush, remindersEnabled, session })
      .catch(() => { if (isCurrentSession()) console.warn("[todos] device reminder sync failed"); });
  }, [todos, loaded, isCurrentSession, remotePush, remindersEnabled, session, alertFormat]);
  // The lead time, quiet hours or time zone saved: every reminder's instant moved on the server.
  useEffect(() => onAppEvent("userUpdated", ({ fields }) => {
    if (fields.some((field) => REMINDER_TIME_FIELDS.has(field))) void refresh({ silent: true, force: true, afterPending: true });
  }), [refresh]);
  const { unseenCount, showIndicator, seenReminderIds, homeNudgeDismissed, markSeen, markSeenIds,
    dismissReminderNudge } = reminders;
  const remindersReady = reminders.remindersReady && !loading;
  // Both hooks hand back a new object every render, and this provider renders on
  // every auth change. Rebuild the value only when a field does, so readers (the
  // chat screen among them) do not render along with it.
  const value = useMemo<TodosContextValue>(() => ({
    todos, loading, error, loaded, retainedOpenIds, olderCompleted, showOlderCompleted, setTodos, getTodos, refresh,
    isCurrentSession, readTodosAt, unseenCount, showIndicator, remindersReady, seenReminderIds, homeNudgeDismissed,
    markSeen, markSeenIds, dismissReminderNudge, now,
  }), [todos, loading, error, loaded, retainedOpenIds, olderCompleted, showOlderCompleted, setTodos, getTodos,
    refresh, isCurrentSession, readTodosAt, unseenCount, showIndicator, remindersReady, seenReminderIds,
    homeNudgeDismissed, markSeen, markSeenIds, dismissReminderNudge, now]);
  return <TodosContext.Provider value={value}>{children}</TodosContext.Provider>;
}

export function useTodos() {
  const ctx = useContext(TodosContext);
  if (!ctx) throw new Error("useTodos must be used within TodosProvider");
  return ctx;
}
export function useTodosOptional() { return useContext(TodosContext); }
