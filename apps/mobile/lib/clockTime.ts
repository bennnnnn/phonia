import { formatDate, formatTimeZoneName, userTimeZone, wallClock } from "@/lib/datetime/format";

/** Local clock parts for an IANA timezone. */
export type ClockParts = {
  hours: number;
  minutes: number;
  seconds: number;
  dateLabel: string;
  timeLabel: string;
  tzLabel: string;
};

/** The zone a clock fence names on its first line, or undefined for the user's own. */
export function resolveClockTimezone(content: string): string | undefined {
  const line = content.trim().split("\n")[0]?.trim() ?? "";
  if (line.includes("/") && !line.includes(":") && formatTimeZoneName(new Date(), line)) return line;
  return undefined;
}

/**
 * The clock's hands, date, time and zone name in `timeZone` (the user's when
 * undefined), written like every other date: the app's language and the phone's
 * 12/24-hour setting.
 */
export function getClockParts(date: Date, timeZone: string | undefined): ClockParts {
  const wall = wallClock(date, timeZone);
  const zone = timeZone ?? userTimeZone();
  return {
    hours: wall.hour % 12,
    minutes: wall.minute,
    seconds: wall.second,
    dateLabel: formatDate(date, "fullDate", { timeZone }),
    timeLabel: formatDate(date, "timeWithSeconds", { timeZone }),
    tzLabel: zone ? (formatTimeZoneName(date, zone) ?? zone) : "",
  };
}

/** Degrees from 12 o'clock, clockwise. */
export function handAngle(
  hours: number,
  minutes: number,
  seconds: number,
  kind: "hour" | "minute" | "second",
): number {
  if (kind === "second") return (seconds / 60) * 360;
  if (kind === "minute") return ((minutes + seconds / 60) / 60) * 360;
  return ((hours + minutes / 60 + seconds / 3600) / 12) * 360;
}
