import { preprocessMarkdown, type PreprocessOptions } from "@/lib/markdown/preprocess";
import { presentStreamTail } from "@/lib/markdown/presentation";
import {
  advanceSegmentedPrefix,
  finishSegmentedPrefix,
  type SegmentedPrefix,
} from "@/lib/markdown/segmentedPreprocess";
import { fenceAfterLine, type OpenFence } from "@/lib/mdFenceScan";

export type StreamingPreprocessCache = {
  /** Raw byte length covered by `preparedStable`. */
  rawStableLen: number;
  /** Preprocessed output for `content.slice(0, rawStableLen)`. */
  preparedStable: string;
  /**
   * Incremental-scan state for `preprocessMarkdownForStream`'s stability
   * check (see `scanStableMarkdownPrefix` below). Opaque to callers — just
   * round-trip it back in on the next call. `null` means "start a fresh
   * scan" (e.g. a new stream, or a cache that predates this field).
   */
  scanState: StableScanState | null;
  /** `preparedStable` was prepared as server-presented text (PreprocessOptions). */
  presented: boolean;
  /** The stable prefix in parts, each preprocessed once (segmentedPreprocess.ts). */
  segments?: SegmentedPrefix | null;
  /** The maths formatter `segments` were preprocessed with. */
  mathFormat?: (expr: string) => string;
};

/**
 * Longest raw prefix safe to preprocess while the message is still growing.
 * Excludes partial lines and regions inside unclosed fences / block math.
 *
 * This is the simple, non-incremental reference implementation: it re-scans
 * from the start of `content` on every call. It is kept exactly as it was
 * (and is still covered directly by tests) as the ground truth that
 * `scanStableMarkdownPrefix`'s incremental fast path is checked against.
 *
 * The streaming hot path (`preprocessMarkdownForStream`) does NOT call this
 * function — it uses the incremental scanner instead, because re-running a
 * whole-prefix scan from scratch on every ~48ms throttle tick is
 * O(content length) per call, and while a single fence/math block/callout
 * stays open across many ticks, that cost is paid again and again as the
 * unstable region grows (cost grows with how long the structure stays open).
 */
export function findStableMarkdownPrefixLen(content: string): number {
  if (!content) return 0;

  let end = content.length;
  if (!content.endsWith("\n")) {
    const lastNl = content.lastIndexOf("\n");
    if (lastNl === -1) return 0;
    end = lastNl + 1;
  }

  while (end > 0) {
    const prefix = content.slice(0, end);
    if (!hasUnclosedStreamingStructure(prefix)) return end;
    const prevNl = prefix.lastIndexOf("\n", prefix.length - 2);
    if (prevNl === -1) return 0;
    end = prevNl + 1;
  }

  return 0;
}

/** `$`, `$$`, `\[`, and `\(` inside a code fence are code, not math. */
function mathMarkersOutsideFences(text: string): {
  blockDollar: number;
  inlineDollar: number;
  brackets: number;
  parens: number;
  fenceOpen: boolean;
} {
  let openFence: OpenFence | null = null;
  let blockDollar = 0;
  let inlineDollar = 0;
  let brackets = 0;
  let parens = 0;
  let pos = 0;
  while (pos < text.length) {
    const nl = text.indexOf("\n", pos);
    const lineEnd = nl === -1 ? text.length : nl;
    const line = text.slice(pos, lineEnd);
    const before = openFence;
    openFence = fenceAfterLine(openFence, line);
    if (before == null && openFence == null) {
      const blocks = countOccurrences(line, "$$");
      blockDollar += blocks;
      inlineDollar += countOccurrences(line, "$") - 2 * blocks;
      brackets += countOccurrences(line, "\\[") - countOccurrences(line, "\\]");
      parens += countOccurrences(line, "\\(") - countOccurrences(line, "\\)");
    }
    if (nl === -1) break;
    pos = nl + 1;
  }
  return { blockDollar, inlineDollar, brackets, parens, fenceOpen: openFence != null };
}

function hasUnclosedStreamingStructure(text: string): boolean {
  const math = mathMarkersOutsideFences(text);
  if (math.blockDollar % 2 !== 0) return true;
  // Odd `$` outside a fence means an unclosed `$...$` span — without this,
  // a prefix cut mid-`$x^2 +` would be treated as stable.
  if (math.inlineDollar % 2 !== 0) return true;
  if (math.fenceOpen) return true;
  // \[...\] is the other block-math delimiter preprocessMarkdown converts
  // (BLOCK_MATH_BRACKET_RE, alongside $$...$$) — without tracking it here
  // too, an unclosed \[ mid-stream gets folded into the "stable" prefix and
  // preprocessed while still open, leaving a raw dangling "\[" visible until
  // the closing \] finally arrives.
  if (math.brackets !== 0) return true;
  // \(...\) inline math — same risk as $...$ above.
  if (math.parens !== 0) return true;
  if (endsWithOpenCallout(text)) return true;
  if (endsWithOpenPipeTable(text)) return true;
  return false;
}

/** True when the last complete line is a GFM pipe-table row (still growing). */
function endsWithOpenPipeTable(text: string): boolean {
  const lines = text.split("\n");
  let i = lines.length - 1;
  if (i >= 0 && lines[i] === "") i -= 1;
  if (i < 0) return false;
  return looksLikePipeTableLine(lines[i] ?? "");
}

function looksLikePipeTableLine(line: string): boolean {
  const trimmed = line.trim();
  if (!trimmed.startsWith("|")) return false;
  return trimmed.indexOf("|", 1) >= 0;
}

/** True when `text` ends inside an open GFM callout (line-scan, no ReDoS). */
function endsWithOpenCallout(text: string): boolean {
  const lines = text.split("\n");
  // A trailing `\n` leaves an empty final segment — skip it.
  let i = lines.length - 1;
  if (i >= 0 && lines[i] === "") i -= 1;
  // Walk back over trailing quote-continuation lines to a `> [!type]` marker.
  // Marker must not be the absolute first line of the message (needs a prior `\n`).
  while (i >= 0 && /^>\s?/.test(lines[i])) {
    if (i > 0 && /^>\s*\[!\w+\]/i.test(lines[i])) return true;
    i -= 1;
  }
  return false;
}

function countOccurrences(text: string, needle: string): number {
  if (!needle) return 0;
  let count = 0;
  let idx = 0;
  while ((idx = text.indexOf(needle, idx)) !== -1) {
    count += 1;
    idx += needle.length;
  }
  return count;
}

const CALLOUT_MARKER_LINE_RE = /^>\s*\[!\w+\]/i;

type StableScanState = {
  /** Absolute offset into `content` already folded into the fields below. */
  scannedLen: number;
  /**
   * The fence open at `scannedLen`, tracked open and closed (not a parity count of fence
   * lines): a ``` line inside a ~~~ block is that block's content (audit DUP-03).
   */
  openFence: OpenFence | null;
  /** Parity of `$$` occurrences seen so far (true = inside block math). */
  dollarOpen: boolean;
  /** Running count of `\[` minus `\]` seen so far (nonzero = inside \[...\] block math). */
  bracketDepth: number;
  /** Parity of single-`$` (not part of `$$`) occurrences seen so far (true = inside `$...$` inline math). */
  inlineDollarOpen: boolean;
  /** Running count of `\(` minus `\)` seen so far (nonzero = inside \(...\) inline math). */
  parenDepth: number;
  /** Whether an unclosed `> [!type]` callout chain reaches `scannedLen`. */
  calloutOpen: boolean;
  /** Whether an unclosed GFM pipe-table chain reaches `scannedLen`. */
  pipeTableOpen: boolean;
  /** Largest confirmed-stable prefix length found up to `scannedLen`. */
  stableEnd: number;
};

/**
 * Incremental equivalent of `findStableMarkdownPrefixLen`, used by the
 * streaming hot path.
 *
 * `findStableMarkdownPrefixLen` finds the answer by walking backward from
 * the end of `content` line by line, re-running a whole-prefix regex/count
 * scan (`hasUnclosedStreamingStructure`) at every candidate boundary. For a
 * reply that opens one giant code fence and keeps streaming for thousands of
 * characters before closing it, every candidate boundary inside that fence
 * is unstable, so the walk visits — and fully re-scans from position 0 —
 * every line of the fence, every tick, for as long as it stays open.
 *
 * This function instead scans `content` forward line by line exactly once,
 * maintaining running parity/state for fences, `$$` math, and callouts as it
 * goes (folding in each line is O(1)), and remembers the last line boundary
 * where all three were "closed". Given a previous call's returned state, a
 * later call for grown (append-only) `content` resumes from
 * `state.scannedLen` instead of re-scanning from position 0 — so the work
 * done on each call is bounded by how much *new* text arrived since the
 * previous call, not by how much of the message is still open.
 *
 * Why resuming is safe: `scannedLen` is always a full-line boundary (0 or
 * right after a `\n`), and the fence/`$$` parity + callout state cached at
 * that boundary are exactly the running state a whole-prefix scan of
 * `content.slice(0, scannedLen)` would have computed. Appending more text
 * cannot retroactively change whether that earlier text closed its
 * fences/math/callouts (its own parity/chain state is a closed fact once
 * written), so the cached state stays valid — only the newly appended lines
 * need to be folded in. (This mirrors why `findStableMarkdownPrefixLen`'s
 * own answer never needs to re-examine text before a boundary it already
 * proved stable: a stable prefix's internal balance can't be undone by
 * appending after it.)
 *
 * If `prevState` looks stale (its `scannedLen` is past the current content —
 * should not happen for append-only streaming content, but checked
 * defensively), the scan restarts from 0.
 */
function scanStableMarkdownPrefix(
  content: string,
  prevState: StableScanState | null,
): StableScanState {
  let end0 = content.length;
  if (!content.endsWith("\n")) {
    const lastNl = content.lastIndexOf("\n");
    end0 = lastNl === -1 ? 0 : lastNl + 1;
  }

  let openFence: OpenFence | null = null;
  let dollarOpen = false;
  let bracketDepth = 0;
  let inlineDollarOpen = false;
  let parenDepth = 0;
  let calloutOpen = false;
  let pipeTableOpen = false;
  let stableEnd = 0;
  let pos = 0;

  if (prevState && prevState.scannedLen <= end0) {
    pos = prevState.scannedLen;
    openFence = prevState.openFence ?? null;
    dollarOpen = prevState.dollarOpen;
    bracketDepth = prevState.bracketDepth;
    inlineDollarOpen = prevState.inlineDollarOpen;
    parenDepth = prevState.parenDepth;
    calloutOpen = prevState.calloutOpen;
    pipeTableOpen = prevState.pipeTableOpen;
    stableEnd = prevState.stableEnd;
  }

  while (pos < end0) {
    const nl = content.indexOf("\n", pos);
    if (nl === -1 || nl >= end0) break;
    const line = content.slice(pos, nl);
    const isAbsoluteFirstLine = pos === 0;

    // ``` and ~~~ fences both keep their body unstable (otherwise the streaming
    // preprocessor would cut mid-fence and render a half-open fence).
    const before = openFence;
    openFence = fenceAfterLine(openFence, line);
    if (before == null && openFence == null) {
      const blockDollarCount = countOccurrences(line, "$$");
      if (blockDollarCount % 2 !== 0) dollarOpen = !dollarOpen;
      // Track single-`$` inline math: total `$` minus the ones consumed by `$$` pairs.
      const totalDollar = countOccurrences(line, "$");
      const inlineDollarCount = totalDollar - 2 * blockDollarCount;
      if (inlineDollarCount % 2 !== 0) inlineDollarOpen = !inlineDollarOpen;
      bracketDepth += countOccurrences(line, "\\[") - countOccurrences(line, "\\]");
      parenDepth += countOccurrences(line, "\\(") - countOccurrences(line, "\\)");
    }
    // A callout chain continues as long as each new line still starts with
    // ">" (matching the original regex's permissive continuation pattern);
    // otherwise it only (re)starts on a proper `> [!type]` marker line — and
    // per the original regex, a marker line at the absolute start of the
    // whole message (no preceding "\n" before it) never counts, so that's
    // excluded here too.
    calloutOpen = calloutOpen
      ? line.startsWith(">")
      : !isAbsoluteFirstLine && CALLOUT_MARKER_LINE_RE.test(line);
    pipeTableOpen = looksLikePipeTableLine(line);

    pos = nl + 1;
    if (
      openFence == null &&
      !dollarOpen &&
      bracketDepth === 0 &&
      !inlineDollarOpen &&
      parenDepth === 0 &&
      !calloutOpen &&
      !pipeTableOpen
    ) {
      stableEnd = pos;
    }
  }

  return {
    scannedLen: end0,
    openFence,
    dollarOpen,
    bracketDepth,
    inlineDollarOpen,
    parenDepth,
    calloutOpen,
    pipeTableOpen,
    stableEnd,
  };
}

/**
 * Incrementally preprocess append-only streaming markdown.
 * The stable prefix is preprocessed exactly as `preprocessMarkdown` would the
 * whole of it, in parts that each run once (segmentedPreprocess.ts), so a
 * flush costs the new text rather than the reply. The trailing unstable region
 * stays raw until it closes (or the stream ends and a full preprocess runs).
 * The text still streaming is the model's own and is presented here;
 * `presented` text is a saved row held in stream layout while it settles.
 */
export function preprocessMarkdownForStream(
  content: string,
  cache: StreamingPreprocessCache | null,
  mathFormat?: (expr: string) => string,
  options: PreprocessOptions = {},
): { prepared: string; cache: StreamingPreprocessCache } {
  const presented = options.presented === true;
  const scanState = scanStableMarkdownPrefix(content, cache?.scanState ?? null);
  const stableLen = scanState.stableEnd;

  if (stableLen === 0) {
    return {
      prepared: presentStreamTail(content, presented),
      cache: { rawStableLen: 0, preparedStable: "", scanState, presented },
    };
  }

  const reusable = cache && cache.presented === presented && cache.mathFormat === mathFormat;
  const { prefix, preparedStable } = advanceSegmentedPrefix(
    reusable ? (cache.segments ?? null) : null,
    content,
    stableLen,
    (raw) => preprocessMarkdown(raw, mathFormat, options),
  );
  const tail = content.slice(stableLen);
  return {
    prepared: preparedStable + presentStreamTail(tail, presented),
    cache: {
      rawStableLen: stableLen,
      preparedStable,
      scanState,
      presented,
      segments: prefix,
      mathFormat,
    },
  };
}

/**
 * A reply that has just finished streaming, preprocessed as
 * `preprocessMarkdown` preprocesses it whole. The parts its stream already
 * preprocessed (`cache`) are kept, so the end of a long reply preprocesses the
 * text after its last cut, not the whole reply again. A reply that changed
 * before that cut, or a cache made with other options, is preprocessed whole.
 */
export function preprocessSettledMarkdown(
  content: string,
  cache: StreamingPreprocessCache | null,
  mathFormat?: (expr: string) => string,
  options: PreprocessOptions = {},
): string {
  const preprocess = (raw: string) => preprocessMarkdown(raw, mathFormat, options);
  const segments =
    cache && cache.presented === (options.presented === true) && cache.mathFormat === mathFormat
      ? cache.segments
      : null;
  return (segments ? finishSegmentedPrefix(segments, content, preprocess) : null) ?? preprocess(content);
}
