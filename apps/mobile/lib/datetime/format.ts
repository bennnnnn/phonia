/**
 * Every date and time a person reads is formatted here, the same way:
 *
 * - **Language:** the app's language setting (`i18n.language`), never the phone's
 *   locale. Some screens wrote the phone's and others the app's: with the app in
 *   German on an English phone, a to-do row said "23:30" and its editor "11:30 PM".
 * - **Time zone:** the user's, which on the phone is the device's. The profile's
 *   `timezone` is the server's copy of it: `useBootstrapSync` writes the device zone
 *   there (at sign-in, when the OS reports a new zone, on each return to the
 *   foreground) and no screen sets another. It is "UTC" on a new account until that
 *   sync, "" on a cold start until `/auth/me` answers (`mergeCachedUser`), and the old
 *   zone after a flight until that report lands. Every day the phone works out (the to-do
 *   day groups, `describeDueAt`, the reminder clock's midnight, the drawer's own
 *   inserts, the date and time pickers) reads local `Date` fields, the device zone,
 *   so a time drawn in the profile's zone could sit under another day's heading and
 *   the picker would edit a time other than the one shown. When the engine cannot
 *   name the zone, the engine's own is used (the one those fields read), never "UTC".
 *   An explicit `timeZone` is for a time that belongs to another zone: a reminder
 *   card in the zone the server read it in, a clock fence's city, a calendar day.
 * - **Hour cycle:** the phone's 12/24-hour setting (`phoneClock.ts`), as an explicit
 *   `hourCycle` "h23" or "h12", never `hour12`: engines resolve `hour12` against the
 *   language's own default, and the older ECMA-402 rule turns it into "0:05 PM" (h11)
 *   for German or "24:05" (h24) for English. None of the app's languages writes h11
 *   or h24. A build that cannot read the setting uses the phone locale's convention.
 * - **Week start:** the phone's First Day of Week (`phoneClock.ts`), where the date
 *   picker's month grid begins; the phone locale's region when a build cannot read it.
 *
 * Formatters are cached by language, zone, hour cycle and style, because a cached
 * formatter keeps the zone it was built in. `toLocale*String` with options built one
 * per call: 39–44 µs against about 1 µs here (Node 22). The zone, the hour cycle and
 * the week start are read once, and again when the app returns to the foreground, when
 * the OS reports a change (`phoneClockSync.ts`), or when the zone's offset moves under a
 * format call.
 * A change re-renders every view that translates (`DATE_FORMAT_CHANGED`). The language
 * is read from the i18next instance itself, so this file needs nothing of `lib/i18n`.
 *
 * Not here: ISO strings sent to the server or stored, and maths, physics or
 * chemistry content.
 */
import i18n from "i18next";

import { readPhoneClock, type HourCycle, type PhoneClock, type Weekday } from "@/lib/datetime/phoneClock";

/**
 * Sent on the i18next instance `lib/i18n` sets up when the phone's zone, 12/24-hour
 * setting or first day of the week changes. It binds every `useTranslation` view to it as to a language change,
 * so a view re-renders when any of a date's three inputs does, memoized rows included.
 */
export const DATE_FORMAT_CHANGED = "dateFormatChanged";

const STYLES = {
  /** "3:05 PM", "15:05". */
  time: { hour: "numeric", minute: "2-digit" },
  /** "3:05:09 PM". */
  timeWithSeconds: { hour: "numeric", minute: "2-digit", second: "2-digit" },
  /** "Tue 3:05 PM": a time a day off the one beside it, such as a reminder's. */
  weekdayTime: { weekday: "short", hour: "numeric", minute: "2-digit" },
  /** "Tue, Sep 8". */
  weekdayDate: { weekday: "short", month: "short", day: "numeric" },
  /** "Tuesday, Sep 8". */
  longWeekdayDate: { weekday: "long", month: "short", day: "numeric" },
  /** "Sep 8". */
  monthDay: { month: "short", day: "numeric" },
  /** "Sep 8, 2026". */
  monthDayYear: { month: "short", day: "numeric", year: "numeric" },
  /** "Tuesday, September 8, 2026". */
  fullDate: { weekday: "long", month: "long", day: "numeric", year: "numeric" },
  /** "September 2026". */
  monthYear: { month: "long", year: "numeric" },
  /** "T". */
  narrowWeekday: { weekday: "narrow" },
  /** "Tuesday". */
  longWeekday: { weekday: "long" },
  /** "3 PM": its parts name the language's AM and PM. */
  hour: { hour: "numeric" },
  /** Its parts hold the zone's short name ("EDT"). */
  zoneName: { timeZoneName: "short" },
} as const satisfies Record<string, Intl.DateTimeFormatOptions>;

type DateStyle = keyof typeof STYLES;

type FormatOptions = {
  /** A time that belongs to another zone than the user's (see above). */
  timeZone?: string;
  /** A time picker held to a 12- or 24-hour dial says its time the same way. */
  hourCycle?: HourCycle;
};

/** More formatters than the app ever asks for at once: a backstop, not a budget. */
const MAX_FORMATTERS = 256;

let phoneClock: (PhoneClock & { offset: number }) | null = null;
const formatters = new Map<string, Intl.DateTimeFormat>();

function readClock(offset: number): void {
  const before = phoneClock;
  const next = { ...readPhoneClock(), offset };
  phoneClock = next;
  if (
    !before ||
    (before.timeZone === next.timeZone && before.hourCycle === next.hourCycle && before.weekStart === next.weekStart)
  ) {
    return;
  }
  // Never inside the render that noticed it: the translated views re-render next.
  void Promise.resolve().then(() => i18n.emit(DATE_FORMAT_CHANGED));
}

function currentClock(): PhoneClock {
  // A new zone moves the offset: read it before anything is drawn in the old one.
  const offset = new Date().getTimezoneOffset();
  if (phoneClock?.offset !== offset) readClock(offset);
  return phoneClock!;
}

/** Reads the phone's zone, 12/24-hour and week settings again; views re-render if one changed. */
export function refreshPhoneClock(): void {
  readClock(new Date().getTimezoneOffset());
}

/** The user's zone (the device's), or undefined when the engine cannot name it. */
export function userTimeZone(): string | undefined {
  return currentClock().timeZone;
}

/** The phone shows a 24-hour clock: a time picker draws the same dial. */
export function userUses24HourClock(): boolean {
  return currentClock().hourCycle === "h23";
}

/** The phone's first day of the week, or undefined when this build cannot read it. */
export function userWeekStart(): Weekday | undefined {
  return currentClock().weekStart;
}

function formatter(style: DateStyle, options: FormatOptions): Intl.DateTimeFormat {
  const clock = currentClock();
  const base: Intl.DateTimeFormatOptions = STYLES[style];
  const language = i18n.language || "en";
  const timeZone = options.timeZone ?? clock.timeZone;
  const hourCycle = base.hour ? (options.hourCycle ?? clock.hourCycle) : undefined;
  const key = `${language}|${timeZone ?? ""}|${hourCycle ?? ""}|${style}`;
  let cached = formatters.get(key);
  if (!cached) {
    cached = new Intl.DateTimeFormat(language, { ...base, timeZone, hourCycle });
    if (formatters.size >= MAX_FORMATTERS) formatters.clear();
    formatters.set(key, cached);
  }
  return cached;
}

/** `date` in `style`, in the app's language, the user's zone and the phone's hour cycle. */
export function formatDate(date: Date, style: DateStyle, options: FormatOptions = {}): string {
  return formatter(style, options).format(date);
}

export function formatDateToParts(
  date: Date,
  style: DateStyle,
  options: FormatOptions = {},
): Intl.DateTimeFormatPart[] {
  return formatter(style, options).formatToParts(date);
}

/**
 * Clock label for a minute offset after midnight. Drawn on a fixed UTC day: on today's
 * date a daylight-saving change skips an hour, and 12:00 AM read "1:00 AM" (Santiago).
 */
export function formatMinuteOfDay(minutes: number, hourCycle?: HourCycle): string {
  const date = new Date(Date.UTC(2000, 0, 1, Math.floor(minutes / 60), minutes % 60));
  return formatDate(date, "time", { timeZone: "UTC", hourCycle });
}

/**
 * A calendar day ("2026-10-16") with no time and no zone: drawn in UTC, where it
 * begins, so no zone moves it to the day before. Null for anything else.
 */
export function formatCalendarDay(day: string, style: "monthDay" | "monthDayYear"): string | null {
  const date = /^\d{4}-\d{2}-\d{2}$/.test(day) ? new Date(`${day}T00:00:00Z`) : null;
  if (!date || Number.isNaN(date.getTime())) return null;
  return formatDate(date, style, { timeZone: "UTC" });
}

/**
 * The zone's short name at that instant ("EDT", "GMT+3"), or null for an unknown zone.
 *
 * Hermes names a zone with no abbreviation (Africa/Nairobi) plain "GMT", which reads as
 * three hours off; a bare GMT or UTC for a zone that is not at zero gets its offset.
 */
export function formatTimeZoneName(date: Date, timeZone: string): string | null {
  try {
    const parts = formatDateToParts(date, "zoneName", { timeZone });
    const name = parts.find((part) => part.type === "timeZoneName")?.value ?? null;
    if (name !== "GMT" && name !== "UTC") return name;
    const minutes = zoneOffsetMinutes(date, timeZone);
    return minutes === 0 ? name : offsetLabel(minutes);
  } catch {
    return null;
  }
}

type WallClock = { year: number; month: number; day: number; hour: number; minute: number; second: number };

const wallClockFormatters = new Map<string, Intl.DateTimeFormat>();

/** The numbers a clock on the wall shows at that instant in `timeZone` (the user's when omitted). */
export function wallClock(date: Date, timeZone?: string): WallClock {
  const zone = timeZone ?? userTimeZone();
  const key = zone ?? "";
  let numeric = wallClockFormatters.get(key);
  if (!numeric) {
    numeric = new Intl.DateTimeFormat("en-US", {
      timeZone: zone,
      hourCycle: "h23",
      year: "numeric",
      month: "numeric",
      day: "numeric",
      hour: "numeric",
      minute: "numeric",
      second: "numeric",
    });
    if (wallClockFormatters.size >= MAX_FORMATTERS) wallClockFormatters.clear();
    wallClockFormatters.set(key, numeric);
  }
  const parts = numeric.formatToParts(date);
  const get = (type: Intl.DateTimeFormatPartTypes) =>
    Number(parts.find((part) => part.type === type)?.value ?? 0);
  return {
    year: get("year"),
    month: get("month"),
    day: get("day"),
    hour: get("hour"),
    minute: get("minute"),
    second: get("second"),
  };
}

/** Minutes the zone's wall clock is ahead of UTC at that instant. */
function zoneOffsetMinutes(date: Date, timeZone: string): number {
  const wall = wallClock(date, timeZone);
  const local = Date.UTC(wall.year, wall.month - 1, wall.day, wall.hour, wall.minute);
  const instant = Math.floor(date.getTime() / 60000) * 60000;
  return Math.round((local - instant) / 60000);
}

function offsetLabel(minutes: number): string {
  const sign = minutes < 0 ? "-" : "+";
  const hours = Math.floor(Math.abs(minutes) / 60);
  const rest = Math.abs(minutes) % 60;
  return `GMT${sign}${hours}${rest ? `:${String(rest).padStart(2, "0")}` : ""}`;
}
