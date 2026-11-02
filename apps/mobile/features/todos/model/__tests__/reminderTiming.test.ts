import {
  DEFAULT_REMINDER_LEAD_MINUTES,
  normalizeReminderLeadMinutes,
} from "@/features/todos/model/reminderTiming";

describe("reminderTiming", () => {
  it("normalizes lead minutes to allowed values", () => {
    expect(normalizeReminderLeadMinutes(15)).toBe(15);
    expect(normalizeReminderLeadMinutes("30")).toBe(30);
    expect(normalizeReminderLeadMinutes(60)).toBe(60);
    expect(normalizeReminderLeadMinutes(99)).toBe(DEFAULT_REMINDER_LEAD_MINUTES);
  });
});
