/**
 * The phone's half of a server-written fence's schema: strict readers that refuse what
 * the server's Pydantic model refuses. The circuit, optics and simulation parsers each
 * kept their own copy, so a limit changed on the server had to be found three times
 * (code-health audit DUP-13). A parser reads inside `guard`: any refusal makes the whole
 * fence unreadable (null), never half a picture.
 */

import { isJsonRecord } from "@/lib/jsonFence";

class Refused extends Error {}

/** Refuse the fence being read. */
export function refuse(): never {
  throw new Refused();
}

/** `read()`, or null when it refused the fence; any other error is a bug and still throws. */
export function guard<T>(read: () => T): T | null {
  try {
    return read();
  } catch (error) {
    if (error instanceof Refused) return null;
    throw error;
  }
}

/**
 * Strictly a JSON number. `Number(null)` and `Number("")` are both 0, so a coercing
 * reader takes a missing coordinate for the origin; the server always sends numbers.
 */
export function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function requireNumber(value: unknown): number {
  return finiteNumber(value) ?? refuse();
}

/** A JSON object: not null and not an array. */
export function requireRecord(raw: unknown): Record<string, unknown> {
  return isJsonRecord(raw) ? raw : refuse();
}

/** Length in code points, which is what the server's `max_length` counts. */
export function codePoints(text: string): number {
  return Array.from(text).length;
}

/** An optional string of at most `max` code points; null, missing and "" are absent. */
export function optionalText(value: unknown, max: number): string | undefined {
  if (value === undefined || value === null) return undefined;
  if (typeof value !== "string" || codePoints(value) > max) refuse();
  return value.length > 0 ? value : undefined;
}

/** An optional boolean: null and missing are `fallback`. */
export function optionalBool(value: unknown, fallback: boolean): boolean {
  if (value === undefined || value === null) return fallback;
  return typeof value === "boolean" ? value : refuse();
}

/** A strictly finite `[x, y]` pair, or null. */
export function readPoint(raw: unknown): { x: number; y: number } | null {
  if (!Array.isArray(raw) || raw.length !== 2) return null;
  const x = finiteNumber(raw[0]);
  const y = finiteNumber(raw[1]);
  return x === null || y === null ? null : { x, y };
}

/** An `[x, y]` the fence must hold. */
export function requirePoint(raw: unknown): { x: number; y: number } {
  return readPoint(raw) ?? refuse();
}

/**
 * A list field with a default (Pydantic's `default_factory=list`): missing is empty;
 * null, or anything but a short enough array, is refused.
 */
export function optionalList(value: unknown, max: number): unknown[] {
  if (value === undefined) return [];
  if (!Array.isArray(value) || value.length > max) refuse();
  return value;
}
