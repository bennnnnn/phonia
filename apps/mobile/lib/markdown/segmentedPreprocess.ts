/**
 * The closed text of a streaming reply, preprocessed in parts: each part once,
 * the open part (since the last cut) again when it grows. `streamSegments.ts`
 * says where a cut may land; here every cut is also checked, so the parts
 * always join to exactly what `preprocessMarkdown` makes of the whole.
 */
import {
  advanceSegmentScan,
  emptySegmentScan,
  readsBackAcrossCuts,
  type SegmentScanState,
} from "@/lib/markdown/streamSegments";

type Preprocess = (raw: string) => string;

export type SegmentedPrefix = {
  /** Raw text of the cut parts, joined (a prefix of the reply). */
  raw: string;
  /** Raw start of each cut part. */
  starts: number[];
  /** Each cut part, preprocessed. */
  parts: string[];
  /** `parts` joined. */
  prepared: string;
  scan: SegmentScanState;
  /** The open part (from the last cut to the stable end) and its preprocess. */
  openRaw: string;
  openPrepared: string;
};

function emptySegmentedPrefix(): SegmentedPrefix {
  return {
    raw: "",
    starts: [],
    parts: [],
    prepared: "",
    scan: emptySegmentScan(),
    openRaw: "",
    openPrepared: "",
  };
}

/** Drop the parts that start at or after `start`; the open part now begins at the first dropped. */
function rewindTo(prefix: SegmentedPrefix, start: number): number {
  let keep = prefix.starts.length;
  while (keep > 0 && prefix.starts[keep - 1]! >= start) keep -= 1;
  if (keep === prefix.starts.length) return prefix.raw.length;
  const from = prefix.starts[keep]!;
  prefix.starts = prefix.starts.slice(0, keep);
  prefix.parts = prefix.parts.slice(0, keep);
  prefix.prepared = prefix.parts.join("");
  prefix.raw = prefix.raw.slice(0, from);
  prefix.openRaw = "";
  return from;
}

/**
 * Extend `prev` (made from an earlier, shorter text of the same reply) to the
 * closed prefix `content.slice(0, stableLen)`, and return the preprocessed
 * prefix. `prev` is not changed.
 */
export function advanceSegmentedPrefix(
  prev: SegmentedPrefix | null,
  content: string,
  stableLen: number,
  preprocess: Preprocess,
): { prefix: SegmentedPrefix; preparedStable: string } {
  // Everything `prev` read must still be there: the cut parts and the open part.
  const base =
    prev &&
    prev.scan.scannedLen <= stableLen &&
    content.startsWith(prev.raw) &&
    content.startsWith(prev.openRaw, prev.raw.length)
      ? prev
      : null;
  const prefix: SegmentedPrefix = base ? { ...base } : emptySegmentedPrefix();
  const tryCut = (start: number): boolean => {
    const open = content.slice(prefix.raw.length, start);
    const after = content.slice(start, stableLen);
    const whole = preprocess(open + after);
    const head = preprocess(open);
    const rest = preprocess(after);
    if (whole !== head + rest) {
      prefix.openRaw = open + after;
      prefix.openPrepared = whole;
      return false;
    }
    prefix.starts = [...prefix.starts, prefix.raw.length];
    prefix.parts = [...prefix.parts, head];
    prefix.prepared += head;
    prefix.raw += open;
    prefix.openRaw = after;
    prefix.openPrepared = rest;
    return true;
  };
  prefix.scan = advanceSegmentScan(prefix.scan, content, stableLen, {
    tryCut,
    rewind: (start) => rewindTo(prefix, start),
  });
  const openRaw = content.slice(prefix.raw.length, stableLen);
  if (openRaw !== prefix.openRaw) {
    prefix.openRaw = openRaw;
    prefix.openPrepared = preprocess(openRaw);
  }
  return { prefix, preparedStable: prefix.prepared + prefix.openPrepared };
}

/**
 * All of `content`, from the parts `prev` cut while it streamed: the cut parts
 * stay as they were preprocessed, and the rest (the open part and the text
 * after it) is preprocessed once, with no new cut. Null when the parts no
 * longer lead `content`, or the text `prev` did not read holds a line that
 * changes how the parts before it preprocess.
 */
export function finishSegmentedPrefix(
  prev: SegmentedPrefix,
  content: string,
  preprocess: Preprocess,
): string | null {
  const read = prev.raw + prev.openRaw;
  if (!content.startsWith(read)) return null;
  const unread = content.slice(read.length);
  if (readsBackAcrossCuts(unread)) return null;
  return prev.prepared + preprocess(prev.openRaw + unread);
}
