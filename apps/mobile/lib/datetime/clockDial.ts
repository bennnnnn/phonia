/**
 * Geometry and rules for the clock-face time picker (`ui/pickers`).
 *
 * Angles are degrees clockwise from 12 o'clock. Hours are 24-hour values
 * (0–23) everywhere outside the dial; a 12-hour dial shows 1–12 plus AM/PM.
 * A 24-hour dial shows 12, 1–11 on the outer ring and 00, 13–23 inside.
 */

import { formatDateToParts } from "@/lib/datetime/format";

export type TimeOfDay = { hour: number; minute: number };
export type ClockMode = "hour" | "minute";

export const HOURS_OUTER = [12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11] as const;
export const HOURS_INNER = [0, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23] as const;
export const MINUTE_MARKS = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55] as const;

/** Degrees clockwise from 12 o'clock for a point relative to the dial center. */
export function pointToAngle(dx: number, dy: number): number {
  const degrees = (Math.atan2(dx, -dy) * 180) / Math.PI;
  return (degrees + 360) % 360;
}

/** Center of a label or the hand's tip at `angle`, `radius` away from `center`. */
export function pointOnDial(
  angle: number,
  radius: number,
  center: number,
): { x: number; y: number } {
  const radians = (angle * Math.PI) / 180;
  return {
    x: center + radius * Math.sin(radians),
    y: center - radius * Math.cos(radians),
  };
}

/** A touch belongs to the inner ring when it is nearer to it than to the outer one. */
export function touchesInnerRing(
  distance: number,
  outerRadius: number,
  innerRadius: number,
): boolean {
  return distance < (outerRadius + innerRadius) / 2;
}

/** The 24-hour value under `angle`. `pm` keeps a 12-hour dial on its half of the day. */
export function hourAtAngle(
  angle: number,
  options: { is24Hour: boolean; inner: boolean; pm: boolean },
): number {
  const index = Math.round(angle / 30) % 12;
  if (options.is24Hour) {
    if (options.inner) return index === 0 ? 0 : index + 12;
    return index === 0 ? 12 : index;
  }
  return index + (options.pm ? 12 : 0);
}

/** Minute under `angle`, snapped to `step` (1 keeps every minute). */
export function minuteAtAngle(angle: number, step = 1): number {
  const minute = Math.round(angle / 6) % 60;
  if (step <= 1) return minute;
  return (Math.round(minute / step) * step) % 60;
}

export function angleForHour(hour: number): number {
  return (hour % 12) * 30;
}

export function angleForMinute(minute: number): number {
  return (minute % 60) * 6;
}

/** On a 24-hour dial, 00 and 13–23 sit on the inner ring. */
export function hourOnInnerRing(hour: number, is24Hour: boolean): boolean {
  return is24Hour && (hour === 0 || hour > 12);
}

export function to12Hour(hour: number): { hour: number; pm: boolean } {
  const rest = hour % 12;
  return { hour: rest === 0 ? 12 : rest, pm: hour >= 12 };
}

export function from12Hour(hour: number, pm: boolean): number {
  return (hour % 12) + (pm ? 12 : 0);
}

/** Keep the hour on the same clock position, in the morning or the afternoon. */
export function withDayHalf(hour: number, pm: boolean): number {
  return from12Hour(to12Hour(hour).hour, pm);
}

export function pad2(value: number): string {
  return String(value).padStart(2, "0");
}

/** What the hour box shows: 1–12 on a 12-hour clock, 00–23 on a 24-hour one. */
export function hourLabel(hour: number, is24Hour: boolean): string {
  return is24Hour ? pad2(hour) : String(to12Hour(hour).hour);
}

/** Typed hour: 1–12 on a 12-hour clock, 0–23 on a 24-hour one. Null when invalid. */
export function parseHourInput(text: string, is24Hour: boolean): number | null {
  const trimmed = text.trim();
  if (!/^\d{1,2}$/.test(trimmed)) return null;
  const value = Number(trimmed);
  if (is24Hour) return value <= 23 ? value : null;
  return value >= 1 && value <= 12 ? value : null;
}

/** Typed minute, 0–59. Null when invalid. */
export function parseMinuteInput(text: string): number | null {
  const trimmed = text.trim();
  if (!/^\d{1,2}$/.test(trimmed)) return null;
  const value = Number(trimmed);
  return value <= 59 ? value : null;
}

export function timeFromMinutes(minutes: number): TimeOfDay {
  const total = ((Math.round(minutes) % 1440) + 1440) % 1440;
  return { hour: Math.floor(total / 60), minute: total % 60 };
}

export function minutesFromTime(time: TimeOfDay): number {
  return time.hour * 60 + time.minute;
}

export function timeFromDate(date: Date): TimeOfDay {
  return { hour: date.getHours(), minute: date.getMinutes() };
}

/** A copy of `date` at `time` (seconds cleared). */
export function withTimeOfDay(date: Date, time: TimeOfDay): Date {
  const next = new Date(date.getTime());
  next.setHours(time.hour, time.minute, 0, 0);
  return next;
}

/** The app language's AM and PM words, as the 12-hour times around the picker write them. */
export function dayPeriodLabels(): { am: string; pm: string } {
  const read = (hour: number, fallback: string) => {
    try {
      const at = new Date(Date.UTC(2000, 0, 1, hour));
      const parts = formatDateToParts(at, "hour", { timeZone: "UTC", hourCycle: "h12" });
      const period = parts.find((part) => part.type === "dayPeriod")?.value.trim();
      return period || fallback;
    } catch {
      return fallback;
    }
  };
  return { am: read(9, "AM"), pm: read(21, "PM") };
}
