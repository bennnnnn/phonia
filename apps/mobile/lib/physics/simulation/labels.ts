/**
 * Where a label goes: its box, the gap it keeps from what it names, and the
 * origins the renderer works out every frame for a label that moves.
 */
import { type Box } from "@/lib/physics/boxes";
import { ARROW_HEAD } from "@/lib/physics/simulation/arrows";
import { type ScreenPoint } from "@/lib/physics/simulation/viewport";

/**
 * Gap between a label and the thing it names. Declared above every worklet
 * that reads it: a worklet captures its constants where it is defined.
 */
export const LABEL_GAP = 6;

/**
 * How far along the unit direction (`ux`, `uy`) a `labelWidth` × `fontSize`
 * box's centre has to be from a point for the box to stay `gap` clear of it.
 * Clearing the point rather than a line across it is what lets a wide label
 * on a slanted arrow sit beside its tip instead of a label-width away.
 */
export function clearanceAlong(
  ux: number,
  uy: number,
  labelWidth: number,
  fontSize: number,
  gap: number,
): number {
  "worklet";
  const a = Math.abs(ux);
  const b = Math.abs(uy);
  const halfW = labelWidth / 2;
  const halfH = fontSize / 2;
  const away = (t: number) => {
    const dx = a * t - halfW;
    const dy = b * t - halfH;
    return Math.hypot(dx > 0 ? dx : 0, dy > 0 ? dy : 0);
  };
  // The support distance always clears it; bisect down to the least that does.
  let high = gap + a * halfW + b * halfH;
  let low = 0;
  for (let i = 0; i < 24; i += 1) {
    const mid = (low + high) / 2;
    if (away(mid) >= gap) high = mid;
    else low = mid;
  }
  return high;
}

/**
 * Top-left of a label box just past an arrow's tip, centred on its line: the
 * same placement `vectorLabelOrigin` gives a stated arrow, as a worklet so a
 * derived arrow's label can follow its tip every frame.
 */
export function tipLabelOrigin(
  tipX: number,
  tipY: number,
  ux: number,
  uy: number,
  labelWidth: number,
  fontSize: number,
): { x: number; y: number } {
  "worklet";
  const reach = clearanceAlong(ux, uy, labelWidth, fontSize, LABEL_GAP);
  return {
    x: tipX + ux * reach - labelWidth / 2,
    y: tipY + uy * reach - fontSize / 2,
  };
}

/**
 * Top-left of a label box beside an arrow's head rather than past it: on the
 * right of the arrow for `side` 1 (below, for a level one), the left for −1.
 * Where something already sits past the tip, the head is the next place a
 * reader looks for the arrow's name.
 */
function besideHeadOrigin(
  tipX: number,
  tipY: number,
  ux: number,
  uy: number,
  length: number,
  labelWidth: number,
  fontSize: number,
  side: number,
): { x: number; y: number } {
  "worklet";
  let nx = -uy;
  let ny = ux;
  if (nx < 0 || (nx === 0 && ny < 0)) {
    nx = -nx;
    ny = -ny;
  }
  if (side < 0) {
    nx = -nx;
    ny = -ny;
  }
  const back = Math.min(ARROW_HEAD, length / 2);
  const reach = LABEL_GAP + (Math.abs(nx) * labelWidth) / 2 + (Math.abs(ny) * fontSize) / 2;
  return {
    x: tipX - ux * back + nx * reach - labelWidth / 2,
    y: tipY - uy * back + ny * reach - fontSize / 2,
  };
}

/** Whether a label box from `origin` overlaps any of the solids. Declared before its
 * caller: a worklet captures what it names when it is made, so a later one is undefined. */
function overlapsAny(
  origin: { x: number; y: number },
  labelWidth: number,
  fontSize: number,
  solids: readonly { x: number; y: number; width: number; height: number }[],
): boolean {
  "worklet";
  for (let i = 0; i < solids.length; i += 1) {
    const box = solids[i];
    if (
      origin.x < box.x + box.width &&
      box.x < origin.x + labelWidth &&
      origin.y < box.y + box.height &&
      box.y < origin.y + fontSize
    ) {
      return true;
    }
  }
  return false;
}

/**
 * Where a derived arrow's label goes this frame: just past its tip, unless
 * that is in the ground or a solid — the weight of a ball about to land, or
 * resting on a table — and then beside the head, on its right, or on its left
 * when a solid takes the right too.
 */
export function derivedLabelOrigin(
  arrow: { fromX: number; fromY: number; ux: number; uy: number; length: number },
  labelWidth: number,
  fontSize: number,
  floorY: number | null,
  solids: readonly { x: number; y: number; width: number; height: number }[],
  beside = 0,
): { x: number; y: number } {
  "worklet";
  const tipX = arrow.fromX + arrow.ux * arrow.length;
  const tipY = arrow.fromY + arrow.uy * arrow.length;
  if (beside !== 0) {
    return besideHeadOrigin(
      tipX,
      tipY,
      arrow.ux,
      arrow.uy,
      arrow.length,
      labelWidth,
      fontSize,
      beside,
    );
  }
  const past = tipLabelOrigin(tipX, tipY, arrow.ux, arrow.uy, labelWidth, fontSize);
  const inGround = floorY !== null && tipY <= floorY + 0.5 && past.y + fontSize > floorY;
  if (!inGround && !overlapsAny(past, labelWidth, fontSize, solids)) return past;
  const right = besideHeadOrigin(tipX, tipY, arrow.ux, arrow.uy, arrow.length, labelWidth, fontSize, 1);
  if (!overlapsAny(right, labelWidth, fontSize, solids)) return right;
  const left = besideHeadOrigin(tipX, tipY, arrow.ux, arrow.uy, arrow.length, labelWidth, fontSize, -1);
  return overlapsAny(left, labelWidth, fontSize, solids) ? right : left;
}

/** A label's box: left, top, width and height in canvas pixels. */
export type LabelBox = Box;

/** Skia text is drawn from its baseline, about this far down a line. */
export const LABEL_ASCENT = 0.8;

/** The baseline Skia draws a label at, for a label's box. */
function labelBaseline(box: LabelBox): number {
  return box.y + box.height * LABEL_ASCENT;
}

export function clampBox(box: LabelBox, width: number, height: number, inset = 4): LabelBox {
  const x = Math.max(inset, Math.min(width - inset - box.width, box.x));
  const y = Math.max(inset, Math.min(height - inset - box.height, box.y));
  return { ...box, x, y };
}

export type Segment = { x1: number; y1: number; x2: number; y2: number };

/** Whether a line segment passes through a box (Liang–Barsky clip). */
export function segmentHitsBox(segment: Segment, box: LabelBox): boolean {
  const dx = segment.x2 - segment.x1;
  const dy = segment.y2 - segment.y1;
  let t0 = 0;
  let t1 = 1;
  const edges: [number, number][] = [
    [-dx, segment.x1 - box.x],
    [dx, box.x + box.width - segment.x1],
    [-dy, segment.y1 - box.y],
    [dy, box.y + box.height - segment.y1],
  ];
  for (const [p, q] of edges) {
    if (p === 0) {
      if (q < 0) return false;
      continue;
    }
    const r = q / p;
    if (p < 0) t0 = Math.max(t0, r);
    else t1 = Math.min(t1, r);
    if (t0 > t1) return false;
  }
  return true;
}

export type BodyLabelSide =
  | "above"
  | "below"
  | "right"
  | "left"
  | "below-right"
  | "above-right"
  | "below-left"
  | "above-left";

/**
 * Where a body's label box sits relative to the body's centre (its top-left
 * corner, as an offset). Above and below are centred on the body, so two
 * balls side by side never print "2 kg1 kg" across each other.
 */
export function bodyLabelOffset(
  side: BodyLabelSide,
  radius: number,
  labelWidth: number,
  fontSize: number,
): { dx: number; dy: number } {
  "worklet";
  const ascent = fontSize * LABEL_ASCENT;
  // Off a corner: clear of anything leaving the body straight up, down or sideways.
  const corner = radius * Math.SQRT1_2 + LABEL_GAP * 0.6;
  switch (side) {
    case "below-right":
      return { dx: corner, dy: corner };
    case "above-right":
      return { dx: corner, dy: -corner - fontSize };
    case "below-left":
      return { dx: -corner - labelWidth, dy: corner };
    case "above-left":
      return { dx: -corner - labelWidth, dy: -corner - fontSize };
    case "below":
      return { dx: -labelWidth / 2, dy: radius + LABEL_GAP };
    case "right":
      return { dx: radius + LABEL_GAP, dy: -fontSize / 2 };
    case "left":
      return { dx: -(radius + LABEL_GAP + labelWidth), dy: -fontSize / 2 };
    default:
      // Baseline `LABEL_GAP` above the top of the body.
      return { dx: -labelWidth / 2, dy: -(radius + LABEL_GAP) - ascent };
  }
}

/**
 * Top-left of a stated vector's label box. `mid` false puts it just past the
 * arrowhead, centred on the line of the arrow; `mid` true puts it beside the
 * middle of the shaft, on `side` (+1 or −1) of it — which is how a component
 * and a dimension line are labelled, so a component never shares the result's
 * tip. A worklet, so a label riding on a body can follow its arrow.
 */
export function vectorLabelOrigin(
  fromX: number,
  fromY: number,
  tipX: number,
  tipY: number,
  labelWidth: number,
  fontSize: number,
  mid: boolean,
  side: number,
  beside = 0,
): { x: number; y: number } {
  "worklet";
  const dx = tipX - fromX;
  const dy = tipY - fromY;
  const length = Math.hypot(dx, dy) || 1;
  const ux = dx / length;
  const uy = dy / length;
  if (!mid && beside !== 0) {
    return besideHeadOrigin(tipX, tipY, ux, uy, length, labelWidth, fontSize, beside);
  }
  let cx: number;
  let cy: number;
  if (!mid) {
    const r = clearanceAlong(ux, uy, labelWidth, fontSize, LABEL_GAP);
    cx = tipX + ux * r;
    cy = tipY + uy * r;
  } else {
    const nx = -uy * side;
    const ny = ux * side;
    const r = LABEL_GAP + (Math.abs(nx) * labelWidth) / 2 + (Math.abs(ny) * fontSize) / 2;
    cx = (fromX + tipX) / 2 + nx * r;
    cy = (fromY + tipY) / 2 + ny * r;
  }
  return { x: cx - labelWidth / 2, y: cy - fontSize / 2 };
}

export type PlacedLabel = { text: string; x: number; y: number; box: LabelBox };

/**
 * Where a label goes once nudged: its home box kept on the canvas, moved by
 * (`dx`, `dy`), and kept on the canvas again — the same steps the layout
 * takes, so a label the renderer places every frame lands where the layout
 * checked it. Returns the left edge and the baseline.
 */
export function placeNudgedLabel(
  x: number,
  y: number,
  labelWidth: number,
  fontSize: number,
  dx: number,
  dy: number,
  width: number,
  height: number,
): { x: number; y: number; baseline: number } {
  "worklet";
  const inset = 4;
  const maxX = width - inset - labelWidth;
  const maxY = height - inset - fontSize;
  let left = x < inset ? inset : x > maxX ? maxX : x;
  let top = y < inset ? inset : y > maxY ? maxY : y;
  left += dx;
  top += dy;
  left = left < inset ? inset : left > maxX ? maxX : left;
  top = top < inset ? inset : top > maxY ? maxY : top;
  // Matches LABEL_ASCENT; a worklet cannot reach a module constant declared below it.
  return { x: left, y: top, baseline: top + fontSize * 0.8 };
}

export function segmentOf(from: ScreenPoint, tip: ScreenPoint): Segment {
  return { x1: from.px, y1: from.py, x2: tip.px, y2: tip.py };
}

export function polylineSegments(points: readonly ScreenPoint[]): Segment[] {
  return points.slice(1).map((point, i) => segmentOf(points[i], point));
}

export function placedLabel(text: string, box: LabelBox): PlacedLabel {
  return { text, x: box.x, y: labelBaseline(box), box };
}
