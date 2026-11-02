import { type ParallelogramSpec } from "@/lib/math/geometryTypes";

/** Vertices for a triangle drawn from its three side lengths — side `a` laid
 * flat on the x-axis, the third vertex placed via the law of cosines. Callers
 * scale/translate the returned unit-ish coordinates to fit the SVG canvas. */
export function triangleSidesVertices(
  a: number,
  b: number,
  c: number,
): { x0: number; y0: number; x1: number; y1: number; x2: number; y2: number } {
  // The renderer labels p0–p1 as a, p1–p2 as b, and p2–p0 as c.
  const cx = (c * c + a * a - b * b) / (2 * a);
  const cy = Math.sqrt(Math.max(0, c * c - cx * cx));
  return { x0: 0, y0: 0, x1: a, y1: 0, x2: cx, y2: cy };
}

/** Apex sits at a quarter of the base so a base+height triangle is scalene,
 * not an implied isosceles with equal-leg ticks. */
const BASE_HEIGHT_APEX_T = 0.25;

export function baseHeightTriangleVertices(
  base: number,
  height: number,
): { x0: number; y0: number; x1: number; y1: number; x2: number; y2: number } {
  return {
    x0: 0,
    y0: height,
    x1: base,
    y1: height,
    x2: base * BASE_HEIGHT_APEX_T,
    y2: 0,
  };
}

export type TickSegment = { x1: number; y1: number; x2: number; y2: number };

/**
 * Congruence hash marks at the midpoint of a side, perpendicular to it.
 * `count` is the number of parallel ticks (1 / 2 / 3 for distinct equal groups).
 */
export function sideTickMarks(
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  count: number,
  halfLen = 5,
  spacing = 4,
): TickSegment[] {
  if (count <= 0) return [];
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.hypot(dx, dy) || 1;
  const ux = dx / len;
  const uy = dy / len;
  const px = -uy;
  const py = ux;
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  const start = -((count - 1) / 2) * spacing;
  const marks: TickSegment[] = [];
  for (let i = 0; i < count; i++) {
    const ox = mx + ux * (start + i * spacing);
    const oy = my + uy * (start + i * spacing);
    marks.push({
      x1: ox - px * halfLen,
      y1: oy - py * halfLen,
      x2: ox + px * halfLen,
      y2: oy + py * halfLen,
    });
  }
  return marks;
}

/** Tick counts for triangle sides a/b/c — 0 when unique, else 1/2/3 by equal-length group. */
export function equalSideTickCounts(
  a: number,
  b: number,
  c: number,
  eps = 1e-6,
): { a: number; b: number; c: number } {
  const sides: Array<{ key: "a" | "b" | "c"; len: number }> = [
    { key: "a", len: a },
    { key: "b", len: b },
    { key: "c", len: c },
  ];
  const used = new Set<"a" | "b" | "c">();
  const out = { a: 0, b: 0, c: 0 };
  let groupMark = 1;
  for (const side of sides) {
    if (used.has(side.key)) continue;
    const group = sides.filter(
      (other) => Math.abs(other.len - side.len) <= eps,
    );
    if (group.length < 2) {
      used.add(side.key);
      continue;
    }
    for (const member of group) {
      out[member.key] = groupMark;
      used.add(member.key);
    }
    groupMark += 1;
  }
  return out;
}

/** Foot of the perpendicular from C onto the line through A–B (not clamped). */
export function footOfPerpendicular(
  ax: number,
  ay: number,
  bx: number,
  by: number,
  cx: number,
  cy: number,
): { x: number; y: number } {
  const abx = bx - ax;
  const aby = by - ay;
  const ab2 = abx * abx + aby * aby || 1;
  const t = ((cx - ax) * abx + (cy - ay) * aby) / ab2;
  return { x: ax + t * abx, y: ay + t * aby };
}

export function midpoint(
  ax: number,
  ay: number,
  bx: number,
  by: number,
): { x: number; y: number } {
  return { x: (ax + bx) / 2, y: (ay + by) / 2 };
}

/** True when two of the three sides match (isosceles, including equilateral). */
export function isIsoscelesSides(
  a: number,
  b: number,
  c: number,
  eps = 1e-6,
): boolean {
  return (
    Math.abs(a - b) <= eps || Math.abs(a - c) <= eps || Math.abs(b - c) <= eps
  );
}

/** Whether congruence ticks should render (explicit flag, else default on). */
export function shouldShowTicks(
  showTicks: boolean | undefined,
  defaultOn = true,
): boolean {
  if (showTicks === false) return false;
  if (showTicks === true) return true;
  return defaultOn;
}

/** Reserve the entire SVG dimension label plus its gap and a small ink margin. */
export function geometryLabelInset(
  label: string,
  fontSize = 13,
  gap = 8,
  minimum = 40,
): number {
  return Math.max(
    minimum,
    Math.ceil(Array.from(label).length * fontSize * 0.65) + gap + 4,
  );
}

export function scaleToFit(
  width: number,
  height: number,
  maxWidth: number,
  padding = 80,
): { w: number; h: number; scale: number } {
  const inner = Math.max(maxWidth - padding, 1);
  const scale = inner / Math.max(width, height, 1);
  return { w: width * scale, h: height * scale, scale };
}

/** Horizontal span of a parallelogram: base plus the shear of the slanted side. */
function parallelogramSpan(
  base: number,
  height: number,
  side: number,
): number {
  const shear = Math.sqrt(Math.max(0, side * side - height * height));
  return base + shear;
}

type ParallelogramLayout = {
  b: number;
  h: number;
  s: number;
  shear: number;
  offsetX: number;
  offsetY: number;
  svgW: number;
  svgH: number;
  bx0: number;
  bx1: number;
  by: number;
  tx0: number;
  tx1: number;
  ty: number;
};

/**
 * Fit a parallelogram into the bubble. Scale against `base + shear` (the
 * drawn width), not `max(base, side)` — otherwise the SVG is ~1.5–2× too
 * wide and `alignItems: "center"` clips both slanted ends.
 */
export function parallelogramLayout(
  spec: Pick<ParallelogramSpec, "base" | "height" | "side">,
  screenWidth: number,
  padding: { left: number; right: number } = { left: 40, right: 40 },
): ParallelogramLayout {
  const inner = Math.max(screenWidth - 48 - padding.left - padding.right, 1);
  const span = parallelogramSpan(spec.base, spec.height, spec.side);
  const scale = inner / Math.max(span, spec.height, 1);
  const b = spec.base * scale;
  const h = spec.height * scale;
  const s = spec.side * scale;
  const shear = Math.sqrt(Math.max(0, s * s - h * h));
  const offsetX = padding.left + shear;
  const offsetY = 28;
  // Leftmost point is tx0 = padding.left; rightmost is bx1 = offsetX + b.
  // Do not add shear again — offsetX already contains it.
  const svgW = b + shear + padding.left + padding.right;
  const svgH = h + offsetY + 52;
  const bx0 = offsetX;
  const bx1 = offsetX + b;
  const by = offsetY + h;
  const tx0 = offsetX - shear;
  const tx1 = tx0 + b;
  const ty = offsetY;
  return {
    b,
    h,
    s,
    shear,
    offsetX,
    offsetY,
    svgW,
    svgH,
    bx0,
    bx1,
    by,
    tx0,
    tx1,
    ty,
  };
}
