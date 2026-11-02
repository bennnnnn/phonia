/**
 * Parsing and geometry for the wave diagram (`simulation` fence, type `wave`).
 *
 * The server samples the wave: one row of displacements per frame over fixed
 * x samples, covering one period. The client steps through those frames and
 * never evaluates a wave function. Between two frames it blends the samples,
 * exactly as the trajectory and the scene blend between path samples, so a
 * 24-frame period still moves smoothly.
 *
 * The world frame (bounds, the equal-aspect transform, measure lines) is the
 * ray diagram's, in `optics.ts`.
 */

import { finiteNumber } from "@/lib/fenceValidate";

type WaveEnd = "none" | "fixed" | "open" | "closed";

const WAVE_ENDS: readonly WaveEnd[] = ["none", "fixed", "open", "closed"];

export type WaveSpec = {
  /** Increasing world x of every sample. */
  x: number[];
  /** One displacement per x sample, per frame. */
  frames: number[][];
  nodes: number[];
  antinodes: number[];
  /** What holds the left end, then the right. */
  ends: [WaveEnd, WaveEnd];
};

const X_LIMITS = [2, 160] as const;
const FRAME_LIMITS = [2, 48] as const;
const MAX_MARKS = 12;

function numbers(raw: unknown, min: number, max: number): number[] | null {
  if (!Array.isArray(raw) || raw.length < min || raw.length > max) return null;
  const out: number[] = [];
  for (const value of raw) {
    const n = finiteNumber(value);
    if (n === null) return null;
    out.push(n);
  }
  return out;
}

/**
 * Read the `wave` object of a fence, or null when it is malformed — as the
 * server model would: x samples that do not increase, a frame with one value
 * too few, a non-finite displacement, an end nothing knows how to draw.
 */
export function parseWaveSpec(raw: unknown): WaveSpec | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const row = raw as Record<string, unknown>;
  const x = numbers(row.x, X_LIMITS[0], X_LIMITS[1]);
  if (!x || x.some((value, index) => index > 0 && value <= x[index - 1])) return null;
  if (!Array.isArray(row.frames) || row.frames.length < FRAME_LIMITS[0] || row.frames.length > FRAME_LIMITS[1]) {
    return null;
  }
  const frames: number[][] = [];
  for (const frame of row.frames) {
    const values = numbers(frame, x.length, x.length);
    if (!values) return null;
    frames.push(values);
  }
  const marks = (value: unknown) =>
    value === undefined || value === null ? [] : numbers(value, 0, MAX_MARKS);
  const nodes = marks(row.nodes);
  const antinodes = marks(row.antinodes);
  if (!nodes || !antinodes) return null;
  let ends: [WaveEnd, WaveEnd] = ["none", "none"];
  if (row.ends !== undefined && row.ends !== null) {
    if (!Array.isArray(row.ends) || row.ends.length !== 2) return null;
    if (!row.ends.every((end) => WAVE_ENDS.includes(end as WaveEnd))) return null;
    ends = [row.ends[0] as WaveEnd, row.ends[1] as WaveEnd];
  }
  return { x, frames, nodes, antinodes, ends };
}

/** A wave that stands still between its nodes, rather than one running off the edge. */
export function isStandingWave(spec: WaveSpec): boolean {
  return spec.nodes.length > 0 || spec.antinodes.length > 0 || spec.ends.some((end) => end !== "none");
}

const SAME_FRAME = 1e-9;

/**
 * How many frames one loop steps through. The frames cover one period; a
 * fence that also repeats the first frame at the end drops that copy, so the
 * loop does not pause on the seam.
 */
export function waveCycleLength(frames: readonly number[][]): number {
  const first = frames[0];
  const last = frames[frames.length - 1];
  const repeats = frames.length > 2 && first.every((value, index) => Math.abs(value - last[index]) < SAME_FRAME);
  return repeats ? frames.length - 1 : frames.length;
}

/**
 * The samples shown at `progress` (0 to 1 is one loop), blended between the
 * two frames either side. Runs on the UI thread every frame.
 */
export function waveSamplesAt(frames: readonly number[][], cycle: number, progress: number): number[] {
  "worklet";
  const position = Math.max(0, progress) * cycle;
  const whole = Math.floor(position);
  const a = whole % cycle;
  const b = (a + 1) % cycle;
  const f = position - whole;
  const from = frames[a];
  const to = frames[b];
  const out: number[] = new Array(from.length);
  for (let i = 0; i < from.length; i += 1) out[i] = from[i] + (to[i] - from[i]) * f;
  return out;
}

/** The largest |displacement| each sample reaches across every frame. */
export function waveEnvelope(spec: WaveSpec): number[] {
  return spec.x.map((_, index) =>
    spec.frames.reduce((best, frame) => Math.max(best, Math.abs(frame[index])), 0),
  );
}

/** A per-sample array read at any x, linearly between samples; 0 outside them. */
export function sampleAt(xs: readonly number[], values: readonly number[], x: number): number {
  if (x < xs[0] || x > xs[xs.length - 1]) return 0;
  for (let i = 1; i < xs.length; i += 1) {
    if (x <= xs[i]) {
      const f = (x - xs[i - 1]) / (xs[i] - xs[i - 1]);
      return values[i - 1] + (values[i] - values[i - 1]) * f;
    }
  }
  return values[values.length - 1];
}

/** The pipe's walls are drawn when either end is part of a pipe. */
export function waveHasPipe(spec: WaveSpec): boolean {
  return spec.ends.some((end) => end === "open" || end === "closed");
}

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** What a screen reader says when the fence has no `alt`. */
export function describeWave(spec: WaveSpec, measureLabels: string[], t: Translate): string {
  const sentences = [t(isStandingWave(spec) ? "rich.diagram_a11y_standing_wave" : "rich.diagram_a11y_wave")];
  if (spec.nodes.length > 0) sentences.push(t("rich.diagram_a11y_nodes", { count: spec.nodes.length }));
  if (spec.antinodes.length > 0) {
    sentences.push(t("rich.diagram_a11y_antinodes", { count: spec.antinodes.length }));
  }
  const ends = spec.ends.filter((end) => end !== "none");
  if (ends.length > 0) {
    sentences.push(t("rich.diagram_a11y_ends", { list: ends.map((end) => t(`rich.diagram_end_${end}`)).join(", ") }));
  }
  if (measureLabels.length > 0) sentences.push(measureLabels.join(", "));
  return sentences.map((sentence) => sentence.replace(/[.\s]+$/, "")).join(". ") + ".";
}
