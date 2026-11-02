import { useEffect, useState } from "react";

import type { Todo } from "@/lib/api";
import { reminderGoesOutAt } from "@/features/todos/model/reminderBadge";
import { onAppStateChange } from "@/lib/foregroundRefresh";

/** Older than this, the clock reads again before it schedules the next change. */
const STALE_MS = 1000;
/** A due time has passed once its minute has (`minutes_until` floors): wake just after. */
const AFTER_MS = 500;
/** The longest a timer can wait; a later change is scheduled when it fires. */
const MAX_WAIT_MS = 2_147_483_647;

/**
 * The next moment an open reminder changes for Home, the badge or the To-do list: its
 * reminder goes out (its `notify_at`, the server's), its due time passes, or the local day
 * turns (the list groups by day: Tomorrow becomes Today, Today becomes Overdue). Null when
 * none will.
 */
export function nextReminderChange(todos: Todo[], now: Date): number | null {
  const nowMs = now.getTime();
  let next: number | null = null;
  let dated = false;
  for (const todo of todos) {
    const goesOut = reminderGoesOutAt(todo);
    const dueMs = todo.due_at ? Date.parse(todo.due_at) : NaN;
    if (goesOut === null || Number.isNaN(dueMs)) continue;
    dated = true;
    for (const at of [goesOut, dueMs]) {
      if (at >= nowMs && (next === null || at < next)) next = at;
    }
  }
  if (dated) {
    const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1).getTime();
    if (next === null || midnight < next) next = midnight;
  }
  return next;
}

/**
 * The time the to-do views read. Home read the clock once, when the to-dos last changed,
 * so a reminder that fell due while the app stayed open showed as overdue only after a
 * restart. This time moves on when the list changes, when a reminder goes out or falls
 * due, and when the app comes back to the foreground.
 */
export function useReminderClock(todos: Todo[]): Date {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const current = Date.now();
    // A new list reads the clock again: a to-do saved already overdue is overdue now.
    if (current - now.getTime() >= STALE_MS) {
      setNow(new Date(current));
      return;
    }
    const next = nextReminderChange(todos, new Date(current));
    if (next === null) return;
    const wait = Math.min(Math.max(next - current, 0) + AFTER_MS, MAX_WAIT_MS);
    const timer = setTimeout(() => setNow(new Date()), wait);
    return () => clearTimeout(timer);
  }, [todos, now]);

  useEffect(
    () =>
      onAppStateChange((state) => {
        if (state === "active") setNow(new Date());
      }),
    [],
  );

  return now;
}
