import { useEffect, useMemo, useState } from "react";
import type { TFunction } from "i18next";

const MAX_VARIANTS = 6;
const STREAM_STATUS_ROTATE_MS = 3200;
const STATUS_DETAIL_MAX_CHARS = 44;

/** Fake agent-progress chips. ChatGPT only labels long tools (search, files,
 *  image gen, …). Ordinary wait is typing dots — same as our TTS path.
 *  `finishing` ends a step after the reply's text (the check, a photo): no label. */
const THEATER_STREAM_PHASES = new Set([
  "preparing",
  "remembering",
  "composing",
  "finishing",
]);

/** Real work the server reports as it happens: the model reasoning, the answer
 *  being checked. Its label waits this long, so a quick step never flashes one. */
const PROGRESS_STREAM_PHASES = new Set(["thinking", "checking"]);
export const PROGRESS_LABEL_DELAY_MS = 1000;
/** A server's `elapsed_ms` beyond this is not a start this turn could have had. */
const MAX_PHASE_ELAPSED_MS = 10 * 60 * 1000;

export function isProgressStreamPhase(phase: string | undefined): boolean {
  return phase !== undefined && PROGRESS_STREAM_PHASES.has(phase);
}

/**
 * When a status's phase began, on this phone's clock. The same phase sent again
 * keeps its start (a backup model thinking on); the server's `elapsed_ms` moves a
 * new one back to when the work really began.
 */
export function phaseStartedAt(
  previous: { status?: string; statusStartedAt?: number } | null | undefined,
  phase: string,
  elapsedMs: unknown,
  now: number = Date.now(),
): number {
  if (previous?.status === phase && previous.statusStartedAt !== undefined) {
    return previous.statusStartedAt;
  }
  const elapsed =
    typeof elapsedMs === "number" && Number.isFinite(elapsedMs) && elapsedMs > 0
      ? Math.min(elapsedMs, MAX_PHASE_ELAPSED_MS)
      : 0;
  return now - elapsed;
}

/**
 * The one-line label for `phase`, `elapsedMs` after it began: "Thinking… 12s",
 * "Checking the answer…". Null while a progress phase is under a second old, and
 * for the theater phases; any other phase reads as its own label.
 */
export function progressStreamLabel(t: TFunction, phase: string, elapsedMs: number): string | null {
  if (!PROGRESS_STREAM_PHASES.has(phase)) {
    return streamStatusLabels(t, phase)[0] ?? null;
  }
  if (elapsedMs < PROGRESS_LABEL_DELAY_MS) {
    return null;
  }
  if (phase === "thinking") {
    return t("chat.status.thinking_seconds", { seconds: Math.floor(elapsedMs / 1000) });
  }
  return t(`chat.status.${phase}`);
}

/** Bound the inline detail so the label stays one line on small screens. */
export function clipStreamStatusDetail(detail: string): string {
  const flattened = detail.replace(/\s+/g, " ").trim();
  if (flattened.length <= STATUS_DETAIL_MAX_CHARS) return flattened;
  return `${flattened.slice(0, STATUS_DETAIL_MAX_CHARS - 1).trimEnd()}…`;
}

/**
 * Collect translated labels for a stream phase (base key + `_1`, `_2`, …).
 * When the server sent activity context (e.g. the search query) and a
 * `<phase>_detail` template exists, that label leads the rotation.
 */
export function streamStatusLabels(
  t: TFunction,
  phase: string,
  detail?: string,
): string[] {
  // Progress phases have their own timed label (progressStreamLabel).
  if (THEATER_STREAM_PHASES.has(phase) || PROGRESS_STREAM_PHASES.has(phase)) {
    return [];
  }
  const labels: string[] = [];
  const baseKey = `chat.status.${phase}`;
  if (detail) {
    const detailKey = `${baseKey}_detail`;
    const withDetail = t(detailKey, { detail: clipStreamStatusDetail(detail) });
    if (withDetail !== detailKey) {
      labels.push(withDetail);
    }
  }
  const base = t(baseKey);
  if (base !== baseKey) {
    labels.push(base);
  }
  for (let i = 1; i < MAX_VARIANTS; i += 1) {
    const key = `${baseKey}_${i}`;
    const label = t(key);
    if (label === key) {
      break;
    }
    labels.push(label);
  }
  return labels;
}

export function pickRotatingStreamLabel(labels: string[], tick: number): string | null {
  if (labels.length === 0) {
    return null;
  }
  return labels[tick % labels.length] ?? labels[0];
}

/** Typing dots / status label while the model is working and no tokens yet.
 * Raw CoT is never shown on the bubble (only that the model is thinking), so this
 * stays on until content arrives. */
export function shouldShowWaitingIndicator(options: {
  isStreaming: boolean;
  hasContent: boolean;
}): boolean {
  return options.isStreaming && !options.hasContent;
}

/**
 * Starting variant for a phase. Detail labels always lead; otherwise start at
 * a random variant so consecutive turns don't open with identical strings.
 */
export function initialStreamStatusTick(
  labelCount: number,
  hasDetail: boolean,
  random: () => number = Math.random,
): number {
  if (hasDetail || labelCount <= 1) {
    return 0;
  }
  return Math.floor(random() * labelCount) % labelCount;
}

export function useRotatingStreamStatus(
  phase: string | undefined,
  enabled: boolean,
  t: TFunction,
  detail?: string,
): string | null {
  const labels = useMemo(
    () => (phase ? streamStatusLabels(t, phase, detail) : []),
    [phase, detail, t],
  );
  // The opening variant is picked in the render that shows a new phase. Picked in an
  // effect, the first variant was painted for a frame and then swapped for another.
  const start = `${phase ?? ""}\n${detail ?? ""}\n${labels.length}\n${enabled}`;
  const [rotation, setRotation] = useState(() => ({
    start,
    tick: initialStreamStatusTick(labels.length, Boolean(detail)),
  }));
  let tick = rotation.tick;
  if (rotation.start !== start) {
    tick = initialStreamStatusTick(labels.length, Boolean(detail));
    setRotation({ start, tick });
  }

  useEffect(() => {
    if (!enabled || labels.length <= 1) {
      return;
    }
    const id = setInterval(() => {
      setRotation((value) => ({ ...value, tick: value.tick + 1 }));
    }, STREAM_STATUS_ROTATE_MS);
    return () => clearInterval(id);
  }, [enabled, labels.length, phase, detail]);

  if (!phase || labels.length === 0) {
    return null;
  }
  return pickRotatingStreamLabel(labels, tick);
}
