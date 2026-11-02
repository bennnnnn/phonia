/**
 * What is asked: **Required**, or **Find** in a reply written before November 2026 (and in
 * one a model still heads that way).
 */
const REQUIRED_HEADINGS: readonly string[] = ["Required", "Find"];

/** The headings that open a worked reply, behind a thin rule: what it is given and what is asked. */
export const OPENING_HEADINGS: readonly string[] = ["Given", ...REQUIRED_HEADINGS];

/**
 * The heading alone between what is asked and the working (November 2026): no lines of its
 * own, the sections below it are its lines.
 */
export const SOLUTION_HEADING = "Solution";

/** **Solution** alone on its line, with an optional trailing colon. */
export function isSolutionHeading(text: string): boolean {
  return text.trim().replace(/:$/, "") === SOLUTION_HEADING;
}

/**
 * The one worked-solution layout the API writes for every subject:
 * **Given**, **Required**, **Solution** (alone, `isSolutionHeading`), the formula under
 * its name ("**Average speed formula**", see `lawHeading`; **Formula** when unnamed),
 * **Substitution** or **Steps**, **Answer** (**Answer (a)** for one part),
 * each a bold heading on its own line followed by one state per line, with
 * the move as a short note after " — " (`$2x = 8$ — subtract 3`). A rearrangement
 * for the unknown is a line of its own (`Solve for $t$`), never a note.
 */
export const WORKOUT_HEADINGS: readonly string[] = [
  ...OPENING_HEADINGS,
  "Formula",
  "Substitution",
  "Steps",
  "Answer",
];

const PART_ANSWER = /^Answer \([a-h]\)$/;

/** A heading as written, with an optional trailing colon. */
export function workoutHeading(text: string): string | null {
  const heading = text.trim().replace(/:$/, "");
  return WORKOUT_HEADINGS.includes(heading) || PART_ANSWER.test(heading) ? heading : null;
}

/** The answer of the whole question, or of one part ("Answer (a)"). */
export function isAnswerHeading(heading: string): boolean {
  return heading === "Answer" || PART_ANSWER.test(heading);
}

/**
 * A formula's own name heads its section ("**Constant acceleration formula**"), so it
 * is no fixed word: in a worked reply, a short bold line alone over a line of maths.
 */
export function lawHeading(text: string, firstLine: string): string | null {
  const heading = text.trim();
  if (!heading || /[.:?!]$/.test(heading) || heading.split(/\s+/).length > 10) return null;
  // A numbered move ("1. Subtract 4 from both sides") and a part are their own blocks.
  if (/^\d+[.)]\s/.test(heading) || workoutPart(heading)) return null;
  return /^\$/.test(firstLine.trim()) ? heading : null;
}

const WORKED_REPLY_RE = new RegExp(String.raw`^\*\*(?:${OPENING_HEADINGS.join("|")}):?\*\*`, "m");

/** A reply worked in sections: it states what it is given or what is asked (a follow-up
 * that changes one given often skips Required). */
export function isWorkedReply(text: string): boolean {
  return WORKED_REPLY_RE.test(text);
}

/** ``$2x = 8$ — subtract 3``: the state, then its move. A dash inside math is the math's. */
export function splitWorkoutNote(line: string): { state: string; note: string | null } {
  let inMath = false;
  for (let i = 0; i < line.length; i += 1) {
    if (line[i] === "$") inMath = !inMath;
    if (!inMath && line.startsWith(" — ", i)) {
      return { state: line.slice(0, i).trim(), note: line.slice(i + 3).trim() || null };
    }
  }
  return { state: line, note: null };
}

// "(a) Acceleration", "Part (b): Speed after 3 s", "c) Distance": one part of
// a question in parts, labelled by its letter and what it finds.
const WORKOUT_PART_RE =
  /^(?:part\s+\(?([a-h])\)?|\(([a-h])\)|([a-h])\))\s*[.:]?\s*(?:[—–-]\s*)?(\S.*)$/i;

/** A part label written alone in bold, or null for any other bold line. */
export function workoutPart(text: string): { letter: string; title: string } | null {
  const match = WORKOUT_PART_RE.exec(text.trim());
  if (!match) return null;
  const letter = (match[1] ?? match[2] ?? match[3] ?? "").toLowerCase();
  const title = (match[4] ?? "").trim();
  return letter && title ? { letter, title } : null;
}

