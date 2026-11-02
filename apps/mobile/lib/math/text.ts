/** Parse simple LaTeX into native Text segments (no WebView). */

import { parseSimpleLatex } from "@/lib/math/latexParse";
import { restoreMathEscapes } from "@/lib/math/textMarkers";
import type { MathSegment } from "@/lib/math/textTypes";

export type { MathAccentKind, MathSegment } from "@/lib/math/textTypes";
export {
  PROTECTED_ESCAPE_MARKER,
  PROTECTED_LITERAL_DOLLAR,
  PROTECTED_MATH_APOSTROPHE_MARKER,
  PROTECTED_MATH_STAR_MARKER,
  PROTECTED_MATH_UNDERSCORE_MARKER,
  restoreMathEscapes,
} from "@/lib/math/textMarkers";
export {
  DEGREE_RING,
  parseSimpleLatex,
  readableLatexFallback,
  segmentsToPlain,
} from "@/lib/math/latexParse";

/**
 * Stacked frac/sqrt need a taller parent `lineHeight` than body prose (16/23).
 * Nested RN Text often keeps the outer line box, so the vinculum kisses the
 * line above unless both MathText and the wrapping markdown Text use this.
 * The math view sizes itself from the layout tree. This floor is only the
 * markdown line box beside a stacked atom.
 */
export const MATH_TALL_LINE_HEIGHT = 46;
/** Superscripts (`a^2`, a²) need more leading than body 23 or they clip the line above. */
export const MATH_SCRIPT_LINE_HEIGHT = 34;

/** True when native/inline layout must leave room above/below the run. */
export function latexNeedsTallLine(latex: string): boolean {
  return /\\(?:d|t|c)?frac|\\sqrt/.test(restoreMathEscapes(latex));
}

/** LaTeX superscript/subscript only — Unicode ² / CO₂ in prose must not inflate the paragraph. */
const SUPER_OR_SUB_RE = /\^|_\{/;

/** Line height the wrapping markdown Text must use so math doesn't overlap neighbors. */
export function mathRunLineHeight(latex: string): number | undefined {
  if (latexNeedsTallLine(latex)) {
    // Never shrink below MATH_TALL_LINE_HEIGHT for a stacked frac/sqrt.
    // Passing the whole paragraph (prose + `$...$`) used to trip
    // `length > 48` / multi-stack and return 34, which clips the 40px
    // numerator ("the above numbers can't be seen").
    return MATH_TALL_LINE_HEIGHT;
  }
  if (SUPER_OR_SUB_RE.test(restoreMathEscapes(latex))) return MATH_SCRIPT_LINE_HEIGHT;
  return undefined;
}

/**
 * Stacked `\\frac` / `\\sqrt` is a nested View. Inside a paragraph `Text`
 * that View gets a zero-size text attachment on iOS and paints over
 * neighboring words (the "smudged" line) unless it leaves the text run.
 */
export function latexHasStackedFrac(latex: string): boolean {
  return /\\(?:d|t|c)?frac/.test(restoreMathEscapes(latex));
}

type ScriptAttachment = {
  segment: MathSegment;
  index: number;
  sup: Extract<MathSegment, { type: "sup" }> | null;
  sub: Extract<MathSegment, { type: "sub" }> | null;
};

/** A base with both a superscript and a subscript is one script column.
 * A lone script stays attached to the text run so it can live inside Text. */
export function attachScripts(segments: MathSegment[]): ScriptAttachment[] {
  const out: ScriptAttachment[] = [];
  for (let i = 0; i < segments.length; i += 1) {
    const segment = segments[i];
    if (!segment) continue;
    if (segment.type === "sup" || segment.type === "sub") {
      out.push({ segment, index: i, sup: null, sub: null });
      continue;
    }
    let sup: ScriptAttachment["sup"] = null;
    let sub: ScriptAttachment["sub"] = null;
    let j = i + 1;
    while (j < segments.length) {
      const next = segments[j];
      if (next?.type === "sup" && !sup) sup = next;
      else if (next?.type === "sub" && !sub) sub = next;
      else break;
      j += 1;
    }
    if (sup && sub) {
      out.push({ segment, index: i, sup, sub });
      i = j - 1;
    } else {
      out.push({ segment, index: i, sup: null, sub: null });
    }
  }
  return out;
}

export function latexHasNestedMathView(latex: string): boolean {
  const source = restoreMathEscapes(latex);
  if (
    latexHasStackedFrac(source)
    || /\\(?:sqrt|xcancel|bcancel|cancel|overline|underline|widehat|widetilde|overrightarrow|overleftarrow|hat|vec|bar|ddot|dot|tilde)(?![A-Za-z])|\^\{[^{}]*\/[^{}]*\}/.test(
      source,
    )
  ) {
    return true;
  }
  // Superscripts and subscripts shift with translateY. That shift is ignored
  // on a Text nested in Text, so the host has to be a View or `x^2` draws as x2.
  return parseSimpleLatex(source).some((seg) => seg.type === "sup" || seg.type === "sub");
}

/**
 * Split a math fence body into individual display lines. A single
 * `renderToString`/parse call on a multi-line body concatenates every line
 * into one expression with no separator (no `\n` handling in LaTeX or in
 * our simple parser) — e.g. "x^2 = 5 - 1\nx^2 = 4" renders as the
 * nonsensical "x^2 = 5 - 1x^2 = 4". Each line must be rendered as its own
 * block instead.
 */
export function splitMathLines(latex: string): string[] {
  // A multi-line LaTeX environment (\begin{aligned}…\end{aligned}, cases,
  // matrix, gather, …) uses newlines BETWEEN its rows and MUST render as one
  // block — splitting it makes each row a standalone KaTeX parse that errors
  // or renders garbage. So if the body contains any \begin{…}, don't split.
  if (/\\begin\{[\w*]+\}/.test(latex)) {
    return [latex.trim()].filter(Boolean);
  }
  return latex
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

