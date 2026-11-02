import {
  markdownHasNestedMathView,
  splitInlineMath,
  type InlineMathPart,
} from "@/lib/markdown/inlineMath";
import { isHeavyInlineMath } from "@/lib/math/fenceRetag";
import { latexHasNestedMathView, mathRunLineHeight } from "@/lib/math/text";

const TRAILING_CHECK_TICK_RE = /[ \t]*([✓✔✅])[ \t]*$/u;

/** Prose and inline math sharing a line, or one formula of its own (`at` is its part index). */
export type MathTextRun =
  | { type: "inline"; parts: InlineMathPart[] }
  | { type: "formula"; latex: string; at: number };

export type TextWithMathSegments = {
  /** The cleaned text; a prose-only run prints this, not its parts. */
  content: string;
  parts: InlineMathPart[];
  /** Line height of the Text runs, from the math drawn inside them; formulas hosted as Views size themselves. */
  runHeight: number | undefined;
  /**
   * prose: one Text of `content`. inline: one Text of `parts`. display: `runs` with each heavy
   * formula a display block. nested: `runs` with each nested-View formula outside Text.
   */
  layout: "prose" | "inline" | "display" | "nested";
  runs: MathTextRun[];
};

function replaceHtmlBreaks(text: string): string {
  return text.replace(/<br\s*\/?>/gi, "\n");
}

/** What closes on a formula: brackets and quotes, then punctuation (`).`, `,`, `”`). */
const FORMULA_TAIL_RE = /^[ \t]*([)\]”’»]*[,.;:!?]*)/;

/** Cuts `parts` at each formula `isFormula` picks; the closing marks right after one join it. */
function mathRuns(
  parts: InlineMathPart[],
  isFormula: (latex: string) => boolean,
  trimRemainder: boolean,
): MathTextRun[] {
  const runs: MathTextRun[] = [];
  let inline: InlineMathPart[] = [];
  const flushInline = () => {
    if (!inline.length) return;
    runs.push({ type: "inline", parts: inline });
    inline = [];
  };
  for (let i = 0; i < parts.length; i += 1) {
    const part = parts[i];
    if (part.type !== "math" || !isFormula(part.value)) {
      inline.push(part);
      continue;
    }
    flushInline();
    const next = parts[i + 1];
    const tail = next?.type === "text" ? FORMULA_TAIL_RE.exec(next.value) : null;
    const punctuationMatch = tail?.[1] ? tail : null;
    const punctuation = punctuationMatch?.[1] ?? "";
    runs.push({
      type: "formula",
      latex: part.value + (punctuation ? `\\text{${punctuation}}` : ""),
      at: i,
    });
    if (punctuationMatch && next?.type === "text") {
      // Keep punctuation with the formula even when the same text token
      // continues with prose (", then compare"), retaining that prose.
      const rest = next.value.slice(punctuationMatch[0].length);
      const remainder = trimRemainder ? rest.trimStart() : rest;
      if (remainder) inline.push({ type: "text", value: remainder });
      i += 1;
    }
  }
  flushInline();
  return runs;
}

/** A markdown text node's prose and math, and how its runs are hosted. */
export function segmentTextWithMath(text: string): TextWithMathSegments {
  // Strip standalone ":" lines — the model puts a colon on its own line as a
  // "leads to the next line" marker. It strands as a lone "two dots" between
  // a label and the formula on the next line. Drop it for all content, not
  // just nested-math paragraphs.
  let content = replaceHtmlBreaks(text)
    .split("\n")
    .filter((line) => line.trim() !== ":")
    .join("\n");
  // A stacked fraction/root is a native View rather than a text glyph. When
  // a verification tick follows it, iOS can wrap that tiny final Text onto a
  // detached line (or the far edge of the bubble). Put the status first for
  // tall math so it stays visibly attached while the equation may scroll.
  const trailingTick = TRAILING_CHECK_TICK_RE.exec(content);
  if (trailingTick) {
    const withoutTick = content.slice(0, trailingTick.index).trimEnd();
    if (markdownHasNestedMathView(withoutTick)) {
      content = `${trailingTick[1]} ${withoutTick}`;
    }
  }
  const parts = splitInlineMath(content);
  // A display formula or a math View sits outside the Text runs; only maths
  // drawn inside them may raise their line height, or every prose line of
  // the paragraph spreads to the tallest formula's height.
  const runHeight = parts.reduce<number | undefined>((acc, p) => {
    if (p.type !== "math" || isHeavyInlineMath(p.value) || latexHasNestedMathView(p.value)) return acc;
    const h = mathRunLineHeight(p.value);
    if (h == null) return acc;
    return acc == null ? h : Math.max(acc, h);
  }, undefined);
  const segments = { content, parts, runHeight };

  if (parts.length === 1 && parts[0].type === "text") {
    return { ...segments, layout: "prose", runs: [] };
  }
  if (parts.some((p) => p.type === "math" && isHeavyInlineMath(p.value))) {
    return { ...segments, layout: "display", runs: mathRuns(parts, isHeavyInlineMath, true) };
  }
  if (parts.some((p) => p.type === "math" && latexHasNestedMathView(p.value))) {
    // A trailing text part that is only a colon (e.g. "Use the product rule
    // $\sqrt{ab}=\sqrt{a}\sqrt{b}$:") strands onto its own line here: the math
    // is a nested View, so the ":" after it can't share its line box and
    // renders as a random lone "two dots" between the rule and the next
    // line. The colon is a "leads to the next line" marker that's redundant
    // once the next line follows — drop it so it doesn't strand.
    const trimmed = parts.filter((p, i) => {
      if (p.type !== "text") return true;
      // Only drop a trailing lone colon (the last part, possibly after a math View).
      if (i !== parts.length - 1) return true;
      return p.value.trim() !== ":";
    });
    return { ...segments, layout: "nested", runs: mathRuns(trimmed, latexHasNestedMathView, false) };
  }
  return { ...segments, layout: "inline", runs: [] };
}
