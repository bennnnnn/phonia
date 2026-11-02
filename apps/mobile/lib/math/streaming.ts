import { readInlineMathSpan } from "@/lib/markdown/inlineMath";
import { revealCurrencyDollars } from "@/lib/markdown/preprocessMathInline";
import {
  PROTECTED_ESCAPE_MARKER,
  PROTECTED_LITERAL_DOLLAR,
  PROTECTED_MATH_APOSTROPHE_MARKER,
  PROTECTED_MATH_STAR_MARKER,
  PROTECTED_MATH_UNDERSCORE_MARKER,
} from "@/lib/math/text";

/** In-progress commands/groups are not meaningful native-math previews yet. */
export function hasIncompleteStreamingLatex(body: string): boolean {
  let braces = 0;
  for (let i = 0; i < body.length; i += 1) {
    if (body[i] === "\\") { i += 1; continue; }
    if (body[i] === "{") braces += 1;
    else if (body[i] === "}") braces -= 1;
  }
  const begins = body.match(/\\begin\{[\w*]+\}/g)?.length ?? 0;
  const ends = body.match(/\\end\{[\w*]+\}/g)?.length ?? 0;
  const trimmed = body.trimEnd();
  if (braces !== 0 || begins > ends || /\\[A-Za-z]*$/.test(trimmed)) return true;
  // A trailing script marker or an unclosed root index is not a formula yet.
  if (/[\^_]$/.test(trimmed) || /\\sqrt\[[^\]]*$/.test(trimmed)) return true;
  // A balanced numerator alone is still only half of a fraction.
  for (const match of body.matchAll(/\\(?:[dtc]?frac)(?![A-Za-z])/g)) {
    let at = match.index + match[0].length;
    for (let arg = 0; arg < 2; arg += 1) {
      while (/\s/.test(body[at] ?? "") && at < body.length) at += 1;
      if (body[at] !== "{") return true;
      let depth = 1;
      at += 1;
      while (at < body.length && depth > 0) {
        if (body[at] === "\\") at += 1;
        else if (body[at] === "{") depth += 1;
        else if (body[at] === "}") depth -= 1;
        at += 1;
      }
      if (depth > 0) return true;
    }
  }
  return false;
}

const MAX_INCOMPLETE_LATEX_TRIM = 800;

/**
 * Longest closed prefix of a display-math tail. An unfinished command stays
 * blank instead of a placeholder bar; a finished formula before it still draws.
 */
export function completeStreamingLatex(body: string): string {
  let source = body.trim();
  if (!source || !hasIncompleteStreamingLatex(source)) return source;
  for (let trimmed = 0; trimmed < MAX_INCOMPLETE_LATEX_TRIM && source; trimmed += 1) {
    source = source.slice(0, -1).trimEnd();
    if (source && !hasIncompleteStreamingLatex(source)) return source.trim();
  }
  return "";
}

/**
 * A `$` with no closer yet that opens an unfinished formula: one that starts
 * like maths, or whose line already holds TeX (`$12 \times 3`,
 * `$[\text{H}^+]`). A price stays visible. An escaped `\$` inside the
 * formula is a dollar sign, not its closer.
 */
export function unfinishedFormulaAt(text: string, i: number): boolean {
  if (text[i] !== "$" || text.slice(i + 1).search(/(?<!\\)\$/) >= 0) return false;
  const line = text.slice(i + 1).split("\n", 1)[0] ?? "";
  // `**` after an amount is bold ("**$18**"), not a product.
  return /^(?:\\(?:[A-Za-z]|$)|[a-zA-Z](?:[\s_^=']|$)|\d+(?:[_^+/=-]|\*(?!\*))|\{)/.test(line) ||
    /\\|[\^_]\{/.test(line);
}

/** Protect complete inline math in the live tail, holding only an unfinished
 * explicit formula. Ordinary dollars and backticked source remain visible. */
export function prepareStreamingMathText(text: string): { text: string; pending: boolean } {
  text = revealCurrencyDollars(text);
  let out = "";
  for (let i = 0; i < text.length;) {
    if (text[i - 1] === "(" && text[i] === "$") {
      const tier = /^\${1,4}\)/.exec(text.slice(i));
      if (tier) { out += tier[0]; i += tier[0].length; continue; }
    }
    if (text[i] === "`") {
      let openerEnd = i + 1;
      while (text[openerEnd] === "`") openerEnd += 1;
      const ticks = text.slice(i, openerEnd);
      const end = text.indexOf(ticks, openerEnd);
      const next = end < 0 ? text.length : end + ticks.length;
      out += text.slice(i, next);
      i = next;
      continue;
    }
    const span = readInlineMathSpan(text, i, true);
    // "Half of $38.40 = $" may go on "19.20": a price-led pair whose body
    // stops on an operator or a space, closing where the stream has got to,
    // waits for the next character. "$2 + 2 = 4$" draws at once.
    if (span && text[i] === "$" && text[i + 1] !== "$" && /^\s*\d/.test(span.value)
      && /[\s=+\-*/×·]$/.test(text.slice(i + 1, span.end - 1)) && !text.slice(span.end).trim()) {
      return { text: out, pending: true };
    }
    if (span) {
      const body = span.value
        // Keep a multiline explicit formula inside one single-dollar span.
        .split(/\r?\n/).map((line) => line.trim()).join(" ")
        .split("\\$")
        .join(PROTECTED_LITERAL_DOLLAR)
        .replace(/\\/g, PROTECTED_ESCAPE_MARKER)
        .replace(/_/g, PROTECTED_MATH_UNDERSCORE_MARKER)
        .replace(/\*/g, PROTECTED_MATH_STAR_MARKER)
        .replace(/'/g, PROTECTED_MATH_APOSTROPHE_MARKER);
      out += `$${body}$`;
      i = span.end;
      continue;
    }
    if (text.startsWith("\\(", i) || text.startsWith("\\[", i) || text.startsWith("$$", i)) {
      return { text: out, pending: true };
    }
    if (unfinishedFormulaAt(text, i)) return { text: out, pending: true };
    if (text[i] === "\\" && i + 1 < text.length) {
      // Preserve escaped dollars/backslashes, rather than treating their
      // second character as a math opener on the next iteration.
      out += text.slice(i, i + 2);
      i += 2;
    } else {
      out += text[i];
      i += 1;
    }
  }
  return { text: out, pending: false };
}
