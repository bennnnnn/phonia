/** Dollar signs in prose that the implicit-maths passes must not take for
 * maths delimiters: currency, and the pairs that are already maths. */

import { codeSpanOpensWithin, escapedAt, readInlineCodeSpan } from "@/lib/markdown/inlineCode";
import { readInlineMathSpan } from "@/lib/markdown/inlineMath";
import { LATEX_SYMBOLS } from "@/lib/math/latexSymbols.generated";

const AMOUNT_AT = /\$[ \t]?\d/y;

/** An unescaped `$` at `i` with an amount after it: "$80", "$ 19.20". */
export function currencyDollarAt(text: string, i: number): boolean {
  AMOUNT_AT.lastIndex = i;
  return AMOUNT_AT.test(text) && !escapedAt(text, i);
}

/** The currency `$` whose amount ends just before `at` ("$1,200.50", "$ 80"),
 * or -1. */
export function priceDollarBefore(text: string, at: number): number {
  let amount = at;
  while (amount > 0 && /[\d,.]/.test(text[amount - 1] ?? "")) amount -= 1;
  if (/[ \t]/.test(text[amount - 1] ?? "") && text[amount - 2] === "$") amount -= 1;
  return amount > 0 && currencyDollarAt(text, amount - 1) ? amount - 1 : -1;
}

/** A price's arithmetic written with operator commands, as text:
 * "80 \times 7 =" reads "80 × 7 =". Null when it holds more than symbols
 * (`\frac{1}{2}`, a script, a spacing command). */
export function priceSymbolsAsText(island: string): string | null {
  if (/[\^_{}]|\\[^A-Za-z]/.test(island)) return null;
  let plain = true;
  const text = island.replace(/\\([A-Za-z]+)/g, (command, name: string) => {
    const glyph = LATEX_SYMBOLS[name];
    if (glyph == null) plain = false;
    return glyph ?? command;
  });
  return plain ? text : null;
}

/** End of the `$...$` pair opening at `open`, or null: the next unescaped
 * `$` on the line that no code span sits before. */
function plainPairEnd(line: string, open: number): number | null {
  let close = open + 1;
  while (close < line.length && line[close] !== "\n" && (line[close] !== "$" || escapedAt(line, close))) {
    close += 1;
  }
  if (line[close] !== "$" || codeSpanOpensWithin(line, open + 1, close)) return null;
  return close + 1;
}

/** Apply `fn` only to the non-`$...$` segments of a line, leaving already-
 * delimited inline math spans untouched. Without this, a heuristic like
 * MATH_IN_PARENS_RE re-wraps parentheticals INSIDE an existing `$...$`
 * (e.g. `$(-2 + \sqrt{3})^2 + 4(-2 + \sqrt{3}) + ...$`), producing `$$` and
 * shattering `$` pairing across the whole message — leaving `\sqrt` as raw
 * text and gluing adjacent prose into the math. Inline code spans are left
 * untouched the same way (`range(n_items)` is not `range($n_items$)`), and a
 * dollar pair never reaches across one.
 *
 * A pair is the renderer's (`readInlineMathSpan`). A currency `$` the
 * renderer pairs with nothing stays prose, so "$5, and $4! = 24$" holds one
 * formula. Any other pair it refuses (`$\frac{1}{2}$3`) is still kept whole:
 * wrapping its TeX again would print `$$`. */
export function applyOutsideInlineMath(line: string, fn: (s: string) => string): string {
  const out: string[] = [];
  let last = 0;
  let i = 0;
  while (i < line.length) {
    const codeEnd = line[i] === "`" ? readInlineCodeSpan(line, i) : null;
    if (codeEnd != null) {
      if (i > last) out.push(fn(line.slice(last, i)));
      out.push(line.slice(i, codeEnd));
      last = codeEnd;
      i = codeEnd;
      continue;
    }
    // `\$` is a currency sign. Closing on that `$` keeps only `$\$`, and
    // wrapping the rest inserts another `$`. `\$$` then becomes a math
    // fence, which is why the screen shows `\43` and `\1,720`.
    const displayDollar = line[i + 1] === "$" || (line[i - 1] === "$" && !escapedAt(line, i - 1));
    if (line[i] !== "$" || escapedAt(line, i) || displayDollar) {
      i += 1;
      continue;
    }
    const end = readInlineMathSpan(line, i)?.end
      ?? (currencyDollarAt(line, i) ? null : plainPairEnd(line, i));
    if (end == null) {
      i += 1;
      continue;
    }
    if (i > last) out.push(fn(line.slice(last, i)));
    out.push(line.slice(i, end));
    last = end;
    i = last;
  }
  if (last === 0) return fn(line);
  if (last < line.length) out.push(fn(line.slice(last)));
  return out.join("");
}
