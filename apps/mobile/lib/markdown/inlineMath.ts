import { codeSpanOpensWithin, escapedAt, readInlineCodeSpan } from "@/lib/markdown/inlineCode";
import { latexHasNestedMathView, latexHasStackedFrac, restoreMathEscapes } from "@/lib/math/text";

export type InlineMathPart = { type: "text" | "math"; value: string };

const SPACED_AMOUNT = /[ \t]+\d/y;

/**
 * The `$` at `dollar` starts an amount, so it cannot close the span holding
 * `body` (pandoc: a closing `$` has no digit after it and no space before
 * it). That is a digit right after it, or, after a body that is itself a
 * price, a space on both sides and then a digit: "$38.40 = $ 19.20". A
 * padded formula keeps its closer: "Let $ x = 2 $ 3 times".
 */
function dollarOpensPrice(text: string, dollar: number, body: string): boolean {
  if (/\d/.test(text[dollar + 1] ?? "")) return true;
  if (!/\s/.test(text[dollar - 1] ?? "") || !/^\s*\d/.test(body)) return false;
  SPACED_AMOUNT.lastIndex = dollar + 1;
  return SPACED_AMOUNT.test(text);
}

/** A variable (`$2 x$`) or a function (`$2 sin x$`) after a leading number. */
const MATH_WORD = /^[a-z]$|^(?:sin|cos|tan|sec|csc|cot|log|ln|exp|lim|max|min)$/i;
/** An amount, maybe with a scale ("1.5M") or a rate ("30/day"), then a
 * clause break or a word. */
const PRICE_LEAD = /^\d[\d,.]*(?:[kKmMbB]|\/[A-Za-z]+)?(?:[;:!?](?:\s|$)|\s+([A-Za-z]+)(.*))/;

/**
 * A body that opens with an amount and goes on in words is a price that the
 * next dollar on the line would wrongly close: "$10; $x=2$", "$5 and $x$",
 * "$80/night for $n$ nights", "$100 a week for $w$ weeks". A TeX command
 * makes it maths: `$4! = 4 \times 3$`.
 */
function priceBody(value: string): boolean {
  // The live tail has swapped every backslash for a marker by now.
  if (/\\[A-Za-z]/.test(restoreMathEscapes(value))) return false;
  const lead = PRICE_LEAD.exec(value.trimStart());
  if (!lead) return false;
  const [, word, rest = ""] = lead;
  if (word === undefined || !MATH_WORD.test(word)) return true;
  // "a" reads as a variable; the prose after it does not.
  return (rest.match(/[A-Za-z]{3,}/g) ?? []).filter((w) => !MATH_WORD.test(w)).length >= 2;
}

/** A complete, explicit math span. Currency and escaped dollars stay literal,
 * and a pair never reaches across an inline code span: markdown-it cuts the
 * code out first, so `$` on either side of it are two lone dollars. */
export function readInlineMathSpan(
  text: string,
  start: number,
  display = false,
): { value: string; end: number } | null {
  const opener = text.startsWith("\\(", start) ? "\\("
    : display && text.startsWith("\\[", start) ? "\\["
      : display && text.startsWith("$$", start) ? "$$"
        : text[start] === "$" && text[start - 1] !== "$" && text[start + 1] !== "$" ? "$" : null;
  if (!opener) return null;
  // Check escaping only at an actual opener, not at every character of a
  // backslash run while callers scan the live text one character at a time.
  if (escapedAt(text, start)) return null;
  const closer = opener === "\\(" ? "\\)" : opener === "\\[" ? "\\]" : opener;
  let end = text.indexOf(closer, start + opener.length);
  while (end >= 0 && escapedAt(text, end)) end = text.indexOf(closer, end + closer.length);
  if (end < 0) return null;
  const value = text.slice(start + opener.length, end);
  if (!value.trim() || (opener === "$" && value.includes("\n"))) return null;
  if (codeSpanOpensWithin(text, start + opener.length, end)) return null;
  // "$5 and $10" contains two prices, not a math span ending before "10".
  if (opener === "$" && dollarOpensPrice(text, end, value)) return null;
  // Do not pair a price with a later formula's opener: "$10; $x=2$".
  if (opener === "$" && priceBody(value)) return null;
  return { value: value.trim(), end: end + closer.length };
}

function looksLikeEnglishMathSpan(inner: string): boolean {
  const source = restoreMathEscapes(inner);
  if (/\\[a-zA-Z]+/.test(source)) return false;
  // Words inside a subscript or superscript (`W_{lost}`, `W_{out}`) are labels, not prose.
  const prose = source.replace(/[_^]\{[^{}]*\}/g, " ");
  return (prose.match(/[A-Za-z]{3,}/g) ?? []).length >= 2;
}

/** Split prose without interpreting inline code or currency as mathematics. */
export function splitInlineMath(text: string): InlineMathPart[] {
  const parts: InlineMathPart[] = [];
  let last = 0;
  for (let i = 0; i < text.length;) {
    if (text[i] === "`") {
      // A complete code span is code. An unpaired tick is a literal tick and
      // must not hide the maths after it.
      let runEnd = i + 1;
      while (text[runEnd] === "`") runEnd += 1;
      i = readInlineCodeSpan(text, i) ?? runEnd;
      continue;
    }
    const span = readInlineMathSpan(text, i);
    if (!span) { i += 1; continue; }
    if (i > last) parts.push({ type: "text", value: text.slice(last, i) });
    // Prose-looking spans are shown as text: restore their placeholders so no private-use character reaches the reader.
    parts.push(looksLikeEnglishMathSpan(span.value)
      ? { type: "text", value: restoreMathEscapes(span.value) }
      : { type: "math", value: span.value });
    i = span.end;
    last = i;
  }
  if (last < text.length) parts.push({ type: "text", value: text.slice(last) });
  return parts.length ? parts : [{ type: "text", value: text }];
}

const NESTED_MATH_COMMAND_RE =
  /\\(?:sqrt|xcancel|bcancel|cancel|overline|underline|widehat|widetilde|overrightarrow|overleftarrow|hat|vec|bar|ddot|dot|tilde)(?![A-Za-z])|\^\{[^{}]*\/[^{}]*\}/;

/**
 * A markdown run needs a View host when a math span draws a nested View.
 * Prose carets (`a^2`) and dunder names (`__init__`) stay in Text.
 */
export function markdownHasNestedMathView(text: string): boolean {
  const source = restoreMathEscapes(text);
  if (latexHasStackedFrac(source) || NESTED_MATH_COMMAND_RE.test(source)) return true;
  return splitInlineMath(source).some(
    (part) => part.type === "math" && latexHasNestedMathView(part.value),
  );
}
