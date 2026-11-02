/**
 * The reminder lead the Settings and to-do editor offer and show. When a reminder goes out is
 * the server's (each to-do's `notify_at`, or its preview for a due time the editor has not
 * saved, `features/todos/hooks/useRemindAt.ts`): the phone never works it out.
 */

export const REMINDER_LEAD_OPTIONS = [5, 10, 15, 30, 60] as const;
type ReminderLeadMinutes = (typeof REMINDER_LEAD_OPTIONS)[number];

export const DEFAULT_REMINDER_LEAD_MINUTES: ReminderLeadMinutes = 10;

export function normalizeReminderLeadMinutes(raw: unknown): ReminderLeadMinutes {
  const parsed =
    typeof raw === "number" ? raw : Number.parseInt(String(raw ?? ""), 10);
  if (REMINDER_LEAD_OPTIONS.includes(parsed as ReminderLeadMinutes)) {
    return parsed as ReminderLeadMinutes;
  }
  return DEFAULT_REMINDER_LEAD_MINUTES;
}
