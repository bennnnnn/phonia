/** An incline's slope on screen: its surface, the wedge under it, and the directions it fixes. */
import { type SimulationSpec } from "@/lib/physics/simulation/spec";
import {
  worldToScreen,
  type ScreenPoint,
  type SimulationTransform,
} from "@/lib/physics/simulation/viewport";

/**
 * The slope's surface, in screen space, extended across the whole scene.
 *
 * Taken from a point the block actually sits on rather than from the scene
 * box, so the line passes under the block instead of near it. The direction
 * comes from the stated angle, which is the only way a *stationary* block's
 * slope can be known at all.
 */
export function inclineSurface(
  spec: SimulationSpec,
  t: SimulationTransform,
): { x1: number; y1: number; x2: number; y2: number } | null {
  if (spec.inclineDeg === undefined || spec.bodies.length === 0) return null;
  const theta = (spec.inclineDeg * Math.PI) / 180;
  const [bx, by] = spec.bodies[0].path[0];
  // The block's centre sits a radius above the surface it rests on, measured
  // along the normal.
  const r = spec.bodies[0].radius;
  const onSurface = { x: bx - r * Math.sin(theta), y: by - r * Math.cos(theta) };

  const slope = -Math.tan(theta); // world dy per dx, descending to the right
  const yAt = (x: number) => onSurface.y + (x - onSurface.x) * slope;
  let x1 = spec.xMin;
  let x2 = spec.xMax;
  // With a ground line the slope ends where it meets the ground, as a wedge
  // does, instead of carrying on beneath the floor.
  if (spec.ground && slope !== 0) {
    const meets = onSurface.x - onSurface.y / slope;
    if (slope < 0) x2 = Math.min(x2, Math.max(x1, meets));
    else x1 = Math.max(x1, Math.min(x2, meets));
  }
  const left = worldToScreen(x1, yAt(x1), t);
  const right = worldToScreen(x2, yAt(x2), t);
  return { x1: left.px, y1: left.py, x2: right.px, y2: right.py };
}

/**
 * The wedge under a slope that stands on the ground: the triangle between the
 * surface, the ground line and the scene's edge, in screen points. Null
 * without a ground line, or when the surface never rises above it.
 */
export function inclineWedge(spec: SimulationSpec, t: SimulationTransform): ScreenPoint[] | null {
  if (!spec.ground) return null;
  const surface = inclineSurface(spec, t);
  if (!surface) return null;
  const floor = worldToScreen(0, 0, t).py;
  const high =
    surface.y1 < surface.y2
      ? { px: surface.x1, py: surface.y1 }
      : { px: surface.x2, py: surface.y2 };
  const low =
    surface.y1 < surface.y2
      ? { px: surface.x2, py: surface.y2 }
      : { px: surface.x1, py: surface.y1 };
  // Something to fill: the high end above the floor, the low end on it.
  if (!(high.py < floor - 0.5) || Math.abs(low.py - floor) > 0.5) return null;
  return [high, low, { px: high.px, py: floor }];
}

/**
 * Screen-space directions fixed by the slope rather than by the motion.
 *
 * Both are perpendicular to each other by construction, so the picture cannot
 * show a normal force that is not normal to the surface it acts on.
 */
export function inclineDirections(inclineDeg: number): {
  normal: { dx: number; dy: number };
  friction: { dx: number; dy: number };
} {
  const theta = (inclineDeg * Math.PI) / 180;
  return {
    // Away from the surface: up and to the right, screen y being downward.
    normal: { dx: Math.sin(theta), dy: -Math.cos(theta) },
    // Up the slope, opposing a block sliding down to the right.
    friction: { dx: -Math.cos(theta), dy: -Math.sin(theta) },
  };
}
