/**
 * Where the closed text of a streaming reply may be cut so each part is
 * preprocessed once.
 *
 * `preprocessMarkdown` is a chain of ~45 passes over the whole text. Run on a
 * growing reply each time a line closes, it does work that grows with the
 * square of the reply. Most passes read a line, its neighbours or one
 * paragraph, so the text splits into parts that preprocess the same apart as
 * together. A few passes read further, and a cut must not separate what they
 * read together:
 *
 * - fences, display maths, `\(…\)` and `\[…\]`: a cut lands outside them, and
 *   only between fences every pass reads alike (column 0, no nesting);
 * - code spans (`protectMathEscapes` pairs ticks across lines): every line's
 *   ticks pair on that line;
 * - a worked reply (`separateStandaloneBoldLines` reads a bold Given or Required
 *   label anywhere in the prose region to decide a law-name heading): no cut
 *   after one in its region, and one arriving after a bold label merges the
 *   region's parts back into one;
 * - an Answer heading looks ahead for its card (`attachAnswerHeadingToFence`),
 *   and a check section runs until a heading (`layoutCheckVerificationLines`);
 * - `<details>`, bare Vega JSON and molecule pairs are read across the whole
 *   reply: a reply with any of them is not cut at all.
 *
 * A cut that passes those guards is still checked: the open part and the text
 * after the cut must preprocess the same apart as together.
 */
import { isAnswerLang, isExplicitCodeLang } from "@/lib/copyBlock";
import { isMathFenceLang, isStructuredFenceLang } from "@/lib/fenceRegistry";
import { escapedAt } from "@/lib/markdown/inlineCode";
import { OPENING_HEADINGS } from "@/lib/markdown/workoutSection";

type OpenFence = { char: "`" | "~"; len: number; durable: boolean };

type SegmentHooks = {
  /** Preprocess the open part cut at `start` and compare; cut and return true when they agree. */
  tryCut: (start: number) => boolean;
  /** Merge the parts that start at or after `start` back into the open part; its new start. */
  rewind: (start: number) => number;
};

export type SegmentScanState = {
  /** Raw offset folded in so far, always a line start. */
  scannedLen: number;
  /** Where the open part begins: the last cut, or 0. */
  segmentStart: number;
  /** A construct some pass reads across the whole reply: no more cuts. */
  poisoned: boolean;
  fence: OpenFence | null;
  /** Where the prose region began: after the last fence no pass rewrites. */
  regionStart: number;
  /** The region has a bold Given or Required label… */
  regionWorked: boolean;
  /** …or a bold line over another line (a law-name heading, when worked). */
  regionLawHeading: boolean;
  /** Inside a "You can check" section (until a heading). */
  inCheck: boolean;
  /** Since the open part began: a line whose code ticks do not pair on it. */
  unpairedTicks: boolean;
  parenOpen: boolean;
  bracketOpen: boolean;
  /** Lines an Answer heading may still look down for its card (0 when none waits). */
  answerLookahead: number;
  /** The last non-blank line was a bold label. */
  prevBoldLabel: boolean;
  /** The last line was a list item or an indented line of one. */
  prevListLine: boolean;
  prevBlank: boolean;
  lastNonBlank: string;
};

/** An Answer heading looks up to 6 lines ahead for its card; keep a margin. */
const ANSWER_LOOKAHEAD_LINES = 12;
const POISON_RE = /<details|"\$schema"|molecule3d/i;
const CLEAN_FENCE_RE = /^(`{3,}|~{3,})([^`~]*)$/;
/** A line that opens with "Answer", or a heading a pass may break out of it. */
const ANSWER_HEADING_RE = /^[\s#*]*answer|#{1,6}[ \t]*(?:\*\*)?answer/i;
const WORKED_RE = new RegExp(String.raw`^\s*\*\*\s*(?:${OPENING_HEADINGS.join("|")})\b`);
const BOLD_LABEL_RE = /^\s*\*\*[^*\n]+\*\*\s*(?:`[^`\n]*`\s*)?$/;
/** A top-level list item: the passes read it apart from the item above it. */
const LIST_ITEM_RE = /^(?:[-*+]|\d{1,9}[.)])[ \t]/;
const INDENTED_RE = /^[ \t]+\S/;
/** Fences whose languages tables, prose and maths passes may unwrap or inline. */
const UNWRAPPED_CODE_LANGS = new Set(["markdown", "md", "table", "json"]);

export function emptySegmentScan(): SegmentScanState {
  return {
    scannedLen: 0,
    segmentStart: 0,
    poisoned: false,
    fence: null,
    regionStart: 0,
    regionWorked: false,
    regionLawHeading: false,
    inCheck: false,
    unpairedTicks: false,
    parenOpen: false,
    bracketOpen: false,
    answerLookahead: 0,
    prevBoldLabel: false,
    prevListLine: false,
    prevBlank: true,
    lastNonBlank: "",
  };
}

/** A fence every later pass keeps as a fence, so the prose before it is its own region. */
function isDurableFence(info: string): boolean {
  const lang = (info.trim().split(/\s/)[0] ?? "").toLowerCase();
  if (!lang || isMathFenceLang(lang)) return false;
  if (isAnswerLang(lang) || isStructuredFenceLang(lang)) return true;
  return isExplicitCodeLang(lang) && !UNWRAPPED_CODE_LANGS.has(lang);
}

/** Unescaped code tick runs on a line pair in order, each with one of its length. */
function ticksPairOnLine(line: string): boolean {
  let open = 0;
  for (let i = line.indexOf("`"); i >= 0; ) {
    let end = i + 1;
    while (line[end] === "`") end += 1;
    const escaped = escapedAt(line, i);
    if (!escaped) {
      if (open === 0) open = end - i;
      else if (open === end - i) open = 0;
      else return false;
    }
    i = line.indexOf("`", escaped ? i + 1 : end);
  }
  return open === 0;
}

/** Lazy pairing, as the display-maths regexes read it: an opener waits for the next closer. */
function pairLazily(line: string, open: boolean, opener: string, closer: string): boolean {
  let pending = open;
  for (let i = 0; i < line.length; ) {
    const next = pending ? line.indexOf(closer, i) : line.indexOf(opener, i);
    if (next < 0) break;
    pending = !pending;
    i = next + 2;
  }
  return pending;
}

/** A check section's label ("For x = 3:") holds its state over the blank lines after it. */
function endsWithCheckLabel(line: string): boolean {
  return /:\s*$/.test(line.replace(/[*$\s]+$/, ""));
}

/** Whether the guards allow a cut before `line`, given the state of the text above it. */
function guardsAllowCut(state: SegmentScanState, line: string): boolean {
  return (
    !state.poisoned &&
    state.fence === null &&
    (state.prevBlank || (state.prevListLine && LIST_ITEM_RE.test(line))) &&
    !state.regionWorked &&
    !state.inCheck &&
    !state.unpairedTicks &&
    !state.parenOpen &&
    !state.bracketOpen &&
    state.answerLookahead === 0 &&
    !endsWithCheckLabel(state.lastNonBlank)
  );
}

/** Fold a line that holds a fence marker; false for any other line. `next` is where the next line starts. */
function foldFenceLine(state: SegmentScanState, line: string, next: number): boolean {
  if (!line.includes("```") && !line.includes("~~~")) return false;
  const match = CLEAN_FENCE_RE.exec(line);
  if (!match) {
    state.poisoned = true;
    return true;
  }
  const marker = match[1]!;
  const info = match[2] ?? "";
  const char = marker[0] as "`" | "~";
  if (!state.fence) {
    state.fence = { char, len: marker.length, durable: isDurableFence(info) };
    return true;
  }
  if (char !== state.fence.char || marker.length < state.fence.len || info.trim()) {
    // A marker inside a fence body: the passes disagree about where it ends.
    state.poisoned = true;
    return true;
  }
  if (state.fence.durable) {
    state.regionStart = next;
    state.regionWorked = false;
    state.regionLawHeading = false;
  }
  state.fence = null;
  return true;
}

function foldProseLine(state: SegmentScanState, line: string, hooks: SegmentHooks): void {
  if (!ticksPairOnLine(line)) state.unpairedTicks = true;
  state.parenOpen = pairLazily(line, state.parenOpen, "\\(", "\\)");
  state.bracketOpen = pairLazily(line, state.bracketOpen, "\\[", "\\]");
  if (state.prevBoldLabel && !state.prevBlank) state.regionLawHeading = true;
  if (!WORKED_RE.test(line)) return;
  state.regionWorked = true;
  // Its bold labels were preprocessed as an unworked reply: preprocess them again.
  if (state.regionLawHeading && state.segmentStart > state.regionStart) {
    state.segmentStart = hooks.rewind(state.regionStart);
  }
}

/** Fold one complete raw line into the state. */
function foldLine(state: SegmentScanState, line: string, next: number, hooks: SegmentHooks): void {
  if (POISON_RE.test(line)) state.poisoned = true;
  const blank = line.trim() === "";
  const fenceLine = foldFenceLine(state, line, next);
  if (!fenceLine && !state.fence && !blank) foldProseLine(state, line, hooks);
  const compact = line.replace(/\*/g, "").trim().toLowerCase();
  if (compact.startsWith("you can check")) state.inCheck = true;
  else if (line.trim().startsWith("#")) state.inCheck = false;
  if (fenceLine) state.answerLookahead = 0;
  else if (!state.fence && ANSWER_HEADING_RE.test(line)) state.answerLookahead = ANSWER_LOOKAHEAD_LINES;
  else if (!blank) state.answerLookahead = Math.max(0, state.answerLookahead - 1);
  state.prevListLine =
    !blank && !fenceLine && !state.fence && (LIST_ITEM_RE.test(line) || INDENTED_RE.test(line));
  if (!blank) {
    state.prevBoldLabel = !state.fence && !fenceLine && BOLD_LABEL_RE.test(line);
    state.lastNonBlank = line;
  }
  state.prevBlank = blank;
}

/**
 * Whether `text` holds a line that changes how parts cut before it preprocess:
 * a bold Given or Required label (its region's parts merge back into one) or a
 * construct some pass reads across the whole reply.
 */
export function readsBackAcrossCuts(text: string): boolean {
  return text.split("\n").some((line) => WORKED_RE.test(line) || POISON_RE.test(line));
}

/** A new open part starts at `start`: what was read about the old one no longer applies. */
function startSegment(state: SegmentScanState, start: number): void {
  state.segmentStart = start;
  state.unpairedTicks = false;
}

/**
 * Fold the complete lines of `content` up to `stableLen` (a line start) into
 * `prev`, offering every allowed cut to `hooks.tryCut`. The text must only
 * have grown since `prev` was made.
 */
export function advanceSegmentScan(
  prev: SegmentScanState,
  content: string,
  stableLen: number,
  hooks: SegmentHooks,
): SegmentScanState {
  const state = { ...prev };
  let pos = state.scannedLen;
  while (pos < stableLen) {
    const nl = content.indexOf("\n", pos);
    if (nl < 0 || nl >= stableLen) break;
    const line = content.slice(pos, nl);
    if (line.trim() !== "" && pos > state.segmentStart && guardsAllowCut(state, line) && hooks.tryCut(pos)) {
      startSegment(state, pos);
    }
    foldLine(state, line, nl + 1, hooks);
    pos = nl + 1;
  }
  state.scannedLen = pos;
  return state;
}
