/**
 * Server-owned answer fences open with header lines, then the value.
 *
 * - `verified: true` — the server checked this value with a solver. It is the only
 *   thing that earns the card's green check; the server strips the line from anything
 *   a model writes, so a reply cannot forge it.
 * - `verified: false` — no solver checked it: the model worked it out. The card draws
 *   no check and no label, in a dashed box. A card from before November 2026 has neither line.
 * - `notation: chemistry` — the body is chemistry text, not LaTeX. Chemistry (and any
 *   later literal subject) keeps formulas, charges, and units as text; treating that
 *   body as algebra rewrites a correct result.
 * - `label: answer` — older replies carry it; every card draws "Answer" now, so it is
 *   read as a header and dropped.
 * - `part: a` — the card answers one part of a question in parts; it draws "Answer (a)".
 *   The phone writes it from the "**Answer (a)**" heading above the card
 *   (lib/markdown/attachAnswerHeading.ts).
 *
 * The value is the final answer alone: a calculation before it (`4 × 4 = 16`) is
 * working and left out (lib/cardValue.ts), on old cards too.
 */

import { finalAnswerOnly } from "@/lib/cardValue";

type AnswerNotation = "math" | "chemistry";

export const CHEMISTRY_ANSWER_NOTATION = "notation: chemistry";
const ANSWER_LABEL_LINE = "label: answer";
const VERIFIED_ANSWER_MARKER = "verified: true";
const UNCHECKED_ANSWER_MARKER = "verified: false";
const PART_LINE = /^part: ([a-h])$/;

function headerLine(line: string): string | null {
  // The marker must be exactly the server's line: no case, spacing, or invisible
  // characters a forged copy could hide behind.
  if (line === VERIFIED_ANSWER_MARKER || line === UNCHECKED_ANSWER_MARKER) return line;
  const trimmed = line.trim();
  if (PART_LINE.test(trimmed)) return trimmed;
  return trimmed === CHEMISTRY_ANSWER_NOTATION || trimmed === ANSWER_LABEL_LINE ? trimmed : null;
}

export function splitAnswerNotation(raw: string): {
  notation: AnswerNotation;
  body: string;
  verified: boolean;
  /** The server marked it as a value no solver checked. */
  unchecked: boolean;
  part?: string;
} {
  const lines = raw.replace(/\r\n/g, "\n").trim().split("\n");
  const headers = new Set<string>();
  // Header lines only at the top, and never the last line: a header with no value
  // after it is the value.
  while (lines.length > 1) {
    const header = headerLine(lines[0]!);
    if (header == null) break;
    headers.add(header);
    lines.shift();
  }
  const part = [...headers].map((header) => PART_LINE.exec(header)?.[1]).find(Boolean);
  return {
    notation: headers.has(CHEMISTRY_ANSWER_NOTATION) ? "chemistry" : "math",
    body: finalAnswerOnly(lines.join("\n").trim()),
    verified: headers.has(VERIFIED_ANSWER_MARKER),
    unchecked: headers.has(UNCHECKED_ANSWER_MARKER) && !headers.has(VERIFIED_ANSWER_MARKER),
    ...(part ? { part } : {}),
  };
}
