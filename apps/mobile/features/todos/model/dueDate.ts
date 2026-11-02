import i18n from "@/lib/i18n";
import { formatDate } from "@/lib/datetime/format";

type DueTone = "overdue" | "today" | "soon" | "later";

export function describeDueAt(iso: string | null | undefined): {
  label: string;
  tone: DueTone;
} | null {
  if (!iso) return null;
  const due = new Date(iso);
  if (Number.isNaN(due.getTime())) return null;

  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfDue = new Date(due.getFullYear(), due.getMonth(), due.getDate());
  const dayDiff = Math.round(
    (startOfDue.getTime() - startOfToday.getTime()) / (24 * 60 * 60 * 1000),
  );

  if (due.getTime() < now.getTime()) {
    if (dayDiff === 0) return { label: i18n.t("todos.overdue_today"), tone: "overdue" };
    const days = Math.max(1, Math.abs(dayDiff));
    return { label: i18n.t("todos.overdue_days", { count: days }), tone: "overdue" };
  }
  if (dayDiff === 0) {
    return {
      label: i18n.t("todos.due_today_time", {
        time: formatDate(due, "time"),
      }),
      tone: "today",
    };
  }
  if (dayDiff === 1) return { label: i18n.t("calendar.tomorrow_heading"), tone: "soon" };
  if (dayDiff <= 7) {
    return {
      label: formatDate(due, "weekdayDate"),
      tone: "soon",
    };
  }
  return {
    label: formatDate(due, "monthDayYear"),
    tone: "later",
  };
}

export function toDueAtIso(date: Date): string {
  return date.toISOString();
}

/** Keep the clock time and take the calendar day, including the year. */
export function withCalendarDate(current: Date, picked: Date): Date {
  const next = new Date(current);
  next.setFullYear(picked.getFullYear(), picked.getMonth(), picked.getDate());
  return next;
}

/** A new to-do's suggested time: 9:00 today, or the next whole hour once it is past nine. */
export function defaultDueDate(): Date {
  const now = new Date();
  const nineToday = new Date(now);
  nineToday.setHours(9, 0, 0, 0);
  if (nineToday.getTime() > now.getTime()) return nineToday;
  const nextHour = new Date(now);
  nextHour.setMinutes(0, 0, 0);
  nextHour.setHours(nextHour.getHours() + 1);
  return nextHour;
}
