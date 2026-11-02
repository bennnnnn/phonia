/**
 * Whether a plain line is a chain to lay out, and how a laid-out line ends: its note and
 * its hard break (twin: calculation_layout_tail.py).
 */
import { LETTER } from "@/lib/markdown/unicodeChars";

// A unit after a value ("km/h", "m/s²", "N.", "kg·m/s"): letter runs of three or fewer, so
// "here" or "only" read as words.
const UNIT_TAIL = /^[A-Za-zµμΩ°]{1,3}(?:[/·^][A-Za-zµμΩ°0-9²³⁻¹]{1,3}|[0-9²³⁻¹]{1,2}){0,3}[.,;:!?]*$/;

/**
 * The laid-out rows of a line, then whatever followed the maths.
 *
 * "$h = …, k = …$ — Vertex of a parabola": the note names the first row, not a
 * line of its own. The line's hard break ("…$  ") still ends it, or the next
 * line runs on.
 */
export function finishInline(parts: string[], tail: string): string {
  const note = tail.trim();
  const last = parts.length > 0 ? parts[parts.length - 1] : "";
  if (note.startsWith("— ") && last.includes("\n")) {
    const cut = last.indexOf("\n");
    parts[parts.length - 1] =
      `${last.slice(0, cut).trimEnd()} ${note}  \n${last.slice(cut + 1)}`;
  } else if (parts.length > 0 && UNIT_TAIL.test(note)) {
    // "$d = 120 + 60 = 180$ km": the unit stays with the last row's value.
    parts[parts.length - 1] = `${last.trimEnd()} ${note}`;
  } else if (note) {
    parts.push(parts.length > 0 ? tail.trimStart() : tail);
  }
  return keepHardBreak(tail, parts.join("\n"));
}

/**
 * Prose follows a maths span on its line: the span is part of a sentence.
 *
 * "has $\Delta = 9 - 8 = 1$, giving …" or "$v = 100/20 = 5$ m/s, so it is slow" split
 * into rows broke the sentence into fragments, a unit or a clause alone on a line. A
 * chain that ends its line ("**Step 1:** $x = 2 + 3 = 5$"), or whose line ends in a unit
 * ("$d = 120 + 60 = 180$ km") or a note ("$h = …$ — Vertex of a parabola"), is a worked
 * step and still splits.
 */
export function continuesSentence(after: string): boolean {
  const rest = after.replace(/^[.,;:!?]+/, "").trim();
  return rest.length > 0 && !rest.startsWith("— ") && !UNIT_TAIL.test(rest);
}

/** `laid` ends with `original`'s hard break, if it had one. */
export function keepHardBreak(original: string, laid: string): string {
  return original.endsWith("  ") ? `${laid.trimEnd()}  ` : laid;
}

// Subscript digits and charges are chemistry notation (C₃H₈, Fe²⁺): typeset as maths,
// its formulas and units went italic ("n(C₃H₈) = 0.227 mol").
const CHEMISTRY_MARKS = /[₀-₉⁺⁻]/;

/** A plain line that stays text: a word of four letters or more, or chemistry notation. */
export function readsAsProse(text: string): boolean {
  let run = 0;
  for (const char of text) {
    if (CHEMISTRY_MARKS.test(char)) return true;
    run = LETTER.test(char) ? run + 1 : 0;
    if (run >= 4) return true;
  }
  return false;
}

// How a value's unit is written: \mathrm{km/h}, \text{ m}, \Omega, 30^\circ.
const UNIT_MARKS = ["\\mathrm{", "\\text{", "\\Omega", "^\\circ", "°"];
const hasUnit = (segment: string) => UNIT_MARKS.some((mark) => segment.includes(mark));

/**
 * `v = 100 km/h × 1000/3600 = 27.8 m/s`: a symbol's value in two units, one row.
 *
 * Every value after the symbol carries its unit. A chain that works a value out
 * (`a = (27.8 − 0)/8 = 3.47 m/s²`) has bare numbers until its end, and splits;
 * so does one through another symbol (`F = ma = …`), or from a value rather than a
 * symbol (`1 km = 1000 m = 100000 cm`).
 */
export function convertsUnits(segments: string[]): boolean {
  return (
    segments.length > 2 && !/^\d/.test((segments[0] ?? "").trim()) && segments.slice(1).every(hasUnit)
  );
}
