/**
 * The shapes `layoutSimulationScene` places before any label, each at every
 * frame it checks, and the lines a label then has to stay off.
 */
import {
  arrowHeadSize,
  ARROW_HEAD,
  bodyEdgeDistance,
  derivedArrowGeometry,
  fitArrowLength,
  leverLoadAnchor,
  riddenVectorGeometry,
  vectorScreenLengths,
} from "@/lib/physics/simulation/arrows";
import { inclineDirections } from "@/lib/physics/simulation/incline";
import {
  polylineSegments,
  segmentOf,
  type PlacedLabel,
  type Segment,
} from "@/lib/physics/simulation/labels";
import { type SceneFrames } from "@/lib/physics/simulation/layoutFrames";
import {
  angleArcPoints,
  angleArrowHead,
  angleRadius,
  angleSweep,
  onPulleyRim,
  pulleyRope,
  supportGeometry,
  tetherEnd,
  type SupportLayout,
} from "@/lib/physics/simulation/parts";
import { isStationary, tangentAt } from "@/lib/physics/simulation/paths";
import {
  type SimulationAngle,
  type SimulationArrow,
  type SimulationVector,
} from "@/lib/physics/simulation/spec";
import { worldToScreen, type ScreenPoint } from "@/lib/physics/simulation/viewport";

/** An angle's arc, its head when it is a moment arrow, and its label. */
export type AngleLayout = {
  angle: SimulationAngle;
  vertex: ScreenPoint;
  radius: number;
  /** The arc as a polyline; a moment arrow's stops short of its head. */
  arc: ScreenPoint[];
  head: { tip: ScreenPoint; ux: number; uy: number; size: number } | null;
  label: PlacedLabel | null;
};

export type TetherLayout = {
  anchor: ScreenPoint;
  body: number;
  /** Null when the string leaves a pulley's rim, which is its support. */
  support: SupportLayout | null;
};

export type PulleyLayout = {
  centre: ScreenPoint;
  radius: number;
  /** The rope over the top of the wheel, between the strings that leave its rim. */
  rope: ScreenPoint[] | null;
};

/** A stated vector on screen at the first frame, and where its shaft runs at each frame. */
export type Shaft = {
  vector: SimulationVector;
  from: ScreenPoint;
  tip: ScreenPoint;
  head: number;
  body: number | null;
  ux: number;
  uy: number;
  desired: number;
  frames: ({ from: ScreenPoint; tip: ScreenPoint } | null)[];
};

/** A derived arrow of one body, at each frame. */
export type DerivedArrow = {
  body: number;
  kind: SimulationArrow;
  frames: ReturnType<typeof derivedArrowGeometry>[];
};

/** An angle before its label is placed. */
export type AngleShape = Omit<AngleLayout, "label">;

/** Every line a label might sit on, at each frame. */
export type SceneLines = {
  vectorLines: (Segment | null)[][];
  derivedLines: (Segment | null)[][];
  tetherLines: (Segment | null)[][];
  restLines: Segment[];
  arcLines: Segment[][];
};

function unit(dx: number, dy: number): { ux: number; uy: number } {
  const length = Math.hypot(dx, dy) || 1;
  return { ux: dx / length, uy: dy / length };
}

/** Where a stated vector starts at the first frame. */
function shaftStart(
  scene: SceneFrames,
  vector: SimulationVector,
  ux: number,
  uy: number,
  pivot: ScreenPoint | null,
): ScreenPoint {
  const { spec, transform, radii, boxAngles, positions } = scene;
  const body = vector.body ?? null;
  let from: ScreenPoint;
  let onBody: number | null = null;
  if (body !== null) {
    // Riding on a body: the anchor is an offset from where it is.
    const [bx, by] = spec.bodies[body].path[0];
    from = worldToScreen(bx + vector.anchor.x, by + vector.anchor.y, transform);
    if (Math.hypot(vector.anchor.x, vector.anchor.y) * transform.scale < 0.5) onBody = body;
  } else {
    from = worldToScreen(vector.anchor.x, vector.anchor.y, transform);
    if (pivot) from = leverLoadAnchor(from, uy, pivot);
    // A body is drawn over the arrows that start at its centre, so an arrow
    // anchored on a still body starts at its edge instead: the part you see
    // is then the whole length, and two forces keep their proportions.
    const still = spec.bodies.findIndex(
      (candidate, i) =>
        isStationary(candidate) &&
        Math.hypot(positions[i][0].px - from.px, positions[i][0].py - from.py) < 0.5,
    );
    if (still >= 0) onBody = still;
  }
  if (onBody !== null) {
    const edge = bodyEdgeDistance(radii[onBody], ux, uy, boxAngles[onBody]);
    from = { px: from.px + ux * edge, py: from.py + uy * edge };
  }
  return from;
}

export function layoutVectors(scene: SceneFrames): {
  shafts: Shaft[];
  vectorLines: (Segment | null)[][];
} {
  const { spec, transform, width, height, progresses, shifts, pulleyCentre, pulleyRadius } = scene;
  const pivot =
    spec.pivot && spec.beam ? worldToScreen(spec.pivot.x, spec.pivot.y, transform) : null;
  const lengths = vectorScreenLengths(spec, transform.scale);
  const wheel = pulleyCentre
    ? { cx: pulleyCentre.px, cy: pulleyCentre.py, radius: pulleyRadius }
    : null;
  const shafts = spec.vectors.map((vector, index) => {
    // World y is up and screen y is down.
    const { ux, uy } = unit(vector.dx, -vector.dy);
    const body = vector.body ?? null;
    const from = shaftStart(scene, vector, ux, uy, pivot);
    const desired = lengths[index];
    const still = fitArrowLength(from.px, from.py, ux, uy, desired, width, height);
    /** Where the shaft runs at each frame; null where too little of it is left to draw. */
    const frames = progresses.map((_, frame) => {
      if (body === null) {
        return { from, tip: { px: from.px + ux * still, py: from.py + uy * still } };
      }
      const { dx, dy } = shifts[body][frame];
      const start = { px: from.px + dx, py: from.py + dy };
      const ride = riddenVectorGeometry(start.px, start.py, ux, uy, desired, width, height, wheel);
      return ride
        ? { from: start, tip: { px: start.px + ux * ride.length, py: start.py + uy * ride.length } }
        : null;
    });
    const first = frames[0];
    const tip = first ? first.tip : from;
    const length = Math.hypot(tip.px - from.px, tip.py - from.py);
    return { vector, from, tip, head: arrowHeadSize(length), body, ux, uy, desired, frames };
  });
  /** Each stated vector's shaft at each frame. */
  const vectorLines = shafts.map(({ frames }) =>
    frames.map((shaft) => (shaft ? segmentOf(shaft.from, shaft.tip) : null)),
  );
  return { shafts, vectorLines };
}

export function layoutDerivedArrows(scene: SceneFrames): {
  derived: DerivedArrow[];
  derivedLines: (Segment | null)[][];
} {
  const { spec, width, height, radii, boxAngles, tracks, closed, maxSpeed } = scene;
  const { floorY, obstacles, centre, progresses, positions } = scene;
  const slope = spec.inclineDeg !== undefined ? inclineDirections(spec.inclineDeg) : null;
  const derived = spec.bodies.flatMap((_, body) =>
    spec.arrows.map((kind) => ({
      body,
      kind,
      frames: progresses.map((progress, frame) =>
        derivedArrowGeometry(kind, positions[body][frame], radii[body], {
          tangent:
            kind === "velocity"
              ? tangentAt(tracks[body], progress, closed[body])
              : { dx: 0, dy: 0 },
          maxSpeed,
          centre,
          slope,
          width,
          height,
          boxAngle: boxAngles[body],
          floorY,
          solids: obstacles,
        }),
      ),
    })),
  );
  const derivedLines = derived.map(({ frames }) =>
    frames.map((arrow) =>
      arrow
        ? {
            x1: arrow.fromX,
            y1: arrow.fromY,
            x2: arrow.fromX + arrow.ux * arrow.length,
            y2: arrow.fromY + arrow.uy * arrow.length,
          }
        : null,
    ),
  );
  return { derived, derivedLines };
}

export function layoutTethers(scene: SceneFrames): {
  tethers: TetherLayout[];
  restLines: Segment[];
  tetherLines: (Segment | null)[][];
  pulley: PulleyLayout | null;
} {
  const { spec, transform, radii, boxAngles, progresses, positions } = scene;
  const { pulleyCentre, pulleyRadius } = scene;
  const tethers: TetherLayout[] = spec.tethers.map((tether) => {
    const anchor = worldToScreen(tether.anchor.x, tether.anchor.y, transform);
    const rim = pulleyCentre !== null && onPulleyRim(anchor, pulleyCentre, pulleyRadius);
    return {
      anchor,
      body: tether.body,
      support: rim ? null : supportGeometry(anchor, positions[tether.body][0]),
    };
  });
  // A pendulum's rest line: straight down from the pivot, as long as the
  // string. The angle it swings through is measured from it.
  const restLines: Segment[] =
    spec.type === "pendulum"
      ? tethers.map(({ anchor, body }) => {
          const bob = positions[body][0];
          const length = Math.hypot(bob.px - anchor.px, bob.py - anchor.py);
          return { x1: anchor.px, y1: anchor.py, x2: anchor.px, y2: anchor.py + length };
        })
      : [];
  const tetherLines = tethers.map(({ anchor, body }) =>
    progresses.map((_, frame) => {
      const end = tetherEnd(anchor, positions[body][frame], radii[body], boxAngles[body]);
      return end ? segmentOf(anchor, end) : null;
    }),
  );
  const pulley: PulleyLayout | null = pulleyCentre
    ? {
        centre: pulleyCentre,
        radius: pulleyRadius,
        rope: pulleyRope(
          pulleyCentre,
          pulleyRadius,
          tethers.filter((tether) => tether.support === null).map((tether) => tether.anchor),
        ),
      }
    : null;
  return { tethers, restLines, tetherLines, pulley };
}

export function layoutAngles(scene: SceneFrames): {
  angleShapes: AngleShape[];
  arcLines: Segment[][];
} {
  const { spec, transform } = scene;
  const angleShapes = spec.angles.map((angle) => {
    const vertex = worldToScreen(angle.vertex.x, angle.vertex.y, transform);
    const radius = angleRadius(angle.startDeg, angle.endDeg);
    let arc = angleArcPoints(vertex, angle.startDeg, angle.endDeg, radius);
    let head: AngleLayout["head"] = null;
    if (angle.arrow) {
      const end = angleArrowHead(vertex, angle.startDeg, angle.endDeg, radius);
      head = { ...end, size: ARROW_HEAD };
      // Stop the stroke under the head, so its round cap does not poke through.
      const sweep = angleSweep(angle.startDeg, angle.endDeg);
      const short = ((ARROW_HEAD * 0.6) / radius) * (180 / Math.PI) * (sweep > 0 ? 1 : -1);
      if (Math.abs(short) < Math.abs(sweep)) {
        arc = angleArcPoints(vertex, angle.startDeg, angle.startDeg + sweep - short, radius);
      }
    }
    return { angle, vertex, radius, arc, head };
  });
  const arcLines = angleShapes.map(({ arc, head }) => [
    ...polylineSegments(arc),
    ...(head ? [segmentOf(arc[arc.length - 1], head.tip)] : []),
  ]);
  return { angleShapes, arcLines };
}

/** Every line a label must stay off at `frame`, leaving out its own. */
export function linesAt(
  sceneLines: SceneLines,
  frame: number,
  skip: { vector?: number; derived?: number; angle?: number },
): Segment[] {
  const { vectorLines, derivedLines, tetherLines, restLines, arcLines } = sceneLines;
  const lines: Segment[] = [];
  vectorLines.forEach((frames, i) => {
    const line = frames[frame];
    if (i !== skip.vector && line) lines.push(line);
  });
  derivedLines.forEach((frames, i) => {
    const line = frames[frame];
    if (i !== skip.derived && line) lines.push(line);
  });
  for (const frames of tetherLines) {
    const line = frames[frame];
    if (line) lines.push(line);
  }
  lines.push(...restLines);
  arcLines.forEach((segments, i) => {
    if (i !== skip.angle) lines.push(...segments);
  });
  return lines;
}
