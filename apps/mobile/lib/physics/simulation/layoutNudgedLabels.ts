/**
 * The labels nudged apart, most important first: each stated vector's, each
 * angle's and each derived arrow's, from where it wants to be to where it
 * ends up.
 */
import {
  derivedLabelOrigin,
  placedLabel,
  vectorLabelOrigin,
  type LabelBox,
  type PlacedLabel,
} from "@/lib/physics/simulation/labels";
import { separateAcrossFrames, type FrameLabel } from "@/lib/physics/simulation/labelSearch";
import { type SceneFrames } from "@/lib/physics/simulation/layoutFrames";
import {
  linesAt,
  type AngleLayout,
  type AngleShape,
  type DerivedArrow,
  type SceneLines,
  type Shaft,
} from "@/lib/physics/simulation/layoutShapes";
import { angleLabelBox } from "@/lib/physics/simulation/parts";
import { type SimulationArrow, type SimulationVector } from "@/lib/physics/simulation/spec";
import { type ScreenPoint } from "@/lib/physics/simulation/viewport";

export type VectorLayout = {
  vector: SimulationVector;
  from: ScreenPoint;
  tip: ScreenPoint;
  head: number;
  label: PlacedLabel | null;
  /**
   * The body the vector rides on. `from`, `tip` and the label are where it is
   * at the first sample; every frame the renderer starts it where the body
   * has carried `from`, fits it again (`riddenVectorGeometry`) and sets the
   * label from `ride`.
   */
  body: number | null;
  /** For a riding vector: its direction, wanted length and label placement. */
  ride: {
    ux: number;
    uy: number;
    desired: number;
    labelWidth: number;
    mid: boolean;
    side: 1 | -1;
    /** 0 past the tip, or beside the head on its right (1) or left (−1). */
    beside: number;
    /** The nudge that keeps the label clear in every sampled frame. */
    dx: number;
    dy: number;
  } | null;
};

/**
 * A label on a derived arrow. The arrow is worked out every frame, so the
 * label is too: at its tip (`tipLabelOrigin`), moved by (`dx`, `dy`) — the
 * one nudge that keeps it clear in every frame the layout sampled.
 */
export type ArrowLabelLayout = {
  body: number;
  kind: SimulationArrow;
  text: string;
  width: number;
  /** 0 past the tip, or beside the head on its right (1) or left (−1). */
  beside: number;
  dx: number;
  dy: number;
};

type VectorLabelPlan = { labelWidth: number; mid: boolean; side: 1 | -1 } | null;

/** A label that gets nudged. The answer (`result`) is placed first. */
type Wanted = {
  kind: "vector" | "angle" | "derived";
  index: number;
  result: boolean;
  label: FrameLabel;
};

type Outcome = Map<string, ReturnType<typeof separateAcrossFrames>[number]>;

/** How each labelled vector's label is placed: beside its middle, or past its tip. */
export function planVectorLabels(scene: SceneFrames, shafts: Shaft[]): VectorLabelPlan[] {
  const { spec, width, height, measureText, positions } = scene;
  // The middle of the figure, so a side label goes outward rather than into
  // the triangle the vectors make.
  let sumX = 0;
  let sumY = 0;
  let count = 0;
  for (const { from, tip } of shafts) {
    sumX += from.px + tip.px;
    sumY += from.py + tip.py;
    count += 2;
  }
  for (const frames of positions) {
    sumX += frames[0].px;
    sumY += frames[0].py;
    count += 1;
  }
  const centroid =
    count > 0 ? { px: sumX / count, py: sumY / count } : { px: width / 2, py: height / 2 };
  return shafts.map(({ vector, from, ux, uy, desired, frames }) => {
    if (!vector.label) return null;
    const labelWidth = measureText(vector.label);
    const mid =
      vector.role === "measure" || (spec.type === "vector_sum" && vector.role !== "result");
    const tip = frames[0]?.tip ?? { px: from.px + ux * desired, py: from.py + uy * desired };
    let side: 1 | -1 = 1;
    if (mid) {
      const midX = (from.px + tip.px) / 2 - centroid.px;
      const midY = (from.py + tip.py) / 2 - centroid.py;
      side = -uy * midX + ux * midY >= 0 ? 1 : -1;
    }
    return { labelWidth, mid, side };
  });
}

export function wantedVectorLabels(
  scene: SceneFrames,
  shafts: Shaft[],
  plans: VectorLabelPlan[],
  lines: SceneLines,
): Wanted[] {
  const { fontSize, progresses } = scene;
  const wanted: Wanted[] = [];
  shafts.forEach(({ vector, body, frames }, index) => {
    const plan = plans[index];
    if (!plan) return;
    const boxAt = (shaft: (typeof frames)[number], beside: number): LabelBox | null => {
      if (!shaft) return null;
      const origin = vectorLabelOrigin(
        shaft.from.px,
        shaft.from.py,
        shaft.tip.px,
        shaft.tip.py,
        plan.labelWidth,
        fontSize,
        plan.mid,
        plan.side,
        beside,
      );
      return { x: origin.x, y: origin.y, width: plan.labelWidth, height: fontSize };
    };
    // A label beside a middle has one place; one past a tip may also sit beside the head.
    const besides = plan.mid ? [0] : [0, 1, -1];
    wanted.push({
      kind: "vector",
      index,
      result: vector.role === "result",
      label: {
        homes: besides.map((beside) => frames.map((shaft) => boxAt(shaft, beside))),
        // A riding vector is refitted every frame, so its label is placed every frame.
        each: body !== null,
        // Its own line too: a label is past its arrow's tip or beside its
        // middle, and a nudge back onto the arrow would strike it through.
        avoid: progresses.map((_, frame) => linesAt(lines, frame, {})),
      },
    });
  });
  return wanted;
}

export function wantedAngleLabels(
  scene: SceneFrames,
  angleShapes: AngleShape[],
  lines: SceneLines,
): Wanted[] {
  const { measureText, fontSize, progresses } = scene;
  const wanted: Wanted[] = [];
  angleShapes.forEach(({ angle, vertex, radius }, index) => {
    if (!angle.label) return;
    const box = angleLabelBox(
      vertex,
      angle.startDeg,
      angle.endDeg,
      radius,
      measureText(angle.label),
      fontSize,
    );
    wanted.push({
      kind: "angle",
      index,
      result: angle.role === "result",
      label: {
        homes: [progresses.map(() => box)],
        each: false,
        avoid: progresses.map((_, frame) => linesAt(lines, frame, { angle: index })),
      },
    });
  });
  return wanted;
}

export function wantedArrowLabels(
  scene: SceneFrames,
  derived: DerivedArrow[],
  lines: SceneLines,
): Wanted[] {
  const { spec, measureText, fontSize, floorY, obstacles, progresses } = scene;
  const wanted: Wanted[] = [];
  derived.forEach(({ kind, frames }, index) => {
    const text = spec.arrowLabels[kind];
    if (!text) return;
    const labelWidth = measureText(text);
    wanted.push({
      kind: "derived",
      index,
      result: false,
      label: {
        homes: [0, 1, -1].map((beside) =>
          frames.map((arrow) => {
            if (!arrow) return null;
            const origin = derivedLabelOrigin(
              arrow,
              labelWidth,
              fontSize,
              floorY,
              obstacles,
              beside,
            );
            return { x: origin.x, y: origin.y, width: labelWidth, height: fontSize };
          }),
        ),
        each: true,
        // Its own arrow too: pushed back onto the canvas, a label past the tip
        // would sit on the arrowhead it names.
        avoid: progresses.map((_, frame) => linesAt(lines, frame, {})),
      },
    });
  });
  return wanted;
}

/** The answer keeps its place; everything else moves out of its way. */
export function separateLabels(scene: SceneFrames, wanted: Wanted[], fixed: LabelBox[][]): Outcome {
  const { width, height } = scene;
  const order = wanted
    .map((entry, position) => ({ entry, position }))
    .sort((a, b) => Number(b.entry.result) - Number(a.entry.result) || a.position - b.position)
    .map(({ entry }) => entry);
  const separated = separateAcrossFrames(
    order.map((entry) => entry.label),
    fixed,
    width,
    height,
  );
  return new Map(order.map((entry, i) => [`${entry.kind}:${entry.index}`, separated[i]]));
}

export function placeVectorLabels(
  shafts: Shaft[],
  plans: VectorLabelPlan[],
  outcome: Outcome,
): VectorLayout[] {
  return shafts.map(({ vector, from, tip, head, body, ux, uy, desired }, index): VectorLayout => {
    const placement = outcome.get(`vector:${index}`);
    const box = placement?.boxes[0];
    const plan = plans[index];
    return {
      vector,
      from,
      tip,
      head,
      body,
      label: box && vector.label ? placedLabel(vector.label, box) : null,
      ride:
        body === null
          ? null
          : {
              ux,
              uy,
              desired,
              labelWidth: plan?.labelWidth ?? 0,
              mid: plan?.mid ?? false,
              side: plan?.side ?? 1,
              beside: [0, 1, -1][placement?.home ?? 0] ?? 0,
              dx: placement?.dx ?? 0,
              dy: placement?.dy ?? 0,
            },
    };
  });
}

export function placeAngleLabels(angleShapes: AngleShape[], outcome: Outcome): AngleLayout[] {
  return angleShapes.map((shape, index): AngleLayout => {
    const box = outcome.get(`angle:${index}`)?.boxes[0];
    return {
      ...shape,
      label: box && shape.angle.label ? placedLabel(shape.angle.label, box) : null,
    };
  });
}

export function placeArrowLabels(
  scene: SceneFrames,
  derived: DerivedArrow[],
  outcome: Outcome,
): ArrowLabelLayout[] {
  const { spec, measureText } = scene;
  return derived.flatMap(({ body, kind }, index): ArrowLabelLayout[] => {
    const text = spec.arrowLabels[kind];
    const nudge = outcome.get(`derived:${index}`);
    return text && nudge
      ? [
          {
            body,
            kind,
            text,
            width: measureText(text),
            beside: [0, 1, -1][nudge.home] ?? 0,
            dx: nudge.dx,
            dy: nudge.dy,
          },
        ]
      : [];
  });
}
