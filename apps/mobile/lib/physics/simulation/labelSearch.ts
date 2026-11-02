/**
 * Keeping labels clear across the frames the layout checks: the side a
 * body's label takes, and how far every other label is nudged.
 */
import { boxesOverlap } from "@/lib/physics/boxes";
import { type SimulationBody } from "@/lib/physics/simulation/spec";
import {
  bodyLabelOffset,
  clampBox,
  segmentHitsBox,
  type BodyLabelSide,
  type LabelBox,
  type Segment,
} from "@/lib/physics/simulation/labels";
import { type ScreenPoint } from "@/lib/physics/simulation/viewport";

/** Room kept between a label and another arrow's line, in px. */
const LINE_CLEARANCE = 4;

function inflateBox(box: LabelBox, by: number): LabelBox {
  return { x: box.x - by, y: box.y - by, width: box.width + by * 2, height: box.height + by * 2 };
}

/** Furthest a label is nudged from where it wants to be, in px. */
const MAX_NUDGE = 48;
const NUDGE_STEP = 2;

/** Room kept between a body's label and any line, in px (on top of the 1 px margin). */
const BODY_LABEL_CLEARANCE = 2;

/**
 * The first side, in the body's order of preference, where its label crosses
 * no arrow and fits on the canvas. The primary body prefers above and a
 * secondary body below, so a pair of bodies never shares a label line.
 *
 * For a body that moves, the label rides along at one offset, so a side is
 * only clear if it is clear at every sampled position
 * (`centres[k]`, against `obstacles[k]`) — a pendulum bob's label beside it
 * would sit on its own track as it swings through the bottom. The corners are
 * the last resort; when nothing is clear all the way through, the side clear
 * for the most frames wins.
 */
export function chooseBodyLabelSideAcrossFrames(
  centres: readonly ScreenPoint[],
  radius: number,
  labelWidth: number,
  fontSize: number,
  role: SimulationBody["role"],
  obstacles: readonly (readonly Segment[])[],
  width: number,
  height: number,
): BodyLabelSide {
  const order: BodyLabelSide[] =
    role === "secondary"
      ? [
          "below",
          "above",
          "right",
          "left",
          "below-right",
          "below-left",
          "above-right",
          "above-left",
        ]
      : [
          "above",
          "below",
          "right",
          "left",
          "above-right",
          "above-left",
          "below-right",
          "below-left",
        ];
  const conflicts = (side: BodyLabelSide) => {
    const offset = bodyLabelOffset(side, radius, labelWidth, fontSize);
    let count = 0;
    for (let frame = 0; frame < centres.length; frame += 1) {
      const centre = centres[frame];
      let box = {
        x: centre.px + offset.dx - 1,
        y: centre.py + offset.dy - 1,
        width: labelWidth + 2,
        height: fontSize + 2,
      };
      if (frame === 0) {
        const inside =
          box.x >= 0 && box.y >= 0 && box.x + box.width <= width && box.y + box.height <= height;
        if (!inside) return Infinity;
      } else {
        // Later frames keep the label on the canvas, as the renderer does.
        box = clampBox(box, width, height, 0);
      }
      // A little more room than the glyphs: an end tick or an arrowhead
      // reaches past its line.
      const room = inflateBox(box, BODY_LABEL_CLEARANCE);
      if ((obstacles[frame] ?? []).some((segment) => segmentHitsBox(segment, room))) count += 1;
    }
    return count;
  };
  let best: BodyLabelSide = order[0];
  let fewest = Infinity;
  for (const side of order) {
    const count = conflicts(side);
    if (count === 0) return side;
    if (count < fewest) {
      fewest = count;
      best = side;
    }
  }
  return best;
}

export type FrameLabel = {
  /**
   * The home box at each sampled frame, null where the label is not drawn —
   * for each place the label may go, in order of preference: past an arrow's
   * tip first, then beside its head on either side.
   */
  homes: (LabelBox | null)[][];
  /**
   * Each frame's box is placed on its own (a derived arrow's label, worked out
   * every frame), or the first frame's box is placed and the rest ride along
   * by the same offset (a label on a body-borne vector, moved as a whole).
   */
  each: boolean;
  avoid: Segment[][];
};

function shiftBox(box: LabelBox, dx: number, dy: number): LabelBox {
  return { ...box, x: box.x + dx, y: box.y + dy };
}

/** What a clash in the first frame costs: that frame is the still picture Reduce Motion shows. */
const FIRST_FRAME_CLASH = 1000;
/** Pixels of nudge worth one later frame of overlap. */
const NUDGE_PER_FRAME = 8;
/** What leaving the tip for the side of the head costs, in the same points (12 px of nudge). */
const ALTERNATE_HOME = 1.5;

/**
 * Nudge labels apart across time, straight along one axis and on the canvas.
 * Each label, in priority order, tries the same
 * nudges in the same order and keeps the cheapest: a clash with anything
 * placed before it, or with a line it must avoid, costs a lot in the first
 * frame (the still picture) and one point in any later frame, and every
 * `NUDGE_PER_FRAME` px of nudge costs a point. A label riding on a body thus
 * stays at its arrow's tip and only gives way where it would be covered for
 * much of the motion.
 */
export function separateAcrossFrames(
  labels: readonly FrameLabel[],
  fixed: readonly LabelBox[][],
  width: number,
  height: number,
  gap = 2,
): { home: number; dx: number; dy: number; boxes: (LabelBox | null)[] }[] {
  const frames = fixed.length;
  const placed: LabelBox[][] = fixed.map((boxes) => [...boxes]);
  return labels.map((label) => {
    const candidate = (home: (LabelBox | null)[], dx: number, dy: number): (LabelBox | null)[] => {
      const first = home.find((box) => box !== null) ?? null;
      return home.map((box) => {
        if (!box) return null;
        if (label.each || !first)
          return clampBox(shiftBox(clampBox(box, width, height), dx, dy), width, height);
        const moved = clampBox(shiftBox(clampBox(first, width, height), dx, dy), width, height);
        return shiftBox(moved, box.x - first.x, box.y - first.y);
      });
    };
    const clashes = (boxes: (LabelBox | null)[]) => {
      let cost = 0;
      boxes.forEach((box, frame) => {
        if (!box || frame >= frames) return;
        const lines = label.avoid[frame] ?? [];
        const clash =
          placed[frame].some((other) => boxesOverlap(box, other, gap)) ||
          lines.some((line) => segmentHitsBox(line, inflateBox(box, LINE_CLEARANCE)));
        if (clash) cost += frame === 0 ? FIRST_FRAME_CLASH : 1;
      });
      return cost;
    };
    let choice = { home: 0, dx: 0, dy: 0 };
    let boxes = candidate(label.homes[0] ?? [], 0, 0);
    let best = clashes(boxes);
    label.homes.forEach((home, index) => {
      const penalty = index === 0 ? 0 : ALTERNATE_HOME;
      if (penalty >= best) return;
      const atHome = candidate(home, 0, 0);
      const cost = clashes(atHome) + penalty;
      if (cost < best) {
        best = cost;
        choice = { home: index, dx: 0, dy: 0 };
        boxes = atHome;
      }
      for (let step = NUDGE_STEP; step <= MAX_NUDGE; step += NUDGE_STEP) {
        // Nothing further out can beat what is already in hand.
        if (penalty + step / NUDGE_PER_FRAME >= best) break;
        for (const [dx, dy] of [
          [0, step],
          [0, -step],
          [step, 0],
          [-step, 0],
        ]) {
          const moved = candidate(home, dx, dy);
          const total = clashes(moved) + penalty + step / NUDGE_PER_FRAME;
          if (total < best) {
            best = total;
            choice = { home: index, dx, dy };
            boxes = moved;
          }
        }
      }
    });
    boxes.forEach((box, frame) => {
      if (box && frame < frames) placed[frame].push(box);
    });
    return { ...choice, boxes };
  });
}
