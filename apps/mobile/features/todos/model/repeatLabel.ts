import type { RecurrenceRule } from "@/lib/api/types";

/** i18n key for a repeat choice. No rule reads "Does not repeat". */
export function repeatMessageKey(
  rule: RecurrenceRule | null,
): "todos.repeat_none" | `todos.repeat_${RecurrenceRule}` {
  return rule == null ? "todos.repeat_none" : `todos.repeat_${rule}`;
}
