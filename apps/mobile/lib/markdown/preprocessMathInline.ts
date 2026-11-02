import { readInlineCodeSpan } from "@/lib/markdown/inlineCode";
import { readInlineMathSpan, splitInlineMath } from "@/lib/markdown/inlineMath";
import {
  PROTECTED_ESCAPE_MARKER,
  PROTECTED_LITERAL_DOLLAR,
  PROTECTED_MATH_APOSTROPHE_MARKER,
  PROTECTED_MATH_STAR_MARKER,
  PROTECTED_MATH_UNDERSCORE_MARKER,
} from "@/lib/math/text";
import { applyOutsideFences } from "@/lib/mdFenceScan";

// A backslash immediately followed by an ASCII punctuation character —
// CommonMark's own escapable set (matches markdown-it's rules_inline/escape.mjs).
const MATH_ESCAPE_BACKSLASH_RE = /\\(?=[!"#$%&'()*+,\-./:;<=>?@[\]^_`{|}~])/g;

/**
 * Protect punctuation-led LaTeX commands (`\,` `\;` `\!` `\%` `\_` `\{` `\}` …)
 * inside `$...$` / `\(...\)` math from markdown-it's own CommonMark
 * backslash-escape rule, which runs during inline tokenization and silently
 * drops the backslash before splitInlineMath/MathText ever see the text —
 * e.g. `\,` (an invisible thin space) survives preprocessMarkdown intact but
 * renders as a bare, visible "," once markdown-it has tokenized it. Letter-led
 * commands (`\int`, `\frac`, `\sqrt`, …) are unaffected — letters aren't in
 * CommonMark's escapable set — so this only needs to touch the backslash
 * itself, and only inside math spans (fenced ```math bodies are already
 * exempt: markdown-it's fence rule never applies inline escaping to them).
 * lib/math/latexPreprocess.ts's preprocessLatex decodes the marker back to "\" as its first
 * step, before any command table runs.
 *
 * Also converts `\(...\)` → `$...$`. CommonMark treats `\(` / `\)` as escaped
 * punctuation and strips those backslashes during inline tokenization, so
 * leaving `\(...\)` in the preprocessed string makes splitInlineMath miss the
 * span entirely and the UI shows raw `(\frac{...})`. `$` is not escapable that
 * way, and splitInlineMath already handles `$...$`.
 *
 * Bare `_` and `*` inside the same spans are swapped for PUA markers so
 * markdown-it's emphasis tokenizer cannot turn `$x_1 * y_2$` into nested
 * em/strong. Apostrophes are protected from smartquotes in the same spans.
 * lib/math/latexPreprocess.ts restores the original source before math parsing.
 */
export function protectMathEscapes(content: string): string {
  return applyOutsideFences(content, (prose) => {
    let out = "";
    for (let i = 0; i < prose.length;) {
      if (prose[i] === "\\" && prose[i + 1] !== "(") {
        // Escaped ticks/dollars cannot open code/math. Copy slash pairs too,
        // so a tick after an even number of backslashes stays unescaped.
        out += prose.slice(i, i + 2);
        i += 2;
        continue;
      }
      if (prose[i] === "`") {
        let openerEnd = i + 1;
        while (prose[openerEnd] === "`") openerEnd += 1;
        const ticks = prose.slice(i, openerEnd);
        const end = prose.indexOf(ticks, openerEnd);
        const next = end < 0 ? openerEnd : end + ticks.length;
        out += prose.slice(i, next);
        i = next;
        continue;
      }
      const span = readInlineMathSpan(prose, i);
      if (!span) {
        out += prose[i];
        i += 1;
        continue;
      }
      const delimiterLength = prose[i] === "$" ? 1 : 2;
      const rawBody = prose.slice(i + delimiterLength, span.end - delimiterLength);
      // Explicit \(...\) may span source lines. Single-dollar inline math
      // cannot: keep its body in one Markdown token, retaining TeX \\ rows.
      const inlineBody = rawBody.includes("\n")
        ? rawBody.split(/\r?\n/).map((line) => line.trim()).join(" ")
        : rawBody;
      const body = inlineBody
        // Preserve LaTeX row separators before CommonMark can consume them.
        .split("\\\\")
        .join(`${PROTECTED_ESCAPE_MARKER}${PROTECTED_ESCAPE_MARKER}`)
        // `\$` is one dollar sign. A backslash marker plus a leftover `$`
        // is a new closer, so `$\$1,505$` renders as `\1,505$`.
        .split("\\$")
        .join(PROTECTED_LITERAL_DOLLAR)
        .replace(MATH_ESCAPE_BACKSLASH_RE, PROTECTED_ESCAPE_MARKER)
        .replace(/_/g, PROTECTED_MATH_UNDERSCORE_MARKER)
        .replace(/\*/g, PROTECTED_MATH_STAR_MARKER)
        .replace(/'/g, PROTECTED_MATH_APOSTROPHE_MARKER);
      out += `$${body}$`;
      i = span.end;
    }
    return out;
  });
}

/** The `$` closing a pair that opens at `open`, and whether a complete code
 * span sits inside the pair. Code spans are skipped whole. */
function dollarCloser(line: string, open: number): { close: number; code: boolean } | null {
  let code = false;
  for (let j = open + 1; j < line.length;) {
    if (line[j] === "\\") {
      j += 2;
      continue;
    }
    const codeEnd = line[j] === "`" ? readInlineCodeSpan(line, j) : null;
    if (codeEnd != null) {
      code = true;
      j = codeEnd;
      continue;
    }
    if (line[j] === "$") return line[j + 1] === "$" ? null : { close: j, code };
    j += 1;
  }
  return null;
}

function unwrapDollarsAroundCodeLine(line: string): string {
  if (!line.includes("$") || !line.includes("`")) return line;
  let out = "";
  for (let i = 0; i < line.length;) {
    if (line[i] === "\\") {
      out += line.slice(i, i + 2);
      i += 2;
      continue;
    }
    if (line[i] === "`") {
      let runEnd = i + 1;
      while (line[runEnd] === "`") runEnd += 1;
      const end = readInlineCodeSpan(line, i) ?? runEnd;
      out += line.slice(i, end);
      i = end;
      continue;
    }
    const pair = line[i] === "$" && line[i + 1] !== "$" && line[i - 1] !== "$"
      ? dollarCloser(line, i)
      : null;
    if (!pair) {
      out += line[i];
      i += 1;
    } else if (!pair.code) {
      // Ordinary maths, or two prices: copy the pair whole so its closer is
      // never read as an opener.
      out += line.slice(i, pair.close + 1);
      i = pair.close + 1;
    } else if (line[i + 1] === "`" || line[pair.close - 1] === "`") {
      out += line.slice(i + 1, pair.close).trim();
      i = pair.close + 1;
    } else {
      out += line[i];
      i += 1;
    }
  }
  return out;
}

/**
 * Code wrapped in maths dollars: "$" + "`total`" + "$", or "$" + "`total` + 2"
 * + "$". markdown-it reads the code span first, so the dollars would paint as
 * two stray `$` around it. Drop them when a code span touches one of them; a
 * price on each side ("$5 and `total` is $3") keeps both.
 */
export function unwrapDollarsAroundCode(content: string): string {
  return applyOutsideFences(content, (prose) =>
    prose.split("\n").map(unwrapDollarsAroundCodeLine).join("\n"),
  );
}

/** Consecutive calculation lines are separate steps, not wrapped prose.
 * Run after math-code unwrapping; complete fences and inline formula bodies
 * keep their own line semantics. */
export function separateConsecutiveMathLines(content: string): string {
  return applyOutsideFences(content, (prose) => {
    const lines = prose.split("\n");
    let previousIsMath = false;
    for (let i = 0; i < lines.length; i += 1) {
      const trimmed = lines[i].trim();
      const span = readInlineMathSpan(trimmed, 0);
      const isMath = span != null && span.end === trimmed.length;
      if (previousIsMath && isMath) lines[i - 1] = `${lines[i - 1].trimEnd()}  `;
      previousIsMath = isMath;
    }
    return lines.join("\n");
  });
}

/** `\$1,505$` is a currency amount with a stray closer, not math `1,505`.
 * Leave `$\$1,505$` alone: that span already keeps the dollar. So does
 * `$\$80 \times 7 = \$560$`, whose last `$` closes the span opened before. */
export function revealCurrencyDollars(text: string): string {
  return text.replace(
    /\\\$(\d[\d,]*(?:\.\d+)?)\$/g,
    (match, amount: string, offset: number, source: string) =>
      source[offset - 1] === "$" || opensBefore(source, offset) ? match : `$${amount}`,
  );
}

/** True when `at` lies inside a formula the renderer reads, opened earlier on
 * the line. A dollar it pairs with nothing ("$5 and") opens nothing. */
function opensBefore(text: string, at: number): boolean {
  for (let i = text.lastIndexOf("\n", at) + 1; i < at; i += 1) {
    if (text[i] === "\\") {
      i += 1;
      continue;
    }
    const span = text[i] === "$" ? readInlineMathSpan(text, i) : null;
    if (span == null) continue;
    if (span.end > at) return true;
    i = span.end - 1;
  }
  return false;
}

/** Move $...$ out of **...** so emphasis nodes do not swallow math delimiters.

 * Keep the original span when math sits in the *middle* of the bold (text
 * both before and after) — e.g. ``**Slope ($m$):** 3``. Unwrapping that
 * produces ``**Slope (**$m$**):**`` which markdown-it splits into three
 * inline nodes; in a list item those stack vertically as
 * "Slope (" / "m" / "): 3" — the colon-on-its-own-line the user keeps
 * seeing. Trailing-formula bold (``**Answer: $x = 2$**``) still unwraps.
 */
export function normalizeBoldInlineMath(content: string): string {
  return content.replace(/\*\*((?:(?!\*\*).)+)\*\*/g, (full, inner: string) => {
    if (!/\$[^$\n]+?\$/.test(inner)) return full;
    // A numbered step label (`**1. Power rule on $x^3$**`) keeps its maths: the
    // lesson-step renderer draws it, and unwrapping it drops the step badge.
    if (/^\d+\.\s/.test(inner)) return full;
    const parts = splitInlineMath(inner);
    if (!parts.some((part) => part.type === "math")) return full;

    const first = parts[0];
    const last = parts[parts.length - 1];
    if (
      first &&
      last &&
      first.type === "text" &&
      last.type === "text" &&
      first.value.trim() !== "" &&
      last.value.trim() !== ""
    ) {
      return full;
    }

    let out = "";
    for (const part of parts) {
      if (part.type === "math") {
        out += `$${part.value}$`;
        continue;
      }
      const lead = part.value.match(/^\s+/)?.[0] ?? "";
      const trail = part.value.match(/\s+$/)?.[0] ?? "";
      const core = part.value.trim();
      if (core) out += `${lead}**${core}**${trail}`;
      else out += part.value;
    }
    return out.trim() ? out : full;
  });
}
