/** Fence types and parsing for ```graph blocks; view math lives in graphBlock.ts. */

export type NumberLineInterval = {
  start: number | null;
  end: number | null;
  start_inclusive: boolean;
  end_inclusive: boolean;
};

type TrajectoryType = "position_vs_time" | "velocity_vs_time" | "parametric";

type SampledGraphSpec = {
  type: "function" | "vertical" | "number_line" | "trajectory";
  expr: string;
  variable?: string;
  x_min?: number;
  x_max?: number;
  /** Learner supplied this x-range; use it for the initial (still movable) view. */
  domain_explicit?: boolean;
  /** Vertical line at this x (when type is "vertical"). */
  x?: number;
  y_min?: number;
  y_max?: number;
  title?: string | null;
  points: [number, number][];
  // points split at a likely discontinuity (e.g. a tan(x) vertical
  // asymptote) — present only when the backend detected a real gap.
  // Undefined/empty means "one continuous curve," same as before this
  // field existed.
  segments?: [number, number][][];
  /** Open points at removable discontinuities in the original function. */
  holes?: [number, number][];
  // Optional second curve for a direct comparison plot ("graph y=x^2 and
  // y=2x on the same axes") — undefined means "single-curve graph," same
  // as every fence before this field existed.
  expr2?: string;
  points2?: [number, number][];
  segments2?: [number, number][][];
  holes2?: [number, number][];
  label?: string;
  label2?: string;
  intervals?: NumberLineInterval[];
  // Trajectory plots (type "trajectory") — pre-computed points from the
  // physics solver. Axis labels render on the SVG.
  x_label?: string;
  y_label?: string;
  trajectory_type?: TrajectoryType;
};

export type InequalityGraphSpec = Omit<SampledGraphSpec, "type"> & {
  type: "inequality";
  /** Verified affine relation: a*x + b*y comparator c. */
  a: number;
  b: number;
  c: number;
  comparator: "<" | "<=" | ">" | ">=";
  x_min: number;
  x_max: number;
  y_min: number;
  y_max: number;
};

export type GraphSpec = SampledGraphSpec | InequalityGraphSpec;

const GRAPH_KIND_SET: Record<GraphSpec["type"], true> = {
  function: true,
  vertical: true,
  number_line: true,
  trajectory: true,
  inequality: true,
};

/** Every graph this build draws; a fence naming another is refused as an unknown kind. */
export const GRAPH_KINDS = Object.keys(GRAPH_KIND_SET);

/** Match backend `GraphBlockSpec.points` max; chat samples default lower. */
const MAX_GRAPH_POINTS = 500;
const MAX_GRAPH_EXPR_LENGTH = 256;

function normalizePoint(raw: unknown): [number, number] | null {
  if (!Array.isArray(raw) || raw.length < 2) return null;
  const x = Number(raw[0]);
  const y = Number(raw[1]);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return [x, y];
}

/** Evenly subsample so oversized backend dumps still draw a smooth curve. */
function downsamplePoints(
  points: [number, number][],
  maxPoints: number,
): [number, number][] {
  if (points.length <= maxPoints || maxPoints < 2) return points;
  const last = points.length - 1;
  const out: [number, number][] = [];
  for (let i = 0; i < maxPoints; i++) {
    const idx = Math.round((i * last) / (maxPoints - 1));
    out.push(points[idx]);
  }
  return out;
}

function parseVerticalGraph(row: Record<string, unknown>): GraphSpec | null {
  const x = Number(row.x);
  if (!Number.isFinite(x)) return null;
  const yMin = Number(row.y_min ?? -10);
  const yMax = Number(row.y_max ?? 10);
  if (!Number.isFinite(yMin) || !Number.isFinite(yMax) || yMax <= yMin) return null;
  const expr = String(row.expr ?? `x = ${x}`).trim() || `x = ${x}`;
  if (expr.length > MAX_GRAPH_EXPR_LENGTH) return null;
  const pointsRaw = row.points;
  let points: [number, number][] = [
    [x, yMin],
    [x, yMax],
  ];
  if (Array.isArray(pointsRaw) && pointsRaw.length >= 2) {
    const parsed = pointsRaw
      .map(normalizePoint)
      .filter((p): p is [number, number] => p != null);
    if (parsed.length >= 2) points = parsed;
  }
  let xMin = Number(row.x_min);
  let xMax = Number(row.x_max);
  if (!Number.isFinite(xMin) || !Number.isFinite(xMax) || xMax <= xMin) {
    if (x > 0) {
      xMin = 0;
      xMax = Math.max(2 * x, 10);
    } else if (x < 0) {
      xMin = Math.min(2 * x, -10);
      xMax = 0;
    } else {
      xMin = -5;
      xMax = 5;
    }
  }
  return {
    type: "vertical",
    expr,
    variable: String(row.variable ?? "x"),
    x,
    y_min: yMin,
    y_max: yMax,
    x_min: xMin,
    x_max: xMax,
    title: row.title != null ? String(row.title) : expr,
    points,
  };
}

function parseBound(raw: unknown): number | null {
  if (raw == null) return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

function parseNumberLineGraph(row: Record<string, unknown>): GraphSpec | null {
  const expr = String(row.expr ?? "").trim();
  if (!expr || expr.length > MAX_GRAPH_EXPR_LENGTH) return null;
  const rawIntervals = Array.isArray(row.intervals) ? row.intervals : [];
  if (rawIntervals.length > 8) return null;
  const intervals: NumberLineInterval[] = [];
  for (const item of rawIntervals) {
    if (!item || typeof item !== "object") return null;
    const iv = item as Record<string, unknown>;
    const start = parseBound(iv.start);
    const end = parseBound(iv.end);
    if (start != null && end != null && start > end) return null;
    intervals.push({
      start,
      end,
      start_inclusive: Boolean(iv.start_inclusive),
      end_inclusive: Boolean(iv.end_inclusive),
    });
  }
  return {
    type: "number_line",
    expr,
    variable: String(row.variable ?? "x"),
    title: row.title != null ? String(row.title) : expr,
    points: [],
    intervals,
  };
}

function parseTrajectoryGraph(row: Record<string, unknown>): GraphSpec | null {
  // Trajectory plots carry pre-computed points (no function sampling).
  // The physics solver already clamped negative heights to 0.
  const points = parsePoints(row.points);
  if (points.length < 2) return null;
  const expr = String(row.expr ?? "").trim();
  return {
    type: "trajectory",
    expr: expr.length > MAX_GRAPH_EXPR_LENGTH ? expr.slice(0, MAX_GRAPH_EXPR_LENGTH) : expr,
    variable: String(row.variable ?? "t"),
    x_min: Number(row.x_min ?? points[0][0]),
    x_max: Number(row.x_max ?? points[points.length - 1][0]),
    title: row.title != null ? String(row.title) : "Trajectory",
    points,
    x_label: row.x_label != null ? String(row.x_label) : undefined,
    y_label: row.y_label != null ? String(row.y_label) : undefined,
    trajectory_type: parseTrajectoryType(row.trajectory_type),
  };
}

/**
 * Validate rather than assert. This was an unchecked `as` cast, which was
 * harmless while nothing read the field — but it now selects which overlay the
 * chart draws, and a gravity arrow drawn across a time axis is worse than none.
 * Unknown values fall back to `undefined` (plain curve), never to a branch.
 */
function parseTrajectoryType(raw: unknown): TrajectoryType | undefined {
  return raw === "position_vs_time" || raw === "velocity_vs_time" || raw === "parametric"
    ? raw
    : undefined;
}

function parseInequalityGraph(row: Record<string, unknown>): InequalityGraphSpec | null {
  const { a, b, c, comparator } = row;
  if (typeof a !== "number" || !Number.isFinite(a) ||
      typeof b !== "number" || !Number.isFinite(b) ||
      typeof c !== "number" || !Number.isFinite(c) || (a === 0 && b === 0)) return null;
  if (comparator !== "<" && comparator !== "<=" && comparator !== ">" && comparator !== ">=") return null;
  const expr = typeof row.expr === "string" ? row.expr.trim() : "";
  if (!expr || expr.length > MAX_GRAPH_EXPR_LENGTH) return null;
  const xMin = row.x_min === undefined ? -10 : row.x_min;
  const xMax = row.x_max === undefined ? 10 : row.x_max;
  const yMin = row.y_min === undefined ? -10 : row.y_min;
  const yMax = row.y_max === undefined ? 10 : row.y_max;
  if (typeof xMin !== "number" || !Number.isFinite(xMin) ||
      typeof xMax !== "number" || !Number.isFinite(xMax) ||
      typeof yMin !== "number" || !Number.isFinite(yMin) ||
      typeof yMax !== "number" || !Number.isFinite(yMax) ||
      xMin >= xMax || yMin >= yMax ||
      !Number.isFinite(xMax - xMin) || !Number.isFinite(yMax - yMin)) return null;
  return {
    type: "inequality", expr, a, b, c, comparator,
    x_min: xMin, x_max: xMax, y_min: yMin, y_max: yMax,
    title: typeof row.title === "string" && row.title.trim() ? row.title.trim() : expr,
    points: [],
  };
}

function parsePoints(raw: unknown): [number, number][] {
  if (!Array.isArray(raw)) return [];
  return downsamplePoints(
    raw.map(normalizePoint).filter((p): p is [number, number] => p != null),
    MAX_GRAPH_POINTS,
  );
}

function parseSegments(raw: unknown): [number, number][][] | undefined {
  if (!Array.isArray(raw) || raw.length > MAX_GRAPH_POINTS) return undefined;
  const parsed = raw
    .map((seg) => (Array.isArray(seg) ? parsePoints(seg) : []))
    .filter((seg) => seg.length > 0);
  // Only meaningful with a real gap (2+ pieces) — a single segment is just
  // `points` again, so leave segments unset and render the plain continuous
  // polyline instead.
  return parsed.length > 1 ? parsed : undefined;
}

function parseHoles(raw: unknown): [number, number][] | null {
  if (raw == null) return [];
  if (!Array.isArray(raw) || raw.length > 8) return null;
  const holes: [number, number][] = [];
  for (const item of raw) {
    const point = normalizePoint(item);
    if (point == null) return null;
    holes.push(point);
  }
  return holes;
}

export function parseGraphSpec(raw: string): GraphSpec | null {
  try {
    const data = JSON.parse(raw.trim()) as unknown;
    if (!data || typeof data !== "object") return null;
    const row = data as Record<string, unknown>;
    if (row.type === "inequality") {
      return parseInequalityGraph(row);
    }
    if (row.type === "vertical") {
      return parseVerticalGraph(row);
    }
    if (row.type === "number_line") {
      return parseNumberLineGraph(row);
    }
    if (row.type === "trajectory") {
      return parseTrajectoryGraph(row);
    }
    if (row.type !== "function") return null;
    const expr = String(row.expr ?? "").trim();
    if (!expr || expr.length > MAX_GRAPH_EXPR_LENGTH) return null;
    const points = parsePoints(row.points);
    // A function curve needs 2+ points to draw a line, but marking a single
    // coordinate ("plot the point (2, 3)") is a single point by definition.
    if (points.length < 1) return null;

    const segments = parseSegments(row.segments);
    const holes = parseHoles(row.holes);
    if (holes == null) return null;

    // Optional second curve — undefined/incomplete means "single-curve
    // graph," same as every fence before this field existed.
    const expr2Raw = row.expr2 != null ? String(row.expr2).trim() : "";
    const points2 = expr2Raw ? parsePoints(row.points2) : [];
    const hasCurve2 = Boolean(expr2Raw) && expr2Raw.length <= MAX_GRAPH_EXPR_LENGTH && points2.length >= 1;
    const holes2 = hasCurve2 ? parseHoles(row.holes2) : [];
    if (holes2 == null) return null;

    return {
      type: "function",
      expr,
      variable: String(row.variable ?? "x"),
      x_min: Number(row.x_min ?? points[0][0]),
      x_max: Number(row.x_max ?? points[points.length - 1][0]),
      domain_explicit: row.domain_explicit === true,
      title: row.title != null ? String(row.title) : null,
      points,
      segments,
      holes: holes.length ? holes : undefined,
      expr2: hasCurve2 ? expr2Raw : undefined,
      points2: hasCurve2 ? points2 : undefined,
      segments2: hasCurve2 ? parseSegments(row.segments2) : undefined,
      holes2: hasCurve2 && holes2.length ? holes2 : undefined,
      label: row.label != null ? String(row.label) : undefined,
      label2: hasCurve2 && row.label2 != null ? String(row.label2) : undefined,
    };
  } catch {
    return null;
  }
}
