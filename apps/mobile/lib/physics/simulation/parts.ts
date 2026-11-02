/** The scene's fixed parts on screen: strings and their supports, the pulley's rope, angle arcs. */
import { bodyEdgeDistance } from "@/lib/physics/simulation/arrows";
import { LABEL_GAP, type LabelBox, type Segment } from "@/lib/physics/simulation/labels";
import { type ScreenPoint } from "@/lib/physics/simulation/viewport";

/** A short hatched bar: the fixed point a string hangs from. */
export type SupportLayout = { bar: Segment; hatches: Segment[] };

/**
 * Where a string ends: at the edge of its body, on the line from its anchor
 * to the body's centre. Null when the anchor is inside the body.
 */
export function tetherEnd(
  anchor: ScreenPoint,
  centre: ScreenPoint,
  radius: number,
  boxAngle: number | null,
): ScreenPoint | null {
  "worklet";
  const dx = centre.px - anchor.px;
  const dy = centre.py - anchor.py;
  const length = Math.hypot(dx, dy);
  if (!(length > 0)) return null;
  const ux = dx / length;
  const uy = dy / length;
  const edge = bodyEdgeDistance(radius, ux, uy, boxAngle);
  if (length <= edge) return null;
  return { px: centre.px - ux * edge, py: centre.py - uy * edge };
}

/** Half the length of a string's support bar, and how far its hatching reaches. */
const SUPPORT_HALF = 12;
const SUPPORT_HATCH = 5;
const SUPPORT_HATCHES = 5;

/**
 * A ceiling (or a wall) for a string to hang from: a bar across the string's
 * line at the anchor, hatched on the side away from the body.
 */
export function supportGeometry(anchor: ScreenPoint, toward: ScreenPoint): SupportLayout {
  const dx = toward.px - anchor.px;
  const dy = toward.py - anchor.py;
  // Snapped to the nearer axis: a pendulum hangs from a level ceiling even
  // when its first sample is the bob at full swing.
  const vertical = Math.abs(dy) >= Math.abs(dx);
  const away = vertical ? (dy >= 0 ? -1 : 1) : dx >= 0 ? -1 : 1;
  const bar: Segment = vertical
    ? { x1: anchor.px - SUPPORT_HALF, y1: anchor.py, x2: anchor.px + SUPPORT_HALF, y2: anchor.py }
    : { x1: anchor.px, y1: anchor.py - SUPPORT_HALF, x2: anchor.px, y2: anchor.py + SUPPORT_HALF };
  const hatches: Segment[] = [];
  for (let i = 0; i < SUPPORT_HATCHES; i += 1) {
    const along = -SUPPORT_HALF + ((i + 0.5) * (SUPPORT_HALF * 2)) / SUPPORT_HATCHES;
    const x = vertical ? anchor.px + along : anchor.px;
    const y = vertical ? anchor.py : anchor.py + along;
    hatches.push(
      vertical
        ? { x1: x, y1: y, x2: x - SUPPORT_HATCH, y2: y + away * SUPPORT_HATCH }
        : { x1: x, y1: y, x2: x + away * SUPPORT_HATCH, y2: y - SUPPORT_HATCH },
    );
  }
  return { bar, hatches };
}

/** Whether a point sits on a pulley's rim (within a pixel and a half). */
export function onPulleyRim(point: ScreenPoint, centre: ScreenPoint, radius: number): boolean {
  return (
    Math.abs(Math.hypot(point.px - centre.px, point.py - centre.py) - radius) <=
    Math.max(1.5, radius * 0.03)
  );
}

/**
 * The rope over the top of a pulley: the arc of the rim between the leftmost
 * and rightmost strings that leave it, the way that passes over the top.
 */
export function pulleyRope(
  centre: ScreenPoint,
  radius: number,
  rim: readonly ScreenPoint[],
): ScreenPoint[] | null {
  if (rim.length < 2) return null;
  const sorted = [...rim].sort((a, b) => a.px - b.px);
  const TAU = Math.PI * 2;
  const angle = (p: ScreenPoint) => {
    const a = Math.atan2(p.py - centre.py, p.px - centre.px);
    return a < 0 ? a + TAU : a;
  };
  let from = angle(sorted[0]);
  let to = angle(sorted[sorted.length - 1]);
  // Screen angles grow clockwise; the top of the wheel is 3π/2.
  if (to <= from) to += TAU;
  const top = Math.PI * 1.5;
  const passesTop = (top >= from && top <= to) || (top + TAU >= from && top + TAU <= to);
  if (!passesTop) [from, to] = [to, from + TAU];
  const steps = Math.max(4, Math.ceil((to - from) / ((6 * Math.PI) / 180)));
  return Array.from({ length: steps + 1 }, (_, i) => {
    const a = from + ((to - from) * i) / steps;
    return { px: centre.px + radius * Math.cos(a), py: centre.py + radius * Math.sin(a) };
  });
}

/** Screen radius of an angle's arc. */
export const ANGLE_RADIUS = 26;
/** A narrow angle's arc is drawn further out, so it is a visible curve rather than a tick... */
const ANGLE_MIN_ARC = 14;
/** ...but never so far out that it stops reading as the angle at its vertex. */
export const ANGLE_MAX_RADIUS = 56;
const ANGLE_STEP_DEG = 4;

/** The signed sweep from `startDeg` to `endDeg`, never more than a full turn. */
export function angleSweep(startDeg: number, endDeg: number): number {
  const sweep = endDeg - startDeg;
  return Math.max(-360, Math.min(360, sweep));
}

export function angleRadius(startDeg: number, endDeg: number): number {
  const sweep = (Math.abs(angleSweep(startDeg, endDeg)) * Math.PI) / 180;
  return Math.max(ANGLE_RADIUS, Math.min(ANGLE_MAX_RADIUS, ANGLE_MIN_ARC / sweep));
}

/** A point on an arc, `deg` counter-clockwise from +x in the world (y up). */
function arcPoint(vertex: ScreenPoint, radius: number, deg: number): ScreenPoint {
  const rad = (deg * Math.PI) / 180;
  return { px: vertex.px + radius * Math.cos(rad), py: vertex.py - radius * Math.sin(rad) };
}

/** An arc from `startDeg` to `endDeg` as a polyline, in steps of a few degrees. */
export function angleArcPoints(
  vertex: ScreenPoint,
  startDeg: number,
  endDeg: number,
  radius: number,
): ScreenPoint[] {
  const sweep = angleSweep(startDeg, endDeg);
  const steps = Math.max(2, Math.ceil(Math.abs(sweep) / ANGLE_STEP_DEG));
  return Array.from({ length: steps + 1 }, (_, i) =>
    arcPoint(vertex, radius, startDeg + (sweep * i) / steps),
  );
}

/** The tip of a moment arrow at `endDeg`, pointing the way the arc turns. */
export function angleArrowHead(
  vertex: ScreenPoint,
  startDeg: number,
  endDeg: number,
  radius: number,
): { tip: ScreenPoint; ux: number; uy: number } {
  const sweep = angleSweep(startDeg, endDeg);
  const end = startDeg + sweep;
  const rad = (end * Math.PI) / 180;
  const turn = sweep > 0 ? 1 : -1;
  // d/dθ of (cos θ, −sin θ), the arc on a y-down screen.
  return {
    tip: arcPoint(vertex, radius, end),
    ux: -Math.sin(rad) * turn,
    uy: -Math.cos(rad) * turn,
  };
}

/** An angle's label box: outside the arc, centred on its middle angle. */
export function angleLabelBox(
  vertex: ScreenPoint,
  startDeg: number,
  endDeg: number,
  radius: number,
  labelWidth: number,
  fontSize: number,
): LabelBox {
  const mid = ((startDeg + angleSweep(startDeg, endDeg) / 2) * Math.PI) / 180;
  const ux = Math.cos(mid);
  const uy = -Math.sin(mid);
  const reach = LABEL_GAP + (Math.abs(ux) * labelWidth) / 2 + (Math.abs(uy) * fontSize) / 2;
  const cx = vertex.px + ux * (radius + reach);
  const cy = vertex.py + uy * (radius + reach);
  return { x: cx - labelWidth / 2, y: cy - fontSize / 2, width: labelWidth, height: fontSize };
}
