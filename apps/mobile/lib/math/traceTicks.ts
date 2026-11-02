/**
 * When tracing a curve in the graph explorer plays a selection tick: when the
 * finger takes hold of a curve or moves to another one, and when the traced
 * point passes a root or a turning point. A tick on every sample buzzed
 * continuously (61 ticks in a one-second scrub), so nothing else ticks, and
 * two marks closer than MIN_TICK_GAP_MS share one.
 */

export type TraceTickState = {
  series: number;
  index: number;
  y: number;
  /** Sign of the curve's slope along x at the last sample: 1, −1 or 0 (unknown). */
  rising: number;
  /** When the last tick played, in ms. */
  at: number;
};

type TracedSample = { seriesIndex: number; index: number; y: number };

export const NO_TRACE: TraceTickState = { series: -1, index: -1, y: 0, rising: 0, at: -1e12 };
/** Marks closer together than this read as a buzz. */
const MIN_TICK_GAP_MS = 90;

export function traceTickW(
  state: TraceTickState,
  sample: TracedSample | null,
  now: number,
): { tick: boolean; state: TraceTickState } {
  "worklet";
  if (sample == null) return { tick: false, state: { ...NO_TRACE, at: state.at } };
  if (sample.seriesIndex !== state.series) {
    return {
      tick: true,
      state: { series: sample.seriesIndex, index: sample.index, y: sample.y, rising: 0, at: now },
    };
  }
  if (sample.index === state.index) return { tick: false, state };
  // Along x, whichever way the finger moves: turning back is not a turning point.
  const slope = Math.sign((sample.y - state.y) * (sample.index - state.index));
  const root = (state.y < 0 && sample.y >= 0) || (state.y > 0 && sample.y <= 0);
  const turned = slope !== 0 && state.rising !== 0 && slope !== state.rising;
  const tick = (root || turned) && now - state.at >= MIN_TICK_GAP_MS;
  return {
    tick,
    state: {
      series: state.series,
      index: sample.index,
      y: sample.y,
      rising: slope !== 0 ? slope : state.rising,
      at: tick ? now : state.at,
    },
  };
}
