import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Todo } from "@/lib/api";
import { loadSeenReminderIds, pruneSeenReminderIds, saveSeenReminderIds } from "@/features/todos/model/reminderSeen";
import { loadHomeNudgeState, pruneHomeNudgeState, saveHomeNudgeState } from "@/features/todos/model/homeReminderNudges";
import { countUnseenUrgentReminders, listUrgentReminderIds } from "@/features/todos/model/reminderBadge";

type Options = { userId?: string; todos: Todo[]; retainedOpenIds?: Set<string>;
  getTodos: () => Todo[]; isCurrentSession: () => boolean;
  /** The time the badge counts against (useReminderClock); the moment of render when absent. */
  now?: Date };

/** Serialize seen/nudge updates so a slow load cannot undo a newer dismissal. */
export function useTodoReminderState({ userId, todos, retainedOpenIds, getTodos, isCurrentSession, now }: Options) {
  const owner = useMemo(() => ({ isCurrentSession }), [isCurrentSession]);
  const resource = useRef({ owner, seen: new Set<string>(), dismissed: new Set<string>(),
    seenDirty: false, dismissedDirty: false, hydrated: false, queue: Promise.resolve() });
  if (resource.current.owner !== owner) resource.current = { owner, seen: new Set(), dismissed: new Set(),
    seenDirty: false, dismissedDirty: false, hydrated: false, queue: Promise.resolve() };
  const latest = useRef({ retainedOpenIds });
  latest.current = { retainedOpenIds };
  const empty = { owner, seen: new Set<string>(), dismissed: new Set<string>(), ready: false };
  const [state, setState] = useState(empty);
  const view = state.owner === owner ? state : empty;

  const run = useCallback((update?: () => void): Promise<void> => {
    const store = resource.current;
    const work = store.queue.then(async () => {
      if (!userId || !isCurrentSession()) return;
      if (!store.hydrated) {
        const [seen, nudges] = await Promise.all([loadSeenReminderIds(userId), loadHomeNudgeState(userId)]);
        if (!isCurrentSession()) return;
        store.seen = seen;
        store.dismissed = nudges.dismissed;
        store.hydrated = true;
      }
      const previousSeen = [...store.seen].join("\n");
      const previousDismissed = [...store.dismissed].join("\n");
      update?.();
      if (latest.current.retainedOpenIds) {
        const openIds = new Set([...latest.current.retainedOpenIds,
          ...getTodos().filter((row) => !row.checked).map((row) => row.id)]);
        store.seen = pruneSeenReminderIds(store.seen, openIds);
        store.dismissed = pruneHomeNudgeState({ dismissed: store.dismissed }, openIds).dismissed;
      }
      if (!isCurrentSession()) return;
      store.seenDirty ||= previousSeen !== [...store.seen].join("\n");
      store.dismissedDirty ||= previousDismissed !== [...store.dismissed].join("\n");
      // Wait for both writes before releasing the queue, and retry only failed storage.
      const writes = await Promise.allSettled([
        store.seenDirty ? saveSeenReminderIds(userId, store.seen)
          .then(() => { store.seenDirty = false; }) : undefined,
        store.dismissedDirty ? saveHomeNudgeState(userId, { dismissed: store.dismissed })
          .then(() => { store.dismissedDirty = false; }) : undefined,
      ]);
      const failed = writes.find((result) => result.status === "rejected");
      if (failed?.status === "rejected") throw failed.reason;
      if (isCurrentSession()) setState((previous) => isCurrentSession()
        ? { owner, seen: new Set(store.seen), dismissed: new Set(store.dismissed), ready: true } : previous);
    }).catch(() => {
      if (isCurrentSession()) {
        console.warn("[todos] reminder state sync failed");
        setState((previous) => isCurrentSession()
          ? { owner, seen: new Set(store.seen), dismissed: new Set(store.dismissed), ready: true } : previous);
      }
    });
    store.queue = work;
    return work;
  }, [owner, userId, isCurrentSession, getTodos]);

  useEffect(() => { void run(); }, [run, todos, retainedOpenIds]);
  const markSeenIds = useCallback((ids: string[]) => run(() => {
    ids.forEach((id) => resource.current.seen.add(id));
  }), [run]);
  const markSeen = useCallback(() => run(() => {
    listUrgentReminderIds(getTodos()).forEach((id) => resource.current.seen.add(id));
  }), [getTodos, run]);
  const dismissReminderNudge = useCallback((todoId: string) => run(() => {
    if (!getTodos().some((todo) => todo.id === todoId && !todo.checked)) return;
    resource.current.dismissed.add(todoId);
    resource.current.seen.add(todoId);
  }), [getTodos, run]);

  const unseenCount = countUnseenUrgentReminders(todos, view.seen, now);
  return { unseenCount, showIndicator: unseenCount > 0, remindersReady: view.ready,
    seenReminderIds: view.seen, homeNudgeDismissed: view.dismissed,
    markSeen, markSeenIds, dismissReminderNudge };
}
