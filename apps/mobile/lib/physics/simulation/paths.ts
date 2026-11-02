/**
 * The bodies' sampled paths: whether they move, whether one loops, where a
 * body is between two samples, and how fast it is going.
 */
import { type SimulationBody, type SimulationSpec } from "@/lib/physics/simulation/spec";
import { type ScreenPoint } from "@/lib/physics/simulation/viewport";

/** Whether any body moves, i.e. whether the scene has anything to play. */
export function simulationIsAnimated(spec: SimulationSpec): boolean {
  return spec.bodies.some((body) =>
    body.path.some((point) => point[0] !== body.path[0][0] || point[1] !== body.path[0][1]),
  );
}

export function isStationary(body: SimulationBody): boolean {
  const [x0, y0] = body.path[0];
  return body.path.every(([x, y]) => x === x0 && y === y0);
}

/**
 * Whether a sampled path is a loop the clock goes round: it ends where it
 * started *and* carries straight on through that join.
 *
 * Both halves matter. An orbit, or a spring sampled over whole periods, ends
 * on its first sample still travelling the same way, so the motion at t = 1
 * is the motion at t = 0. A ball thrown straight up and caught also ends where
 * it started, but arrives moving the opposite way — wrapping that path would
 * average the throw with the catch and draw no velocity at all at launch.
 */
export function isClosedPath(points: readonly ScreenPoint[]): boolean {
  const last = points.length - 1;
  if (last < 3) return false;
  const first = points[0];
  const end = points[last];
  let extent = 0;
  for (const p of points) extent = Math.max(extent, Math.hypot(p.px - first.px, p.py - first.py));
  if (extent === 0) return false;
  if (Math.hypot(end.px - first.px, end.py - first.py) > Math.max(0.5, extent * 0.01)) {
    return false;
  }
  const outX = points[1].px - first.px;
  const outY = points[1].py - first.py;
  const inX = end.px - points[last - 1].px;
  const inY = end.py - points[last - 1].py;
  const outLength = Math.hypot(outX, outY);
  const inLength = Math.hypot(inX, inY);
  if (outLength === 0 || inLength === 0) return false;
  // Coarse loops turn by 360°/n per sample, so a square still counts; a path
  // that doubles back (≥ 120°) does not.
  return (outX * inX + outY * inY) / (outLength * inLength) > -0.5;
}

/** Whether a sampled path comes back to its first sample (to within 1% of its size). */
export function endsWhereItStarts(points: readonly ScreenPoint[]): boolean {
  const last = points.length - 1;
  if (last < 3) return false;
  const first = points[0];
  let extent = 0;
  for (const p of points) extent = Math.max(extent, Math.hypot(p.px - first.px, p.py - first.py));
  if (extent === 0) return false;
  return (
    Math.hypot(points[last].px - first.px, points[last].py - first.py) <=
    Math.max(0.5, extent * 0.01)
  );
}

/**
 * The path at a fractional sample index in [0, last], linearly interpolated.
 *
 * Declared before `tangentAt` on purpose: a worklet captures the functions it
 * calls when it is defined, so a helper declared below it is `undefined` on
 * the UI thread.
 */
export function samplePathAt(points: readonly ScreenPoint[], index: number): ScreenPoint {
  "worklet";
  const last = points.length - 1;
  const lo = Math.floor(index);
  const hi = lo + 1 > last ? last : lo + 1;
  const frac = index - lo;
  return {
    px: points[lo].px + (points[hi].px - points[lo].px) * frac,
    py: points[lo].py + (points[hi].py - points[lo].py) * frac,
  };
}

/**
 * Velocity at `progress`, as screen pixels per sample.
 *
 * Taken across a small window rather than between adjacent points: on a
 * densely sampled path two neighbours can round to the same pixel, and a
 * near-zero tangent makes the velocity arrow flip about randomly. The window
 * is what solves that, so a genuinely zero result here means the body is not
 * moving — which collisions and held blocks both produce — and it is returned
 * as zero rather than papered over with a default direction that would draw a
 * velocity arrow on a stationary ball.
 *
 * The samples are uniform in time, so dividing by the window's span makes the
 * length proportional to speed with no physics repeated here — including at
 * the ends, where the window is cut in half. On a closed path
 * (`isClosedPath`) the window wraps round the join instead, so an orbit's
 * arrow is as tangent at t = 0 and t = 1 as anywhere else.
 */
export function tangentAt(
  points: readonly ScreenPoint[],
  progress: number,
  closed = false,
): { dx: number; dy: number } {
  "worklet";
  const last = points.length - 1;
  if (last < 1) return { dx: 0, dy: 0 };
  const clamped = progress < 0 ? 0 : progress > 1 ? 1 : progress;
  const window = Math.max(1, Math.round(last * 0.04));
  // Read at the fractional index the body is drawn at, so the arrow turns
  // smoothly with it instead of snapping from sample to sample.
  const at = clamped * last;
  const wraps = closed && last > 2 * window;
  let lo = at - window;
  let hi = at + window;
  if (wraps) {
    // The last sample repeats the first, so the loop has `last` distinct ones.
    if (lo < 0) lo += last;
    if (hi > last) hi -= last;
  } else {
    lo = lo < 0 ? 0 : lo;
    hi = hi > last ? last : hi;
  }
  const span = wraps ? 2 * window : hi - lo;
  if (span <= 0) return { dx: 0, dy: 0 };
  const a = samplePathAt(points, lo);
  const b = samplePathAt(points, hi);
  return { dx: (b.px - a.px) / span, dy: (b.py - a.py) / span };
}

/** The fastest the body moves anywhere on its path, in `tangentAt`'s units. */
export function maxTrackSpeed(points: readonly ScreenPoint[], closed = false): number {
  const last = points.length - 1;
  let best = 0;
  for (let i = 0; i <= last; i += 1) {
    const v = tangentAt(points, last > 0 ? i / last : 0, closed);
    best = Math.max(best, Math.hypot(v.dx, v.dy));
  }
  return best;
}

/** Which samples a strobe shows: `count` evenly spaced, first and last included. */
export function strobeIndices(samples: number, count: number | undefined): number[] {
  if (!count || count < 2 || samples < 2) return [];
  const last = samples - 1;
  const out: number[] = [];
  for (let i = 0; i < count; i += 1) {
    const index = Math.round((i * last) / (count - 1));
    if (out[out.length - 1] !== index) out.push(index);
  }
  return out;
}
