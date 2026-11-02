/** Skia paths for a scene's fixed parts, its box bodies and its springs. */
import { Skia } from "@shopify/react-native-skia";

import { PIVOT_SIZE, type ScreenPoint } from "@/lib/physics/simulation";

const WALL_HALF_HEIGHT = 16;

export type Rect = { x: number; y: number; width: number; height: number };

export function wallPath(point: ScreenPoint, floorY: number | null) {
  const path = Skia.Path.Make();
  path.moveTo(point.px, point.py - WALL_HALF_HEIGHT);
  // A wall standing on the ground stops at it rather than poking through.
  const bottom = point.py + WALL_HALF_HEIGHT;
  path.lineTo(point.px, floorY === null ? bottom : Math.min(bottom, floorY));
  return path;
}

export function pivotPath(point: ScreenPoint) {
  const path = Skia.Path.Make();
  path.moveTo(point.px, point.py);
  path.lineTo(point.px - PIVOT_SIZE, point.py + PIVOT_SIZE * 1.4);
  path.lineTo(point.px + PIVOT_SIZE, point.py + PIVOT_SIZE * 1.4);
  path.close();
  return path;
}

export function polygonPath(points: readonly ScreenPoint[]) {
  const path = Skia.Path.Make();
  points.forEach((point, index) => {
    if (index === 0) path.moveTo(point.px, point.py);
    else path.lineTo(point.px, point.py);
  });
  path.close();
  return path;
}

export function rectPath(rect: Rect) {
  return polygonPath([
    { px: rect.x, py: rect.y },
    { px: rect.x + rect.width, py: rect.y },
    { px: rect.x + rect.width, py: rect.y + rect.height },
    { px: rect.x, py: rect.y + rect.height },
  ]);
}

/** A box body: a square of side 2 * `half`, turned `angle` radians on screen. */
export function boxPath(cx: number, cy: number, half: number, angle: number) {
  "worklet";
  const c = Math.cos(angle) * half;
  const s = Math.sin(angle) * half;
  const path = Skia.Path.Make();
  // Corners at ±along ±across, where along = (c, s) and across = (−s, c).
  path.moveTo(cx + c - s, cy + s + c);
  path.lineTo(cx - c - s, cy - s + c);
  path.lineTo(cx - c + s, cy - s - c);
  path.lineTo(cx + c + s, cy + s - c);
  path.close();
  return path;
}

const COIL_COUNT = 8;
const COIL_WIDTH = 8;

export function springPath(from: ScreenPoint, to: ScreenPoint) {
  "worklet";
  const path = Skia.Path.Make();
  const dx = to.px - from.px;
  const dy = to.py - from.py;
  const length = Math.hypot(dx, dy);
  path.moveTo(from.px, from.py);
  if (length < 1) {
    path.lineTo(to.px, to.py);
    return path;
  }
  const ux = dx / length;
  const uy = dy / length;
  const px = -uy;
  const py = ux;
  const turns = COIL_COUNT * 2;
  for (let i = 1; i < turns; i += 1) {
    const along = (i / turns) * length;
    const side = i % 2 === 0 ? COIL_WIDTH : -COIL_WIDTH;
    path.lineTo(from.px + ux * along + px * side, from.py + uy * along + py * side);
  }
  path.lineTo(to.px, to.py);
  return path;
}
