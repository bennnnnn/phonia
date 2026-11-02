// **Answer**, **Answer:**, ## Answer, Answer:, **Answer (a)** — the heading written above a card.
const ANSWER_HEADING = /^(?:#{1,4}\s+)?(?:\*\*)?answer(?:\s*\(([a-h])\))?:?(?:\*\*)?:?$/i;
// "Answer: 26.3\,\mathrm{N·m}": a heading and its value on one line.
const ANSWER_WITH_VALUE = /^(?:\*\*)?answer:(?:\*\*)?\s*(\S.*)$/i;
// Every fence the card draws: ```answer, ~~~result, ```final.
const ANSWER_FENCE = /^(?:`{3,}|~{3,})\s*(?:answer|result|final)\b/i;

function answerHeading(line: string): { part: string | null } | null {
  const match = ANSWER_HEADING.exec(line.trim());
  return match ? { part: match[1]?.toLowerCase() ?? null } : null;
}

// A line that only restates the value the card will show: maths, an "x = ...", or
// a "(or -2.5)" aside. Prose is working or an explanation and stays.
const RESTATED_VALUE = /^(?:\$[^$]+\$|\\\(.+\\\)|[A-Za-z]\s*[=≈<>≤≥].{0,40})(?:\s*\((?:or|about|≈)[^)]{0,30}\))?[.\s]*$/i;
// How far above its card a heading may sit, past restated values and other headings.
const MAX_LOOKAHEAD = 6;

function restatesValue(line: string): boolean {
  return RESTATED_VALUE.test(line) || ANSWER_WITH_VALUE.test(line);
}

/** "Answer: 26.3\,\mathrm{N·m}" under an Answer heading: the value alone, LaTeX as maths. */
function valueOnly(line: string): string {
  const value = ANSWER_WITH_VALUE.exec(line.trim())?.[1]?.trim() ?? line;
  return /\\[a-zA-Z]/.test(value) && !value.includes("$") ? `$${value}$` : value;
}

/**
 * Every answer card draws its own "Answer" heading, checked or not. Drop the
 * **Answer** heading written above one, so the word shows once, and the lines
 * between them that only restate the card's value ("$x = -5/2$ (or -2.5)",
 * "Answer: x = -5/2"): kept, they read as a second Answer section. A part's
 * heading (**Answer (a)**) gives the card its letter. With no card below, a
 * written-out Answer section is the answer and stays, its "Answer:" line
 * reduced to the value.
 */
export function attachAnswerHeadingToFence(markdown: string): string {
  const lines = markdown.split("\n");
  const out: string[] = [];
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i] ?? "";
    const heading = answerHeading(line);
    const inline = !heading && ANSWER_WITH_VALUE.test(line.trim());
    if (!heading && !inline) {
      out.push(line);
      continue;
    }
    let fenceAt = -1;
    for (let j = i + 1; j < lines.length && j <= i + MAX_LOOKAHEAD; j += 1) {
      const next = (lines[j] ?? "").trim();
      if (ANSWER_FENCE.test(next)) {
        fenceAt = j;
        break;
      }
      if (next === "" || answerHeading(next) || restatesValue(next)) continue;
      break;
    }
    if (fenceAt !== -1) {
      i = fenceAt - 1;
      const part = heading?.part;
      // The card's letter rides in its header lines (lib/answerNotation.ts).
      if (part) {
        out.push(lines[fenceAt] ?? "", `part: ${part}`);
        i = fenceAt;
      }
      continue;
    }
    out.push(line);
    if (!heading) continue;
    // No card: the written-out section keeps its heading, and "Answer: X" under it is X.
    let j = i + 1;
    while (j < lines.length && (lines[j] ?? "").trim() === "") out.push(lines[j++] ?? "");
    if (j < lines.length && ANSWER_WITH_VALUE.test((lines[j] ?? "").trim())) {
      out.push(valueOnly(lines[j] ?? ""));
      i = j;
    } else {
      i = j - 1;
    }
  }
  return out.join("\n");
}
