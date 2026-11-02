/**
 * CommonMark inline code spans, as markdown-it reads them.
 *
 * A code span binds tighter than anything else on the line: markdown-it
 * cuts it out before our `$...$` maths split ever sees the text. Every
 * string-level pass that pairs dollars must agree, or it pairs a `$` with a
 * dollar on the far side of a code span and rewrites the code between them.
 * The API's twin is apps/api/app/modules/chat/inline_code.py.
 */

/** True when an odd run of backslashes escapes `text[at]`. */
export function escapedAt(text: string, at: number): boolean {
  let slashes = 0;
  for (let i = at - 1; i >= 0 && text[i] === "\\"; i -= 1) slashes += 1;
  return slashes % 2 === 1;
}

/** Start of the first blank line after `from`: a paragraph, and any code
 * span in it, ends there. */
function paragraphEnd(text: string, from: number): number {
  for (let nl = text.indexOf("\n", from); nl >= 0; nl = text.indexOf("\n", nl + 1)) {
    let next = nl + 1;
    while (text[next] === " " || text[next] === "\t") next += 1;
    if (text[next] === "\n") return nl;
  }
  return text.length;
}

/**
 * End (exclusive) of the complete code span whose backtick run starts at
 * `start`, or null when that run opens nothing: an escaped tick, the middle
 * of a run, or a run with no closing run of the same length in its paragraph.
 */
export function readInlineCodeSpan(text: string, start: number): number | null {
  if (text[start] !== "`" || text[start - 1] === "`" || escapedAt(text, start)) return null;
  let openerEnd = start + 1;
  while (text[openerEnd] === "`") openerEnd += 1;
  const length = openerEnd - start;
  const stop = paragraphEnd(text, openerEnd);
  for (let tick = text.indexOf("`", openerEnd); tick >= 0 && tick < stop;) {
    let runEnd = tick + 1;
    while (text[runEnd] === "`") runEnd += 1;
    if (runEnd - tick === length) return runEnd;
    tick = text.indexOf("`", runEnd);
  }
  return null;
}

/** True when a complete code span opens anywhere in `[from, to)`. */
export function codeSpanOpensWithin(text: string, from: number, to: number): boolean {
  for (let i = text.indexOf("`", from); i >= 0 && i < to; i = text.indexOf("`", i + 1)) {
    if (readInlineCodeSpan(text, i) != null) return true;
  }
  return false;
}
