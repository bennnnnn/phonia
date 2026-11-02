/**
 * Skia path builders shared by the physics scene and the trajectory chart.
 *
 * The arrow is the one drawing vocabulary both use, so it lives here once:
 * a filled head is a force, an open chevron is motion (velocity, an
 * acceleration), and cross-ticks at both ends are a length (a dimension line).
 */
import { Skia, type SkPath } from "@shopify/react-native-skia";

type Point = { px: number; py: number };

type ArrowHead = "filled" | "open" | "ticks";

/** A polyline through screen points. */
export function pointsPath(points: readonly Point[]): SkPath {
  const path = Skia.Path.Make();
  points.forEach((point, index) => {
    if (index === 0) path.moveTo(point.px, point.py);
    else path.lineTo(point.px, point.py);
  });
  return path;
}

export function linePath(x1: number, y1: number, x2: number, y2: number): SkPath {
  const path = Skia.Path.Make();
  path.moveTo(x1, y1);
  path.lineTo(x2, y2);
  return path;
}

/** Separate straight strokes in one path: hatching, ticks, walls. */
export function segmentsPath(
  segments: readonly { x1: number; y1: number; x2: number; y2: number }[],
): SkPath {
  const path = Skia.Path.Make();
  for (const segment of segments) {
    path.moveTo(segment.x1, segment.y1);
    path.lineTo(segment.x2, segment.y2);
  }
  return path;
}

/**
 * Append just the head of an arrow whose tip is (`tipX`, `tipY`) and whose
 * unit direction is (`ux`, `uy`). For `ticks` the start of the line is needed
 * too, since a dimension line is marked at both ends.
 */
export function appendArrowHead(
  path: SkPath,
  tipX: number,
  tipY: number,
  ux: number,
  uy: number,
  head: number,
  kind: ArrowHead,
  length = 0,
): SkPath {
  "worklet";
  if (head <= 0) return path;
  // Perpendicular, for the barbs.
  const wx = -uy * head * 0.6;
  const wy = ux * head * 0.6;
  if (kind === "ticks") {
    const fromX = tipX - ux * length;
    const fromY = tipY - uy * length;
    path.moveTo(tipX - wx, tipY - wy);
    path.lineTo(tipX + wx, tipY + wy);
    path.moveTo(fromX - wx, fromY - wy);
    path.lineTo(fromX + wx, fromY + wy);
    return path;
  }
  const baseX = tipX - ux * head;
  const baseY = tipY - uy * head;
  path.moveTo(baseX + wx, baseY + wy);
  path.lineTo(tipX, tipY);
  path.lineTo(baseX - wx, baseY - wy);
  if (kind === "filled") path.close();
  return path;
}

/**
 * An arrow `length` long from (`fromX`, `fromY`) along the unit direction
 * (`ux`, `uy`), shaft and head in one path. Draw it stroked; a `filled` head
 * also needs the same path drawn with `style="fill"`, which fills only the
 * closed head since the shaft has no area.
 */
export function arrowPath(
  fromX: number,
  fromY: number,
  ux: number,
  uy: number,
  length: number,
  head: number,
  kind: ArrowHead,
): SkPath {
  "worklet";
  const path = Skia.Path.Make();
  if (!(length > 0)) return path;
  const tipX = fromX + ux * length;
  const tipY = fromY + uy * length;
  // A filled head covers the last stretch of shaft; stopping short keeps the
  // round cap from poking through its point.
  const shaft = kind === "filled" ? Math.max(0, length - head * 0.6) : length;
  path.moveTo(fromX, fromY);
  path.lineTo(fromX + ux * shaft, fromY + uy * shaft);
  return appendArrowHead(path, tipX, tipY, ux, uy, head, kind, length);
}

/** Just the shaft, for an arrow whose shaft is dashed and whose head is not. */
export function arrowShaftPath(
  fromX: number,
  fromY: number,
  ux: number,
  uy: number,
  length: number,
): SkPath {
  return linePath(fromX, fromY, fromX + ux * length, fromY + uy * length);
}

/** Just the head, positioned for an arrow `length` long. */
export function arrowHeadPath(
  fromX: number,
  fromY: number,
  ux: number,
  uy: number,
  length: number,
  head: number,
  kind: ArrowHead,
): SkPath {
  return appendArrowHead(
    Skia.Path.Make(),
    fromX + ux * length,
    fromY + uy * length,
    ux,
    uy,
    head,
    kind,
    length,
  );
}
