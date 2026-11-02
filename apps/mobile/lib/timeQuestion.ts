/**
 * Time answers as the reply carries them. The server decides what a time
 * question is (`is_time_question` in apps/api/app/services/time_context.py)
 * and answers a local one with an empty ```clock fence; the phone only reads
 * the reply, never the user's words.
 */

import { parseFenceLang } from "@/lib/codeHighlight";
import { mapClosedFences, scanFences } from "@/lib/mdFenceScan";

const DIGITAL_TIME_ONLY =
  /^\d{1,2}:\d{2}(?::\d{2})?(?:\s*(?:AM|PM))?$/i;

/** An IANA zone name ("America/New_York", "Etc/GMT+5"), not any word/word ("TCP/IP"). */
const IANA_TIMEZONE_ONLY =
  /^(?:Africa|America|Antarctica|Arctic|Asia|Atlantic|Australia|Europe|Indian|Pacific|Etc)\/[A-Za-z0-9_+\-]+(?:\/[A-Za-z_\-]+)?$/;

/** The body of the reply's first closed fence, any language. */
function firstFenceBody(markdown: string): string | null {
  return scanFences(markdown).find((span) => span.closed)?.body ?? null;
}

export function isDigitalTimeOnly(text: string): boolean {
  const t = text.trim().replace(/^\*\*|\*\*$/g, "").trim();
  return DIGITAL_TIME_ONLY.test(t);
}

export function isIanaTimezoneOnly(text: string): boolean {
  return IANA_TIMEZONE_ONLY.test(text.trim());
}

export function isClockFenceBody(text: string): boolean {
  const body = text.trim();
  if (!body) return true;
  return isDigitalTimeOnly(body) || isIanaTimezoneOnly(body);
}

/** Strip time-answer fences (static time, timezone, empty clock blocks). */
export function stripTimeAnswerFences(markdown: string): string {
  return mapClosedFences(markdown, (_info, body, original) =>
    isClockFenceBody(body) ? "" : original,
  )
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function extractClockTimezone(markdown: string): string {
  const body = firstFenceBody(markdown)?.trim() ?? "";
  return isIanaTimezoneOnly(body) ? body : "";
}

/**
 * True when the reply is a time answer, so the live clock card shows: a
 * ```clock fence, or a first fence holding only a clock reading or a timezone.
 */
export function assistantReplyIsTimeAnswer(content: string): boolean {
  // A ```clock fence, even one still streaming.
  if (scanFences(content).some((span) => parseFenceLang(span.info) === "clock")) return true;
  const body = firstFenceBody(content);
  if (body == null) return false;
  return isDigitalTimeOnly(body) || isIanaTimezoneOnly(body);
}
