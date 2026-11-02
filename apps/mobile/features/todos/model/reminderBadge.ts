import type { Todo } from "@/lib/api";

/**
 * When an open dated to-do's reminder goes out, as epoch ms: its `notify_at`, which the
 * server works out (the lead time, after quiet hours) and push and the phone's own alert
 * fire at. The badge, Home and the to-do clock read this one time; the phone keeps no copy
 * of the rule. A to-do the server gave none (more than 48 hours past due, or a due time
 * whose save has not answered yet) counts from its due time, once it is overdue. Null for
 * a done or undated to-do.
 */
export function reminderGoesOutAt(todo: Todo): number | null {
  if (todo.checked || !todo.due_at) return null;
  const at = Date.parse(todo.notify_at ?? todo.due_at);
  return Number.isNaN(at) ? null : at;
}

/** Open reminders that have gone out by `now`; an overdue one stays until it is done. */
export function listUrgentReminders(todos: Todo[], now = new Date()): Todo[] {
  const nowMs = now.getTime();
  return todos.filter((todo) => {
    const at = reminderGoesOutAt(todo);
    return at !== null && at <= nowMs;
  });
}

export function listUrgentReminderIds(todos: Todo[], now = new Date()): string[] {
  return listUrgentReminders(todos, now).map((todo) => todo.id);
}

export function countUnseenUrgentReminders(
  todos: Todo[],
  seenIds: Set<string>,
  now = new Date(),
): number {
  return listUrgentReminders(todos, now).filter((todo) => !seenIds.has(todo.id)).length;
}
