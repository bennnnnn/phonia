/**
 * Reading a streaming reply's prepared text line by line for the places a
 * chunk may end (`streamBlocks.ts`): fences, display maths, blank runs, the
 * open list, and what stops every cut.
 */
import {
  CONTINUATION_LINE_RE,
  listItemCut,
  type OpenList,
} from "@/lib/markdown/streamListCuts";
import { fenceAfterLine, type OpenFence } from "@/lib/mdFenceScan";

/** A link reference definition the reply holds, and where. */
export type Definition = { at: number; line: string };

/** Group small blocks together so long replies don't spawn hundreds of renderers. */
export const MIN_SETTLED_CHUNK_CHARS = 320;

const LIST_LINE_RE = /^ {0,3}(?:[-*+]|\d{1,9}[.)])(?:\s|$)/;
const TABLE_LINE_RE = /^ {0,3}\|/;
const QUOTE_LINE_RE = /^ {0,3}>/;
const REFERENCE_DEFINITION_RE = /^ {0,3}\[[^\]\n]+\]:/;

function isBlankLine(line: string): boolean {
  return line.trim().length === 0;
}

/**
 * Lines that glue to their neighbours across blank lines: cutting before them
 * would split a list, table or quote, or detach a list continuation into a
 * separate parse. (Between two items of one list is the one exception; see
 * `listItemCut`.)
 */
function isGlueyLine(line: string): boolean {
  return (
    LIST_LINE_RE.test(line) ||
    TABLE_LINE_RE.test(line) ||
    QUOTE_LINE_RE.test(line) ||
    CONTINUATION_LINE_RE.test(line)
  );
}

function countDoubleDollar(line: string): number {
  let count = 0;
  let idx = 0;
  while ((idx = line.indexOf("$$", idx)) !== -1) {
    count += 1;
    idx += 2;
  }
  return count;
}

/** Where the scan stands: inside a fence or `$$` math, and what the last lines allow. */
type ScanState = {
  /** Tracked open and closed, as `scanFences` reads fences: a ``` inside ~~~ is content. */
  openFence: OpenFence | null;
  mathOpen: boolean;
  prevLineSafe: boolean;
  inBlankRun: boolean;
  list: OpenList | null;
  /**
   * A closed rich block (fenced code, ```math, or $$ display math) is cut into its
   * own once-mounted chunk at the next safe boundary, whatever its size, rather than
   * waiting for MIN_SETTLED_CHUNK_CHARS like prose. The pending segment re-parses on
   * every flush (react-native-markdown-display re-keys its output per parse, as
   * `streamBlocks.ts` says), so a short step-by-step maths reply whose closed blocks
   * waited there would unmount and remount every KaTeX WebView on every flush: a
   * blank-then-repaint flicker.
   */
  hasRichBlockSinceChunkStart: boolean;
};

/**
 * Track one line that a fence, `$$` math or a blank run accounts for, and
 * say so; a plain prose line (false) is where a cut may land.
 */
function trackBlockLine(state: ScanState, line: string): boolean {
  const before = state.openFence;
  state.openFence = fenceAfterLine(before, line);
  if (before != null && state.openFence != null) {
    state.inBlankRun = false;
    return true;
  }
  if (before != null || state.openFence != null) {
    // The fence's opener or its closer.
    state.prevLineSafe = state.openFence == null;
    state.inBlankRun = false;
    state.hasRichBlockSinceChunkStart = true;
    state.list = null;
    return true;
  }

  const dollarCount = countDoubleDollar(line);
  if (dollarCount % 2 === 1) {
    state.mathOpen = !state.mathOpen;
    state.prevLineSafe = !state.mathOpen;
    state.inBlankRun = false;
    state.hasRichBlockSinceChunkStart = true;
    if (!CONTINUATION_LINE_RE.test(line)) state.list = null;
    return true;
  }
  if (state.mathOpen) {
    state.inBlankRun = false;
    return true;
  }
  if (dollarCount > 0) {
    // Even, nonzero count while not already inside an open block: one or
    // more complete, self-contained "$$...$$" spans on a single line (no
    // mathOpen state change) — an odd-count line above already covers the
    // multi-line open/close case; this covers the single-line one. Defer
    // to the next safe boundary like the fence/odd-count branches above
    // (instead of falling through to the cut-check below) so the cut
    // lands after this line, not at its start — the cut-check uses the
    // current line's start, so evaluating it on this same line would
    // slice the chunk right before the $$ content it's meant to include.
    state.prevLineSafe = true;
    state.inBlankRun = false;
    state.hasRichBlockSinceChunkStart = true;
    if (!CONTINUATION_LINE_RE.test(line)) state.list = null;
    return true;
  }

  if (isBlankLine(line)) {
    state.inBlankRun = true;
    return true;
  }
  return false;
}

export type Cut = { at: number; continued: boolean; listAfter: OpenList | null };

type Scan = {
  cuts: Cut[];
  /** A link reference definition the scan read: no cut may stand. */
  definition: Definition | null;
  /** The list open where the scan began (the last chunk goes on in it) reached 100. */
  inheritedWide: boolean;
};

/**
 * The cut points in `prepared` between `from` and `cutEnd`, at whole lines
 * only. A cut lands at the start of a prose line that follows a blank run,
 * when the line before the blank run may end a chunk and the line does not
 * glue to what came before; or before the next item of the open list. Either
 * needs the pending chunk to be long enough or to hold a closed rich block.
 * `from` is a chunk boundary, so every fence and `$$` block starts closed,
 * and `list` is the list open there.
 *
 * The text after `cutEnd` (to `readEnd`, its last line too, however far it
 * has come) is read but never cut: a link reference definition there, or a
 * numbered list reaching 100, still takes back the cuts it changes. A cut
 * inside a numbered list stands only while the list stays under 100: one
 * that reaches it is drawn wider than its pieces were.
 */
export function scanClosedBlocks(
  prepared: string,
  from: number,
  cutEnd: number,
  list: OpenList | null,
  readEnd = cutEnd,
): Scan {
  const inherited = list ? { ...list } : null;
  const cuts: Cut[] = [];
  let pending: Cut[] = [];
  let pendingList: OpenList | null = null;
  let inheritedWide = false;
  const state: ScanState = {
    openFence: null,
    mathOpen: false,
    prevLineSafe: false,
    inBlankRun: false,
    list: inherited,
    hasRichBlockSinceChunkStart: false,
  };
  let chunkStart = from;
  let committedAt = from;
  /** The numbered list the pending cuts are in ended (they stand) or went wide (they go). */
  const settlePending = () => {
    if (pendingList && !pendingList.wide) {
      cuts.push(...pending);
      committedAt = chunkStart;
    } else if (pending.length > 0) {
      chunkStart = committedAt;
    }
    pending = [];
    pendingList = null;
  };
  let i = from;
  while (i < readEnd) {
    let nl = prepared.indexOf("\n", i);
    if (nl === -1 || nl >= readEnd) nl = readEnd;
    // Past `cutEnd`, or a line not yet closed within it: read, never cut.
    const readOnly = nl >= cutEnd;
    if (readOnly && readEnd === cutEnd) break;
    const line = prepared.slice(i, nl);
    if (!trackBlockLine(state, line)) {
      if (REFERENCE_DEFINITION_RE.test(line)) {
        return { cuts: [], definition: { at: i, line }, inheritedWide: false };
      }
      const listBefore = state.list ? { ...state.list } : null;
      const nextItem = listItemCut(state, line);
      if (inherited?.wide) inheritedWide = true;
      if (pendingList && (state.list !== pendingList || pendingList.wide)) settlePending();
      const longEnough =
        i - chunkStart >= MIN_SETTLED_CHUNK_CHARS || state.hasRichBlockSinceChunkStart;
      const afterBlock = state.inBlankRun && state.prevLineSafe && !isGlueyLine(line);
      if (!readOnly && longEnough && i > chunkStart && (afterBlock || nextItem)) {
        const cut = { at: i, continued: nextItem, listAfter: nextItem ? listBefore : null };
        if (nextItem && state.list?.next != null) {
          pending.push(cut);
          pendingList = state.list;
        } else {
          settlePending();
          cuts.push(cut);
          committedAt = i;
        }
        chunkStart = i;
        state.hasRichBlockSinceChunkStart = false;
      }
      state.inBlankRun = false;
      state.prevLineSafe = true;
    } else if (pendingList && state.list !== pendingList) {
      settlePending();
    }
    i = nl + 1;
  }
  settlePending();
  return { cuts, definition: null, inheritedWide };
}
