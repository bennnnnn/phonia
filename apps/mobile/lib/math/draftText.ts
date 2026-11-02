/**
 * What the composer's math preview draws, decided without React: whether a draft
 * or a sent message shows it, a run's label, and the size a script is drawn at.
 */
import { textLooksLikeMath } from "@/lib/math/composerIntent";
import type { DraftNode } from "@/lib/math/draftSlots";
import { SCRIPT_RATIO } from "@/lib/math/layout";
import { readableLatexFallback } from "@/lib/math/latexParse";
import { isMostlyProsePaste } from "@/lib/math/pasteNormalize";
import {
  NATIVE_LITERAL_LEFT_BRACE_MARKER,
  NATIVE_LITERAL_RIGHT_BRACE_MARKER,
} from "@/lib/math/textMarkers";

/**
 * True when the composer draft should show the live math preview.
 * Shows when the input contains `$` (explicit math delimiters) OR when it
 * looks like math content (LaTeX commands, math symbols, bare equations)
 * even without `$` — so typing `√9` or `x^2 = 4` shows the preview without
 * requiring the user to manually wrap in `$...$`.
 *
 * Note: `UserMessageContent` uses its own check (only `$`) for sent messages;
 * this broader check is for the live composer draft only.
 */
export function draftShowsMathPreview(input: string): boolean {
  const s = input.trim();
  if (s.length === 0) return false;
  // Commands between `$`s (`\partial`, `\nabla`) are math, not words: a row of
  // calculus keys read as prose, and the preview (and a sent bubble) went blank.
  if (s.includes("$") && !/[A-Za-z]{2,}/.test(proseOutsideMath(s))) return true;
  if (isMostlyProsePaste(s)) return false;
  if (input.includes("$")) return true;
  return textLooksLikeMath(input);
}

/**
 * True when a *sent* user message should render via `MathDraftPreview`.
 * Unlike the composer, sent messages only use the preview when the user
 * explicitly wrapped math in `$...$` — bare equations in sent messages
 * render through the normal markdown path (which handles implicit math).
 *
 * Multi-line / display-math pastes (`\[...\]`, `$$...$$`) must not use the
 * composer preview: wrapping them in one `$` row left a tall empty bubble.
 * A sentence that only contains an equation stays markdown, so the words
 * are not dropped and the bubble is not left as a dot.
 */
/** Words outside `$...$`. A question around an equation is a sentence. */
function proseOutsideMath(input: string): string {
  let out = "";
  let i = 0;
  while (i < input.length) {
    if (input[i] === "$") {
      const close = input.indexOf("$", i + 1);
      if (close > i) {
        i = close + 1;
        continue;
      }
    }
    out += input[i];
    i += 1;
  }
  return out;
}

export function sentMessageShowsMathPreview(input: string): boolean {
  const s = input.trim();
  if (!s.includes("$") || s.length === 0) return false;
  if (s.includes("\n")) return false;
  if (s.includes("\\[") || s.includes("\\]") || s.includes("$$")) return false;
  if (s.length > 160) return false;
  // The composer preview drops the words and the bubble collapses to a dot.
  if (/[A-Za-z]{2,}/.test(proseOutsideMath(s))) return false;
  return true;
}

// A command's argument (`\mathbb{N}`, `\mathrm{i}`) is read by MathText, braces and all.
const COMMAND_ARGUMENT = /\\[A-Za-z]+\{[^{}]*\}/g;

/** Drop TeX grouping braces, but keep `\{` and `\}` as the braces the user typed. */
function composerTextLabel(raw: string): string {
  let label = "";
  let last = 0;
  for (const found of raw.matchAll(COMMAND_ARGUMENT)) {
    label += dropGroupingBraces(raw.slice(last, found.index)) + found[0].replace(/\$/g, "");
    last = found.index + found[0].length;
  }
  return label + dropGroupingBraces(raw.slice(last));
}

function dropGroupingBraces(raw: string): string {
  return raw
    .replace(/\$/g, "")
    .replace(/\\\{/g, NATIVE_LITERAL_LEFT_BRACE_MARKER)
    .replace(/\\\}/g, NATIVE_LITERAL_RIGHT_BRACE_MARKER)
    .replace(/[{}]/g, "")
    .split(NATIVE_LITERAL_LEFT_BRACE_MARKER)
    .join("{")
    .split(NATIVE_LITERAL_RIGHT_BRACE_MARKER)
    .join("}");
}

/** The formula's text size. A script draws smaller, as MathText draws one in a reply. */
export const DRAFT_TEXT_SIZE = 16;
const MIN_SCRIPT_SIZE = 9;

export function scriptSize(size: number): number {
  return Math.max(MIN_SCRIPT_SIZE, Math.round(size * SCRIPT_RATIO));
}

/** Text between `$`s is math: a lone `x` is the italic variable, not prose. */
function insideInlineMath(input: string, index: number): boolean {
  let open = false;
  for (let i = 0; i < index; i += 1) {
    if (input[i] === "$" && input[i - 1] !== "\\") open = !open;
  }
  return open;
}

/** A run of draft text and whether it is math (between `$`s) or prose; `$` dropped. */
export function textRuns(input: string, start: number, end: number): { math: boolean; text: string }[] {
  const runs: { math: boolean; text: string }[] = [];
  let math = insideInlineMath(input, start);
  let from = start;
  for (let i = start; i <= end; i += 1) {
    if (i < end && !(input[i] === "$" && input[i - 1] !== "\\")) continue;
    const text = composerTextLabel(input.slice(from, i));
    if (text) runs.push({ math: math && text.trim().length > 0, text });
    math = !math;
    from = i + 1;
  }
  return runs;
}

/** What a screen reader says for a sent math message: its prose, and its maths as words. */
export function spokenDraft(input: string): string {
  return textRuns(input, 0, input.length)
    .map((run) => (run.math ? readableLatexFallback(run.text) : run.text))
    .join("")
    .replace(/\s+/g, " ")
    .trim();
}

type TextNode = Extract<DraftNode, { kind: "text" }>;

/**
 * A run ending in ∫, ∑, ∏ or lim, split at that operator: the text before it is
 * drawn as text, so `$\\int $ $\\int_{a}^{b}$` keeps its first ∫. The operator starts at
 * the run's last backslash (the caller has matched it at the end).
 */
export function splitBeforeOperator(input: string, run: TextNode): { lead: TextNode | null; operator: TextNode } {
  const at = run.start + input.slice(run.start, run.end).lastIndexOf("\\");
  const lead = input.slice(run.start, at).replace(/[$\s]/g, "") ? { ...run, end: at } : null;
  return { lead, operator: { ...run, start: at } };
}
