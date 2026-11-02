/** Bounds, ticks, axis formatting and point mapping for ```graph blocks. */
import { mapPointW, niceStepW } from "@/lib/math/graphWorklets";
import { toSuperscript } from "@/lib/unicodeSupSub";
import { type NumberLineInterval } from "@/lib/math/graphSpec";

export function graphBounds(
  points: [number, number][],
  // Second curve's points, when present — folded into the same min/max so
  // both curves share one consistent axis scale instead of each being
  // (re)bounded to just its own range.
  extraPoints?: [number, number][],
): {
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
} {
  let xMin = points[0][0];
  let xMax = points[0][0];
  let yMin = points[0][1];
  let yMax = points[0][1];
  for (const [x, y] of points) {
    xMin = Math.min(xMin, x);
    xMax = Math.max(xMax, x);
    yMin = Math.min(yMin, y);
    yMax = Math.max(yMax, y);
  }
  for (const [x, y] of extraPoints ?? []) {
    xMin = Math.min(xMin, x);
    xMax = Math.max(xMax, x);
    yMin = Math.min(yMin, y);
    yMax = Math.max(yMax, y);
  }
  // A single point (or several points sharing an x or y value) collapses
  // that axis's range to zero — pad it symmetrically so the point renders
  // centered instead of glued to the chart's edge (mapGraphPoint's `|| 1`
  // divide-by-zero guard alone would put it flush at the left/bottom).
  if (yMin === yMax) {
    yMin -= 1;
    yMax += 1;
  }
  if (xMin === xMax) {
    xMin -= 1;
    xMax += 1;
  }
  return { xMin, xMax, yMin, yMax };
}

/** Viewport for a number line: integers both sides of 0, room for arrows. */
export function numberLineBounds(intervals: NumberLineInterval[]): {
  xMin: number;
  xMax: number;
} {
  const finite: number[] = [0];
  let rayLeft = false;
  let rayRight = false;
  for (const iv of intervals) {
    if (iv.start == null) rayLeft = true;
    else finite.push(iv.start);
    if (iv.end == null) rayRight = true;
    else finite.push(iv.end);
  }
  let xMin = Math.min(...finite);
  let xMax = Math.max(...finite);
  xMin = Math.floor(xMin) - 1;
  xMax = Math.ceil(xMax) + 1;
  if (rayLeft) xMin -= 2;
  if (rayRight) xMax += 2;
  // Don't let the axis start at 0 — a number line continues through negatives.
  if (xMin > -2) xMin = -2;
  if (xMax < 2) xMax = 2;
  if (xMax - xMin < 6) {
    const extra = 6 - (xMax - xMin);
    xMin -= Math.ceil(extra / 2);
    xMax += Math.floor(extra / 2);
  }
  return { xMin, xMax };
}

/** Integer tick marks inside the viewport (capped so labels don't collide). */
export function numberLineTicks(xMin: number, xMax: number): number[] {
  const start = Math.floor(xMin) + 1;
  const end = Math.ceil(xMax) - 1;
  if (end < start) return [];
  const count = end - start + 1;
  const push = (n: number, into: number[]) => {
    into.push(n === 0 ? 0 : n);
  };
  if (count <= 11) {
    const out: number[] = [];
    for (let n = start; n <= end; n += 1) push(n, out);
    return out;
  }
  const step = Math.ceil(count / 9);
  const out: number[] = [];
  for (let n = start; n <= end; n += step) push(n, out);
  if (out[out.length - 1] !== end) push(end, out);
  if (!out.includes(0) && 0 >= start && 0 <= end) {
    push(0, out);
    out.sort((a, b) => a - b);
  }
  return out;
}

/** ``x >= 3`` → ``x ≥ 3`` for number-line titles. */
export function formatInequalityExpr(expr: string): string {
  let out = "";
  let i = 0;
  const src = expr.trim();
  while (i < src.length) {
    const two = src.slice(i, i + 2);
    if (two === ">=") {
      out += "≥";
      i += 2;
      continue;
    }
    if (two === "<=") {
      out += "≤";
      i += 2;
      continue;
    }
    out += src[i];
    i += 1;
  }
  return out;
}

const AXIS_PAD_RATIO = 0.08;

/** Expand data bounds so (0, 0) is in view and axes aren't glued to the frame.

Whole-number edges: the 8% pad used to leak into labels as ``-11.6`` /
``13.6``. Snap out to integers so school graphs show ``-12`` / ``14``.

Pass ``pad: false`` for vertical lines — the sample window already includes
the origin, and padding ±10 to ±12 makes the axis labels look like the
line's endpoints.
 */
export function expandBoundsForAxes(
  bounds: ReturnType<typeof graphBounds>,
  options?: { pad?: boolean },
): ReturnType<typeof graphBounds> {
  let { xMin, xMax, yMin, yMax } = bounds;
  if (xMin > 0) xMin = 0;
  if (xMax < 0) xMax = 0;
  if (yMin > 0) yMin = 0;
  if (yMax < 0) yMax = 0;
  if (options?.pad !== false) {
    const xSpan = xMax - xMin || 1;
    const ySpan = yMax - yMin || 1;
    xMin = Math.floor(xMin - xSpan * AXIS_PAD_RATIO);
    xMax = Math.ceil(xMax + xSpan * AXIS_PAD_RATIO);
    yMin = Math.floor(yMin - ySpan * AXIS_PAD_RATIO);
    yMax = Math.ceil(yMax + ySpan * AXIS_PAD_RATIO);
  }
  if (xMin >= xMax) xMax = xMin + 1;
  if (yMin >= yMax) yMax = yMin + 1;
  return { xMin, xMax, yMin, yMax };
}

/** API default sample is ±10. ChatGPT-style school graphs zoom to about ±6. */
const TEXTBOOK_HALF_X = 6;
/** Vertex |y| at or above this (e.g. 4x²−5x−12) gets a root-zoomed window. */
export const SHIFTED_VERTEX_MIN = 4;

/** Zero crossings of a sampled y=f(x) curve, interpolated between samples. */
export function graphXIntercepts(points: [number, number][]): number[] {
  const xs: number[] = [];
  for (let i = 1; i < points.length; i += 1) {
    const [x0, y0] = points[i - 1];
    const [x1, y1] = points[i];
    if (!Number.isFinite(y0) || !Number.isFinite(y1) || !Number.isFinite(x0) || !Number.isFinite(x1)) {
      continue;
    }
    if (y0 === 0) {
      if (xs.length === 0 || xs[xs.length - 1] !== x0) xs.push(x0);
      continue;
    }
    if (y0 * y1 < 0) {
      const t = y0 / (y0 - y1);
      xs.push(x0 + t * (x1 - x0));
    } else if (y1 === 0 && i === points.length - 1) {
      xs.push(x1);
    }
  }
  return xs;
}

/** Interior min/max of a dense sample — the vertex of a U, not an arm at the window edge. */
export function interiorVertex(
  points: [number, number][],
): { x: number; y: number } | null {
  if (points.length < 8) return null;
  let minI = 0;
  let maxI = 0;
  for (let i = 1; i < points.length; i += 1) {
    if (points[i][1] < points[minI][1]) minI = i;
    if (points[i][1] > points[maxI][1]) maxI = i;
  }
  const lo = Math.max(1, Math.floor(points.length * 0.08));
  const hi = points.length - 1 - lo;
  const minInterior = minI >= lo && minI <= hi;
  const maxInterior = maxI >= lo && maxI <= hi;
  if (minInterior && (!maxInterior || Math.abs(points[minI][1]) >= Math.abs(points[maxI][1]))) {
    return { x: points[minI][0], y: points[minI][1] };
  }
  if (maxInterior) return { x: points[maxI][0], y: points[maxI][1] };
  return null;
}

function featureWindowAroundVertex(
  points: [number, number][],
): ReturnType<typeof graphBounds> | null {
  const vertex = interiorVertex(points);
  if (!vertex || !(Math.abs(vertex.y) >= SHIFTED_VERTEX_MIN)) return null;
  const intercepts = graphXIntercepts(points);
  if (intercepts.length < 1 || intercepts.length > 3) return null;
  let xLo = Math.min(vertex.x, 0, ...intercepts);
  let xHi = Math.max(vertex.x, 0, ...intercepts);
  const pad = Math.max(1.5, (xHi - xLo) * 0.45);
  xLo -= pad;
  xHi += pad;
  let yLo = Math.min(0, vertex.y);
  let yHi = 0;
  for (const [x, y] of points) {
    if (x >= xLo && x <= xHi && Number.isFinite(y)) {
      yLo = Math.min(yLo, y);
      yHi = Math.max(yHi, y);
    }
  }
  if (!(yHi > 0) || yLo >= yHi) return null;
  return { xMin: xLo, xMax: xHi, yMin: yLo, yMax: yHi };
}

/**
 * View window for a function plot — origin in frame, integer edges.
 *
 * Fitting y = x² on the default ±10 sample makes y run to 100, so the
 * vertex is a spike and 8% pad labels the frame as −12 / 108 / −8.
 * When y is much taller than a 1:1 scale, zoom to a textbook x of ±6
 * and a matching y (about −1…6) so (±1,1) / (±2,4) stay readable.
 *
 * A shifted quadratic (4x²-5x-12, vertex at y≈-13) is different: crop x
 * to the roots and let y run from the vertex up the arms (to ~30), so the
 * U fills the card instead of a ±10 needle with the x-axis at the top.
 */
export function schoolViewBounds(
  data: ReturnType<typeof graphBounds>,
  plotAspect: number,
  points?: [number, number][],
): ReturnType<typeof graphBounds> {
  if (points && points.length >= 8) {
    const feature = featureWindowAroundVertex(points);
    if (feature) {
      return {
        xMin: Math.floor(feature.xMin),
        xMax: Math.ceil(feature.xMax),
        yMin: Math.floor(feature.yMin),
        yMax: Math.ceil(feature.yMax),
      };
    }
  }
  let xMin = Math.min(data.xMin, 0);
  let xMax = Math.max(data.xMax, 0);
  let yMin = Math.min(data.yMin, 0);
  let yMax = Math.max(data.yMax, 0);
  const aspect = Number.isFinite(plotAspect) && plotAspect > 0.3 ? plotAspect : 1.7;
  const xSpan = xMax - xMin || 1;
  const ySpan = yMax - yMin || 1;
  const yUnit = xSpan / aspect;
  // Only crop a sky-high y (x² on ±10 → y=100). A short sample like
  // (0,0)/(1,1)/(2,4) must keep those points on screen.
  if (ySpan > yUnit * 2.5 && ySpan >= 20) {
    const defaultSample =
      xMin <= -9 && xMax >= 9 && xMin >= -12 && xMax <= 12;
    const pathologicalY = ySpan > 1e6;
    if ((defaultSample || pathologicalY) && xMin < 0 && xMax > 0) {
      xMin = -TEXTBOOK_HALF_X;
      xMax = TEXTBOOK_HALF_X;
    }
    const spanY = (xMax - xMin) / aspect;
    if (data.yMin >= -1e-9) {
      yMin = -1;
      yMax = yMin + spanY;
    } else if (data.yMax <= 1e-9) {
      yMax = 1;
      yMin = yMax - spanY;
    } else {
      yMin = -spanY / 2;
      yMax = spanY / 2;
      const clip = Math.max(48, spanY * 4);
      if (data.yMin < yMin && data.yMin > -clip) {
        yMin = data.yMin;
        yMax = Math.max(yMax, 1);
      }
      if (data.yMax > yMax && data.yMax < clip) {
        yMax = data.yMax;
        yMin = Math.min(yMin, -1);
      }
    }
  }
  return {
    xMin: Math.floor(xMin),
    xMax: Math.ceil(xMax),
    yMin: Math.floor(yMin),
    yMax: Math.ceil(yMax),
  };
}

/** Skip 1:1 scale when a tall feature window would expand x into a needle. */
function isTallFeatureWindow(
  bounds: ReturnType<typeof graphBounds>,
  plotAspect: number,
): boolean {
  const xSpan = bounds.xMax - bounds.xMin;
  const ySpan = bounds.yMax - bounds.yMin;
  return xSpan > 0 && ySpan > xSpan * plotAspect * 1.25;
}

/** School crop, then equal-scale — unless that would hide a steep parabola. */
export function functionPlotBounds(
  points: [number, number][],
  extraPoints: [number, number][] | undefined,
  plotAspect: number,
): ReturnType<typeof graphBounds> {
  const data = graphBounds(points, extraPoints);
  const school = schoolViewBounds(
    data,
    plotAspect,
    extraPoints ? undefined : points,
  );
  if (isTallFeatureWindow(school, plotAspect)) return school;
  return equalScaleGraphBounds(school, plotAspect);
}

/** Expand a chosen window so one x unit and one y unit occupy equal pixels. */
export function equalScaleGraphBounds(
  bounds: ReturnType<typeof graphBounds>,
  plotAspect: number,
): ReturnType<typeof graphBounds> {
  const xSpan = bounds.xMax - bounds.xMin;
  const ySpan = bounds.yMax - bounds.yMin;
  if (!(plotAspect > 0) || !Number.isFinite(plotAspect) ||
    !(xSpan > 0) || !(ySpan > 0) ||
    !Number.isFinite(xSpan) || !Number.isFinite(ySpan)) return bounds;
  if (xSpan / ySpan < plotAspect) {
    const extra = (ySpan * plotAspect - xSpan) / 2;
    const xMin = bounds.xMin - extra;
    const xMax = bounds.xMax + extra;
    if (Number.isFinite(xMin) && Number.isFinite(xMax) && Number.isFinite(xMax - xMin)) {
      return { ...bounds, xMin, xMax };
    }
  } else {
    const extra = (xSpan / plotAspect - ySpan) / 2;
    const yMin = bounds.yMin - extra;
    const yMax = bounds.yMax + extra;
    if (Number.isFinite(yMin) && Number.isFinite(yMax) && Number.isFinite(yMax - yMin)) {
      return { ...bounds, yMin, yMax };
    }
  }
  return bounds;
}

/** Even ticks inside a view window (e.g. −6, −4, …, 6). */
export function graphAxisTicks(min: number, max: number, maxCount = 7, fractional = false): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) return [];
  const step = niceStepW((max - min) / Math.max(1, maxCount - 1));
  if (!Number.isFinite(step) || step <= 0) return [];
  const start = Math.ceil((min - 1e-12) / step) * step;
  const ticks: number[] = [];
  const seen = new Set<string>();
  // Extreme finite viewports can round v + step back to v. Keep drawing
  // bounded even when floating-point precision cannot resolve another tick.
  for (let v = start, count = 0; count < 64 && v <= max + step * 1e-9; v += step, count += 1) {
    const n = Math.abs(v) < step * 1e-9 ? 0 : Number(v.toPrecision(12));
    if (n < min - 1e-9 || n > max + 1e-9) continue;
    const key = formatAxisNumber(n, fractional);
    if (seen.has(key)) continue;
    seen.add(key);
    ticks.push(n);
  }
  return ticks;
}

/** School plots use whole labels; explicit fractional viewports retain precision. */
export function formatAxisNumber(n: number, fractional = false): string {
  if (fractional) return Object.is(n, -0) ? "0" : String(Number(n.toPrecision(12)));
  const rounded = Math.round(n);
  return Object.is(rounded, -0) ? "0" : String(rounded);
}

/** Turn integer ``x**2`` / ``x^2`` powers into readable ``x²`` titles. */
export function formatGraphExpr(expr: string): string {
  const src = expr.trim();
  let out = "";
  let i = 0;
  while (i < src.length) {
    if (src.startsWith("Abs(", i) && (i === 0 || !/[A-Za-z0-9_]/.test(src[i - 1]))) {
      let depth = 1;
      let end = i + 4;
      while (end < src.length && depth > 0) {
        if (src[end] === "(") depth += 1;
        else if (src[end] === ")") depth -= 1;
        end += 1;
      }
      const body = src.slice(i + 4, end - 1);
      // Keep nested calls, existing bars, and incomplete syntax verbatim;
      // simple arithmetic inside Abs has an unambiguous bar equivalent.
      if (depth === 0 && body.trim() && /^[A-Za-z0-9_+\-*/^.\s]+$/.test(body)) {
        out += `|${formatGraphExpr(body)}|`;
      } else {
        out += src.slice(i, end);
      }
      i = end;
      continue;
    }
    if (src[i] === "^" || (src[i] === "*" && src[i + 1] === "*")) {
      let j = i + (src[i] === "^" ? 1 : 2);
      let exp = "";
      if (src[j] === "-") {
        exp = "-";
        j += 1;
      }
      while (j < src.length && src[j] >= "0" && src[j] <= "9") {
        exp += src[j];
        j += 1;
      }
      const simpleInteger = exp && !exp.endsWith("-") && src[j] !== "." &&
        src[j] !== "^" && src.slice(j, j + 2) !== "**" && !/^[eE][+-]?\d/.test(src.slice(j));
      const sup = simpleInteger ? toSuperscript(exp) : null;
      if (sup) {
        out += sup;
        i = j;
        continue;
      }
    }
    out += src[i];
    i += 1;
  }
  let stripped = "";
  for (let k = 0; k < out.length; k += 1) {
    const ch = out[k];
    if (ch === "*" && k > 0 && k + 1 < out.length) {
      const prev = out[k - 1];
      const next = out[k + 1];
      const prevOk =
        (prev >= "0" && prev <= "9") ||
        (prev >= "A" && prev <= "Z") ||
        (prev >= "a" && prev <= "z") ||
        prev === ")";
      const nextOk =
        (next >= "A" && next <= "Z") ||
        (next >= "a" && next <= "z") ||
        next === "(";
      if (prevOk && nextOk) continue;
    }
    stripped += ch;
  }
  return stripped;
}

/** `mapPointW` on the JS thread, with the chart's default padding. */
export function mapGraphPoint(
  x: number,
  y: number,
  bounds: ReturnType<typeof graphBounds>,
  width: number,
  height: number,
  pad = 28,
): { px: number; py: number } {
  return mapPointW(x, y, bounds, width, height, pad);
}

export function graphPolylinePoints(
  points: [number, number][],
  width: number,
  height: number,
  // Optional precomputed bounds — required when rendering multiple segments
  // of the same curve, so every segment maps against the same shared axis
  // scale instead of each one being (re)bounded to just its own points.
  bounds: ReturnType<typeof graphBounds> = graphBounds(points),
  pad = 28,
): string {
  return points
    .map(([x, y]) => {
      const { px, py } = mapGraphPoint(x, y, bounds, width, height, pad);
      return `${px},${py}`;
    })
    .join(" ");
}
