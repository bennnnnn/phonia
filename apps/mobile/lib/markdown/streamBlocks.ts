/**
 * Append-only chunking of streaming markdown so settled text parses once.
 *
 * The streaming renderer re-parsed the whole reply on every flush and
 * react-native-markdown-display regenerates node keys per parse, so the
 * entire message subtree remounted every time — jankier the longer the
 * reply. Splitting the prepared text into settled chunks (each rendered by
 * its own memoized `<Markdown>`) plus a small growing tail keeps per-flush
 * work proportional to the tail, ChatGPT-style.
 *
 * Chunks only ever append while the same reply streams; each chunk's string
 * never changes, so its parse/render is done exactly once.
 */

import { listGoesOn, type OpenList } from "@/lib/markdown/streamListCuts";
import {
  MIN_SETTLED_CHUNK_CHARS,
  scanClosedBlocks,
  type Cut,
  type Definition,
} from "@/lib/markdown/streamBlockScan";

export type { OpenList } from "@/lib/markdown/streamListCuts";
export { MIN_SETTLED_CHUNK_CHARS };

export type StreamBlocksState = {
  /** Settled chunks; their concatenation is exactly `settledText`. */
  chunks: string[];
  /**
   * Per chunk: it ends between two items of one list, so its last list
   * continues in the next chunk and is drawn without a list's end (see
   * `markdownRenderRules`).
   */
  continued: boolean[];
  /** Per chunk: the list still open where it ends. */
  listAfter: (OpenList | null)[];
  /** Prefix of the prepared streaming text covered by `chunks`. */
  settledText: string;
  /**
   * A link reference definition (`[1]: https://…`) the reply holds, and
   * where. A reference resolves only in the piece its definition is in, so a
   * reply with one is drawn in one piece.
   */
  definition: Definition | null;
};

export function emptyStreamBlocksState(): StreamBlocksState {
  return { chunks: [], continued: [], listAfter: [], settledText: "", definition: null };
}

/** Append the chunks between consecutive cuts to the settled state. */
function cutChunks(base: StreamBlocksState, prepared: string, cuts: Cut[]): StreamBlocksState {
  const chunks = base.chunks.slice();
  const continued = base.continued.slice();
  const listAfter = base.listAfter.slice();
  let settledText = base.settledText;
  let chunkStart = settledText.length;
  for (const cut of cuts) {
    const chunk = prepared.slice(chunkStart, cut.at);
    chunks.push(chunk);
    continued.push(cut.continued);
    // The list this chunk leaves open is the one the next chunk starts in.
    listAfter.push(cut.listAfter);
    settledText += chunk;
    chunkStart = cut.at;
  }
  return { chunks, continued, listAfter, settledText, definition: null };
}

/** `state` without its last chunks that end inside a list: the list is cut again whole. */
function withoutOpenListChunks(state: StreamBlocksState): StreamBlocksState {
  let keep = state.chunks.length;
  while (keep > 0 && state.continued[keep - 1]) keep -= 1;
  return trimmedTo(state, keep);
}

function trimmedTo(state: StreamBlocksState, keep: number): StreamBlocksState {
  if (keep === state.chunks.length) return state;
  const length = state.chunks.slice(0, keep).reduce((sum, chunk) => sum + chunk.length, 0);
  return {
    chunks: state.chunks.slice(0, keep),
    continued: state.continued.slice(0, keep),
    listAfter: state.listAfter.slice(0, keep),
    settledText: state.settledText.slice(0, length),
    definition: null,
  };
}

/** The reply still holds the definition `state` found, where it was. */
function holdsDefinition(state: StreamBlocksState, prepared: string): boolean {
  return state.definition !== null && prepared.startsWith(state.definition.line, state.definition.at);
}

/**
 * The chunks of `state` that `prepared` still starts with: a preprocess pass
 * that rewrote earlier text, or a settled reply that differs from what
 * streamed, drops the chunks from there on, not all of them. A chunk drawn as
 * a list that goes on is kept only while the text after it still goes on with
 * that list.
 */
function keptPrefix(state: StreamBlocksState, prepared: string): StreamBlocksState {
  let keep = state.chunks.length;
  let length = state.settledText.length;
  if (!prepared.startsWith(state.settledText)) {
    keep = 0;
    length = 0;
    while (keep < state.chunks.length && prepared.startsWith(state.chunks[keep]!, length)) {
      length += state.chunks[keep]!.length;
      keep += 1;
    }
  }
  while (keep > 0 && state.continued[keep - 1] && !listGoesOn(state.listAfter[keep - 1]!, prepared, length)) {
    keep -= 1;
    length -= state.chunks[keep]!.length;
  }
  return trimmedTo(state.definition ? { ...state, definition: null } : state, keep);
}

/**
 * Advance the settled-chunk state for grown `prepared` content.
 *
 * `safeLen` bounds settling to the region whose preprocessing is final
 * (the prepared-stable prefix); the remainder stays in the live tail.
 * If `prepared` no longer extends the settled prefix (new stream, or a
 * preprocess pass rewrote earlier text) the chunks from the first one that
 * changed are dropped and cut again.
 */
export function advanceStreamBlocks(
  prev: StreamBlocksState | null,
  prepared: string,
  safeLen: number,
): StreamBlocksState {
  const start = prev ?? emptyStreamBlocksState();
  if (holdsDefinition(start, prepared)) return start;
  let base = keptPrefix(start, prepared);

  // Cut only in the closed text; read the live end too (see scanClosedBlocks).
  const boundedSafeLen = Math.min(Math.max(safeLen, 0), prepared.length);
  const scanFrom = (state: StreamBlocksState) =>
    scanClosedBlocks(
      prepared,
      state.settledText.length,
      Math.max(boundedSafeLen, state.settledText.length),
      lastOpenList(state),
      prepared.length,
    );
  let scan = scanFrom(base);
  if (scan.definition) return { ...emptyStreamBlocksState(), definition: scan.definition };
  if (scan.inheritedWide) {
    base = withoutOpenListChunks(base);
    scan = scanFrom(base);
  }
  return scan.cuts.length > 0 ? cutChunks(base, prepared, scan.cuts) : base;
}

/**
 * The chunks a settled reply is drawn with: those of its stream it still
 * starts with, the rest in one piece, so what was drawn is not drawn again.
 * No new cuts. A reply that holds a link reference definition is one piece,
 * and a numbered list that reached 100 is drawn whole.
 */
export function settleStreamBlocks(
  prev: StreamBlocksState | null,
  prepared: string,
): StreamBlocksState {
  const start = prev ?? emptyStreamBlocksState();
  if (holdsDefinition(start, prepared)) return start;
  const base = keptPrefix(start, prepared);
  if (base.chunks.length === 0) return base;
  const settledEnd = base.settledText.length;
  const scan = scanClosedBlocks(prepared, settledEnd, settledEnd, lastOpenList(base), prepared.length);
  if (scan.definition) return { ...emptyStreamBlocksState(), definition: scan.definition };
  return scan.inheritedWide ? withoutOpenListChunks(base) : base;
}

function lastOpenList(state: StreamBlocksState): OpenList | null {
  return state.listAfter[state.listAfter.length - 1] ?? null;
}
