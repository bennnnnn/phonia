/**
 * Arrows: how long each is drawn, where it leaves its body, and where the
 * canvas, the ground, a solid or a pulley's wheel cuts it short.
 */
import {
  type SimulationArrow,
  type SimulationBody,
  type SimulationSpec,
  type SimulationVector,
  type SimulationVectorRole,
} from "@/lib/physics/simulation/spec";
import { type ScreenPoint } from "@/lib/physics/simulation/viewport";

/**
 * Longest a relative arrow is drawn. Every non-measure vector in a scene is
 * scaled so its largest is this long, and velocity at top speed is too.
 */
export const ARROW_MAX_LENGTH = 48;
/** Shortest a relative force arrow is drawn, so a small load is still an arrow. */
export const ARROW_MIN_LENGTH = 16;
/** Shortest a moving body's velocity arrow is drawn. */
export const VELOCITY_MIN_LENGTH = 12;
export const ARROW_HEAD = 7;
/** Room kept between an arrow's tip and the canvas edge, so its head stays in. */
export const ARROW_EDGE_INSET = 6;

/**
 * Velocity arrow length from speed alone: proportional to how fast the body
 * is moving now against the fastest any body moves in the scene, so the apex
 * of a throw is visibly slower than the launch and the lighter ball visibly
 * faster after a collision. Zero speed draws nothing.
 */
export function velocityArrowLength(speed: number, maxSpeed: number): number {
  "worklet";
  if (!(speed > 0) || !(maxSpeed > 0)) return 0;
  const length = (ARROW_MAX_LENGTH * speed) / maxSpeed;
  return length < VELOCITY_MIN_LENGTH
    ? VELOCITY_MIN_LENGTH
    : length > ARROW_MAX_LENGTH
      ? ARROW_MAX_LENGTH
      : length;
}

/** A vector the scene states at its true world length. */
function drawsAtWorldScale(spec: SimulationSpec, vector: SimulationVector): boolean {
  return spec.type === "vector_sum" || vector.role === "measure";
}

/**
 * On-screen length of each stated vector, in the order the scene lists them.
 *
 * A vector-sum part and a `measure` are geometry, so they keep their world
 * length exactly — a 2 N component next to a 100 N one is meant to be tiny.
 * Everything else is relative: the longest of its kind is drawn at
 * `ARROW_MAX_LENGTH` and the rest in proportion, never shorter than
 * `ARROW_MIN_LENGTH`. Forces and `motion` arrows are normalised separately,
 * since newtons and m/s² share no scale. An old server sent unit vectors,
 * which all come out at the maximum length.
 */
export function vectorScreenLengths(spec: SimulationSpec, scale: number): number[] {
  const largest = { force: 0, motion: 0 };
  for (const vector of spec.vectors) {
    if (drawsAtWorldScale(spec, vector)) continue;
    const family = vector.role === "motion" ? "motion" : "force";
    largest[family] = Math.max(largest[family], Math.hypot(vector.dx, vector.dy));
  }
  return spec.vectors.map((vector) => {
    const magnitude = Math.hypot(vector.dx, vector.dy);
    if (drawsAtWorldScale(spec, vector)) return magnitude * scale;
    const max = largest[vector.role === "motion" ? "motion" : "force"];
    if (!(max > 0) || magnitude >= max) return ARROW_MAX_LENGTH;
    return Math.max(ARROW_MIN_LENGTH, ARROW_MAX_LENGTH * (magnitude / max));
  });
}

/**
 * The longest an arrow from (`fromX`, `fromY`) along the unit direction
 * (`ux`, `uy`) can be while its tip stays `ARROW_EDGE_INSET` inside the canvas — at most
 * `length`. An arrow that leaves the canvas loses its head, and a headless
 * line reads as nothing at all.
 */
export function fitArrowLength(
  fromX: number,
  fromY: number,
  ux: number,
  uy: number,
  length: number,
  width: number,
  height: number,
): number {
  "worklet";
  // Read in the body: a worklet's default parameter does not carry module values to
  // the UI thread, and `inset = ARROW_EDGE_INSET` threw there on every frame.
  const inset = ARROW_EDGE_INSET;
  let fit = length;
  if (ux > 1e-9) fit = Math.min(fit, (width - inset - fromX) / ux);
  else if (ux < -1e-9) fit = Math.min(fit, (inset - fromX) / ux);
  if (uy > 1e-9) fit = Math.min(fit, (height - inset - fromY) / uy);
  else if (uy < -1e-9) fit = Math.min(fit, (inset - fromY) / uy);
  return fit > 0 ? fit : 0;
}

/** A head never longer than about half its arrow. */
export function arrowHeadSize(length: number): number {
  "worklet";
  return Math.min(ARROW_HEAD, length * 0.45);
}

/**
 * How a body's box is turned on screen: onto the slope in an incline scene,
 * upright anywhere else. Null for a circle.
 */
export function bodyBoxAngle(spec: SimulationSpec, body: SimulationBody): number | null {
  if (body.shape !== "box") return null;
  if (spec.type === "incline" && spec.inclineDeg !== undefined) {
    // Descending left to right is clockwise on a y-down screen.
    return (spec.inclineDeg * Math.PI) / 180;
  }
  return 0;
}

/**
 * How far from a body's centre its edge is along the unit direction
 * (`ux`, `uy`). A circle is `radius` every way; a box (a square of side
 * 2 * `radius`, turned `boxAngle` radians on screen) is further out toward its
 * corners, so an arrow leaving a block starts on the block, not inside it.
 */
export function bodyEdgeDistance(
  radius: number,
  ux: number,
  uy: number,
  boxAngle: number | null,
): number {
  "worklet";
  if (boxAngle === null) return radius;
  const c = Math.cos(boxAngle);
  const s = Math.sin(boxAngle);
  const along = Math.abs(ux * c + uy * s);
  const across = Math.abs(-ux * s + uy * c);
  const most = along > across ? along : across;
  return most > 1e-9 ? radius / most : radius;
}

/** Half the width of a body's upright bounding box: where its labels clear it. */
export function bodyExtent(radius: number, boxAngle: number | null): number {
  "worklet";
  if (boxAngle === null) return radius;
  return radius * (Math.abs(Math.cos(boxAngle)) + Math.abs(Math.sin(boxAngle)));
}

/** A derived arrow cut short by the ground or a solid is hidden below this, in px. */
export const MIN_CLIPPED_ARROW = 10;

/**
 * The longest an arrow from (`fromX`, `fromY`) along (`ux`, `uy`) can be — at
 * most `length` — before it reaches the ground line (screen y `floorY`) or
 * enters one of `solids` (screen rects). A weight drawn through the floor, or
 * through the table the ball sits on, says the floor is not there.
 */
export function clipArrowLength(
  fromX: number,
  fromY: number,
  ux: number,
  uy: number,
  length: number,
  floorY: number | null,
  solids: readonly { x: number; y: number; width: number; height: number }[],
): number {
  "worklet";
  let limit = length;
  if (floorY !== null && uy > 1e-9) {
    const reach = (floorY - fromY) / uy;
    if (reach < limit) limit = reach > 0 ? reach : 0;
  }
  for (let i = 0; i < solids.length; i += 1) {
    const box = solids[i];
    // Liang–Barsky: the entry parameter of the shaft into the rect, if any.
    let enter = 0;
    let leave = limit;
    let hits = true;
    const edges = [
      [-ux, fromX - box.x],
      [ux, box.x + box.width - fromX],
      [-uy, fromY - box.y],
      [uy, box.y + box.height - fromY],
    ];
    for (let e = 0; e < 4; e += 1) {
      const p = edges[e][0];
      const q = edges[e][1];
      if (Math.abs(p) < 1e-12) {
        if (q < 0) {
          hits = false;
          break;
        }
        continue;
      }
      const r = q / p;
      if (p < 0) {
        if (r > enter) enter = r;
      } else if (r < leave) {
        leave = r;
      }
      if (enter > leave) {
        hits = false;
        break;
      }
    }
    if (hits && enter < limit) limit = enter;
  }
  return limit;
}

/**
 * Where an arrow the scene derives (rather than states) is drawn this frame:
 * from the body's edge, along a direction read off the scene, shortened to
 * stay on the canvas. Null when there is nothing to draw — a ball at rest has
 * no velocity, and an arrow toward a centre the body sits on has no direction.
 *
 * Velocity is as long as the body is fast (`velocityArrowLength`); the force
 * arrows have no magnitude to show, so they share one length. With a ground
 * line (`floorY`) or solids in the scene the arrow stops where it would enter
 * them, and one cut to under `MIN_CLIPPED_ARROW` is not drawn at all — the
 * weight of a ball resting on the floor is not an arrow into the floor.
 */
export function derivedArrowGeometry(
  kind: SimulationArrow,
  at: ScreenPoint,
  radius: number,
  context: {
    tangent: { dx: number; dy: number };
    maxSpeed: number;
    centre: ScreenPoint | null;
    slope: { normal: { dx: number; dy: number }; friction: { dx: number; dy: number } } | null;
    width: number;
    height: number;
    /** Screen rotation of a box body; null or absent for a circle. */
    boxAngle?: number | null;
    /** Screen y of the ground line, when the scene has one. */
    floorY?: number | null;
    /** Screen rects of the scene's solids (not its fluids). */
    solids?: readonly { x: number; y: number; width: number; height: number }[];
  },
): { fromX: number; fromY: number; ux: number; uy: number; length: number } | null {
  "worklet";
  let dx = 0;
  let dy = 0;
  let length = ARROW_MAX_LENGTH;
  if (kind === "gravity") {
    dy = 1;
  } else if (kind === "velocity") {
    dx = context.tangent.dx;
    dy = context.tangent.dy;
    length = velocityArrowLength(Math.hypot(dx, dy), context.maxSpeed);
  } else if (kind === "centripetal" && context.centre) {
    dx = context.centre.px - at.px;
    dy = context.centre.py - at.py;
  } else if (kind === "normal" && context.slope) {
    dx = context.slope.normal.dx;
    dy = context.slope.normal.dy;
  } else if (kind === "friction" && context.slope) {
    dx = context.slope.friction.dx;
    dy = context.slope.friction.dy;
  }
  const magnitude = Math.hypot(dx, dy);
  if (magnitude === 0 || !(length > 0)) return null;
  const ux = dx / magnitude;
  const uy = dy / magnitude;
  const edge = bodyEdgeDistance(radius, ux, uy, context.boxAngle ?? null);
  // Never past the centre it points at.
  if (kind === "centripetal") length = Math.min(length, magnitude - edge - 2);
  if (!(length > 0)) return null;
  const fromX = at.px + ux * edge;
  const fromY = at.py + uy * edge;
  const fit = fitArrowLength(fromX, fromY, ux, uy, length, context.width, context.height);
  if (!(fit > 0)) return null;
  const clipped = clipArrowLength(
    fromX,
    fromY,
    ux,
    uy,
    fit,
    context.floorY ?? null,
    context.solids ?? [],
  );
  if (clipped < fit && clipped < MIN_CLIPPED_ARROW) return null;
  return { fromX, fromY, ux, uy, length: clipped };
}

/** The fulcrum wedge under a lever's pivot: half-width, and height below the beam. */
export const PIVOT_SIZE = 7;
/** Clear space kept between a load arrow and the wedge. */
const LEVER_PIVOT_GAP = 6;

/**
 * Where a lever load's arrow starts, kept clear of the fulcrum wedge.
 *
 * A load 0.1 m from the pivot sits on the wedge, and the shaft plus the
 * triangle read as a double-headed arrow. A downward load that close is moved
 * just far enough sideways to clear the wedge; its label still states the
 * real arm.
 */
export function leverLoadAnchor(from: ScreenPoint, uy: number, pivot: ScreenPoint): ScreenPoint {
  if (uy <= 0) return from;
  const clear = PIVOT_SIZE + LEVER_PIVOT_GAP;
  const offset = from.px - pivot.px;
  if (Math.abs(offset) >= clear) return from;
  return { px: pivot.px + (offset < 0 ? -clear : clear), py: from.py };
}

/**
 * How far an arrow from (`fromX`, `fromY`) along (`ux`, `uy`) gets — at most
 * `length` — before it meets the circle at (`cx`, `cy`) of `radius`.
 */
export function clipArrowAtCircle(
  fromX: number,
  fromY: number,
  ux: number,
  uy: number,
  length: number,
  cx: number,
  cy: number,
  radius: number,
): number {
  "worklet";
  const ox = cx - fromX;
  const oy = cy - fromY;
  const along = ox * ux + oy * uy;
  if (along <= 0) return length;
  const miss = ox * ox + oy * oy - along * along;
  const reach = radius * radius;
  if (miss > reach) return length;
  const enter = along - Math.sqrt(reach - miss);
  if (enter >= length) return length;
  return enter > 0 ? enter : 0;
}

/**
 * A stated vector riding on a body, this frame: from wherever the body has
 * carried its start, fitted to the canvas, and stopped at a pulley's wheel —
 * the tension along an Atwood rope ends where the rope does. Null when too
 * little of it is left to read.
 */
export function riddenVectorGeometry(
  fromX: number,
  fromY: number,
  ux: number,
  uy: number,
  desired: number,
  width: number,
  height: number,
  wheel: { cx: number; cy: number; radius: number } | null,
): { length: number } | null {
  "worklet";
  let length = fitArrowLength(fromX, fromY, ux, uy, desired, width, height);
  if (wheel) {
    const cut = clipArrowAtCircle(
      fromX,
      fromY,
      ux,
      uy,
      length,
      wheel.cx,
      wheel.cy,
      wheel.radius + 1,
    );
    if (cut < length && cut < MIN_CLIPPED_ARROW) return null;
    length = cut;
  }
  return length > 0 ? { length } : null;
}

/** How a stated vector is drawn. */
type VectorStroke = "force" | "motion" | "measure";

export function vectorStroke(role: SimulationVectorRole): VectorStroke {
  return role === "motion" ? "motion" : role === "measure" ? "measure" : "force";
}
