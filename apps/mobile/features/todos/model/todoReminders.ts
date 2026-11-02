import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

import type { Todo } from "@/lib/api";
import { getSessionGeneration } from "@/lib/auth";
import { formatDate } from "@/lib/datetime/format";
import i18n from "@/lib/i18n";
import { shouldSyncLocalTodoReminders } from "@/features/todos/model/todoReminderPush";
import { AndroidNotificationChannel, notificationSound } from "@/features/notifications/model/notificationChannels";
import { ensureReminderChannel } from "@/features/notifications/model/pushNotifications";

export { ensureNotificationPermission } from "@/features/notifications/model/pushNotifications";
const TODO_PREFIX = "todo-due-";
const ANDROID_CHANNEL = AndroidNotificationChannel.reminders;
type ReminderOptions = {
  /** The server holds this device's push token and sends its reminders. */
  remotePush?: boolean | null;
  /** Settings → Notifications → Reminders; off means no reminder alerts from anywhere. */
  remindersEnabled?: boolean;
  session?: number;
};
type IsCurrent = () => boolean;
let revision = 0;
let pending: Promise<void> = Promise.resolve();
const scheduledVersions = new Map<string, string>();

/** Native writes finish in order; newer full-list intent invalidates older work. */
function enqueue(session: number, operation: (current: IsCurrent) => Promise<unknown>, supersede = true): Promise<void> {
  if (session !== getSessionGeneration()) return Promise.resolve();
  const request = supersede ? ++revision : revision;
  const current = () => session === getSessionGeneration() && request === revision;
  const task = pending.then(async () => { if (current()) await operation(current); });
  pending = task.then(() => {}, () => {});
  return task;
}

export function todoNotificationId(todoId: string): string { return `${TODO_PREFIX}${todoId}`; }

type Pending = Notifications.NotificationRequest[];

/**
 * Cancels the pending notifications `matches` picks and resolves the ones left. A sync
 * passes that list on (`listed`) instead of asking the OS again for each to-do: a first
 * sync of 500 to-dos listed every pending notification 501 times.
 */
async function cancelMatching(matches: (id: string) => boolean, current: IsCurrent, listed?: Pending): Promise<Pending> {
  const scheduled = listed ?? await Notifications.getAllScheduledNotificationsAsync();
  if (!current()) return scheduled;
  for (const id of scheduledVersions.keys()) if (matches(id)) scheduledVersions.delete(id);
  // Wait for every started native cancellation before another job may schedule.
  const results = await Promise.allSettled(scheduled.filter((item) => matches(item.identifier))
    .map((item) => Notifications.cancelScheduledNotificationAsync(item.identifier)));
  const failure = results.find((result) => result.status === "rejected");
  if (failure?.status === "rejected") throw failure.reason;
  return scheduled.filter((item) => !matches(item.identifier));
}
function matchesTodo(todoId: string): (id: string) => boolean {
  const id = todoNotificationId(todoId);
  return (candidate) => candidate === id || candidate.startsWith(`${id}-`);
}
export function cancelTodoReminder(todoId: string): Promise<void> {
  return enqueue(getSessionGeneration(), (current) => cancelMatching(matchesTodo(todoId), current), false);
}

/** The instant the server says this to-do's reminder goes out, while it is still to come. */
function upcomingNotifyAt(todo: Todo, now = Date.now()): Date | null {
  if (todo.checked || todo.id.startsWith("local-") || !todo.due_at || !todo.notify_at) return null;
  const at = new Date(todo.notify_at);
  return at.getTime() > now ? at : null;
}

/**
 * Schedules one to-do's alert at its `notify_at`, as the server worked it out (its lead time,
 * after quiet hours: the moment push would send it); `listed` is what is pending, and the
 * result what is left of it.
 */
async function schedule(todo: Todo, current: IsCurrent, listed: Pending): Promise<Pending> {
  const notifyAt = upcomingNotifyAt(todo);
  if (!current() || !notifyAt || !todo.due_at) return listed;
  const due = new Date(todo.due_at);
  const id = todoNotificationId(todo.id);
  const title = i18n.t("notifications.todo_reminder_title");
  const body = i18n.t("notifications.todo_reminder_body", { content: todo.content, time: formatDate(due, "time") });
  // What the alert says and when: its text is in the app's language, the phone's 12/24-hour
  // clock and zone, so a change of one writes it again. Repeated list refreshes must not
  // schedule the same alert again.
  const version = JSON.stringify([title, body, todo.topic, todo.notify_at]);
  if (scheduledVersions.get(id) === version) return listed;
  const left = await cancelMatching(matchesTodo(todo.id), current, listed);
  if (!current()) return left;
  await Notifications.scheduleNotificationAsync({
    identifier: id,
    content: {
      title,
      body,
      data: { type: "todo_due", screen: "todos", todo_id: todo.id, topic: todo.topic },
      sound: notificationSound(),
      ...(Platform.OS === "android" ? { channelId: ANDROID_CHANNEL } : {}),
    },
    trigger: { type: Notifications.SchedulableTriggerInputTypes.DATE, date: notifyAt },
  });
  if (current()) scheduledVersions.set(id, version);
  return left;
}

async function permitted(current: IsCurrent): Promise<boolean> {
  await ensureReminderChannel();
  if (!current()) return false;
  // Permission prompts belong to explicit user actions, never a background refresh.
  const permission = await Notifications.getPermissionsAsync();
  return current() && permission.status === "granted";
}

/**
 * iOS keeps 64 pending local notifications and drops the rest without a word, so
 * past that the later reminders never fired. The soonest are scheduled; the list is
 * read again each time the app comes to the front, and the next ones take the slots
 * the fired ones left.
 */
export const MAX_SCHEDULED_REMINDERS = 60;

function soonestReminders(todos: Todo[]): Todo[] {
  return todos
    .map((todo) => ({ todo, at: upcomingNotifyAt(todo)?.getTime() }))
    .filter((item): item is { todo: Todo; at: number } => item.at !== undefined)
    .sort((a, b) => a.at - b.at)
    .slice(0, MAX_SCHEDULED_REMINDERS)
    .map((item) => item.todo);
}

export function syncTodoReminders(todos: Todo[], options?: ReminderOptions): Promise<void> {
  return enqueue(options?.session ?? getSessionGeneration(), async (current) => {
    if (options?.remindersEnabled === false || !shouldSyncLocalTodoReminders(options?.remotePush)) {
      await cancelMatching((id) => id.startsWith(TODO_PREFIX), current);
      return;
    }
    const upcoming = soonestReminders(todos);
    const keepIds = new Set(upcoming.map((todo) => todoNotificationId(todo.id)));
    let listed = await cancelMatching((id) => id.startsWith(TODO_PREFIX) && !keepIds.has(id), current);
    if (!upcoming.length || !current() || !await permitted(current)) return;
    for (const todo of upcoming) {
      if (!current()) return;
      listed = await schedule(todo, current, listed);
    }
  });
}

/** Invalidates queued schedules immediately, then cancels after any native write settles. */
export function cancelAllTodoReminders(): Promise<void> {
  return enqueue(getSessionGeneration(), (current) => cancelMatching((id) => id.startsWith(TODO_PREFIX), current));
}
