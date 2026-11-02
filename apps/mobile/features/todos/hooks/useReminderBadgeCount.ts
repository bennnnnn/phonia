import { useTodosOptional } from "@/features/todos/context/TodosContext";

export function useReminderBadgeCount(options?: { enabled?: boolean }) {
  const enabled = options?.enabled ?? true;
  const ctx = useTodosOptional();

  if (!ctx || !enabled) {
    return {
      unseenCount: 0,
      showIndicator: false,
      markSeen: async () => {},
      refresh: async () => {},
    };
  }

  return {
    unseenCount: ctx.unseenCount,
    showIndicator: ctx.showIndicator && ctx.remindersReady,
    markSeen: ctx.markSeen,
    refresh: ctx.refresh,
  };
}
