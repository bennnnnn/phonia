/**
 * Skia paths for the schematic symbols, each drawn about its centre.
 *
 * Load parts lie along a horizontal wire and reach `PART_HALF_SPAN` either
 * side of their centre, where the layout's leads stop. The source stands on
 * the vertical left edge and reaches `SOURCE_HALF_SPAN` up and down. Letters
 * (the A and V of the meters, the battery's + and −) are strokes rather than
 * text, so they need no font and stay crisp at any scale.
 *
 * Only `moveTo`, `lineTo`, `close` and `addCircle` are used: every builder
 * runs under the component tests' Skia stub too.
 */
import { Skia, type SkPath } from "@shopify/react-native-skia";

import {
  PART_HALF_SPAN,
  SOURCE_HALF_SPAN,
  SOURCE_HALF_WIDTH,
  type CircuitPartKind,
  type CircuitSourceKind,
} from "@/lib/physics/circuit";

/** Thin strokes, and the heavier ones (plates) drawn separately. */
type SymbolPaths = { stroke: SkPath; heavy?: SkPath };

const METER_RADIUS = 9;
const ZIGZAG_PEAKS = 6;
const ZIGZAG_HEIGHT = 5;
const PLATE_HALF = 9;
const COIL_LOOPS = 4;
const COIL_HEIGHT = 6;
const ARC_STEPS = 10;

function polyline(path: SkPath, points: [number, number][]) {
  points.forEach(([x, y], index) => (index === 0 ? path.moveTo(x, y) : path.lineTo(x, y)));
}

function letterA(path: SkPath, cx: number, cy: number) {
  polyline(path, [
    [cx - 3.6, cy + 4.6],
    [cx, cy - 4.6],
    [cx + 3.6, cy + 4.6],
  ]);
  polyline(path, [
    [cx - 2.1, cy + 1],
    [cx + 2.1, cy + 1],
  ]);
}

function letterV(path: SkPath, cx: number, cy: number) {
  polyline(path, [
    [cx - 3.6, cy - 4.6],
    [cx, cy + 4.6],
    [cx + 3.6, cy - 4.6],
  ]);
}

export function partSymbolPaths(part: CircuitPartKind, cx: number, cy: number): SymbolPaths {
  const stroke = Skia.Path.Make();
  const half = PART_HALF_SPAN[part];
  switch (part) {
    case "resistor": {
      const points: [number, number][] = [[cx - half, cy]];
      for (let i = 0; i < ZIGZAG_PEAKS; i += 1) {
        const x = cx - half + ((i + 0.5) * half * 2) / ZIGZAG_PEAKS;
        points.push([x, cy + (i % 2 === 0 ? -ZIGZAG_HEIGHT : ZIGZAG_HEIGHT)]);
      }
      points.push([cx + half, cy]);
      polyline(stroke, points);
      return { stroke };
    }
    case "bulb": {
      stroke.addCircle(cx, cy, METER_RADIUS);
      const d = METER_RADIUS * 0.7;
      polyline(stroke, [
        [cx - d, cy - d],
        [cx + d, cy + d],
      ]);
      polyline(stroke, [
        [cx - d, cy + d],
        [cx + d, cy - d],
      ]);
      return { stroke };
    }
    case "ammeter":
    case "voltmeter":
      stroke.addCircle(cx, cy, METER_RADIUS);
      if (part === "ammeter") letterA(stroke, cx, cy);
      else letterV(stroke, cx, cy);
      return { stroke };
    case "capacitor": {
      const heavy = Skia.Path.Make();
      polyline(heavy, [
        [cx - half, cy - PLATE_HALF],
        [cx - half, cy + PLATE_HALF],
      ]);
      polyline(heavy, [
        [cx + half, cy - PLATE_HALF],
        [cx + half, cy + PLATE_HALF],
      ]);
      return { stroke, heavy };
    }
    case "inductor": {
      // Humps above the wire, each half an ellipse.
      const width = (half * 2) / COIL_LOOPS;
      const points: [number, number][] = [];
      for (let loop = 0; loop < COIL_LOOPS; loop += 1) {
        const centre = cx - half + width * (loop + 0.5);
        for (let step = 0; step <= ARC_STEPS; step += 1) {
          const angle = Math.PI - (Math.PI * step) / ARC_STEPS;
          points.push([centre + (width / 2) * Math.cos(angle), cy - COIL_HEIGHT * Math.sin(angle)]);
        }
      }
      polyline(stroke, points);
      return { stroke };
    }
    case "switch": {
      // Two terminals and the blade lifted off the right one: an open switch.
      stroke.addCircle(cx - half, cy, 2);
      stroke.addCircle(cx + half, cy, 2);
      const blade = half * 2 - 2;
      const lift = (25 * Math.PI) / 180;
      polyline(stroke, [
        [cx - half + 1.4, cy - 1.4],
        [cx - half + blade * Math.cos(lift), cy - blade * Math.sin(lift)],
      ]);
      return { stroke };
    }
  }
}

/** The source on the left edge, about its centre; the + terminal is at the top. */
export function sourceSymbolPaths(kind: CircuitSourceKind, cx: number, cy: number): SymbolPaths {
  const stroke = Skia.Path.Make();
  if (kind === "ac") {
    stroke.addCircle(cx, cy, SOURCE_HALF_SPAN);
    const points: [number, number][] = [];
    for (let step = 0; step <= 16; step += 1) {
      const u = step / 16;
      points.push([cx - 6 + 12 * u, cy - 3.5 * Math.sin(u * Math.PI * 2)]);
    }
    polyline(stroke, points);
    return { stroke };
  }
  // Long plate (+) above the short, heavy plate (−), joined to the edge wire.
  const gap = 3.5;
  polyline(stroke, [
    [cx, cy - SOURCE_HALF_SPAN],
    [cx, cy - gap],
  ]);
  polyline(stroke, [
    [cx, cy + gap],
    [cx, cy + SOURCE_HALF_SPAN],
  ]);
  polyline(stroke, [
    [cx - SOURCE_HALF_WIDTH, cy - gap],
    [cx + SOURCE_HALF_WIDTH, cy - gap],
  ]);
  const heavy = Skia.Path.Make();
  polyline(heavy, [
    [cx - SOURCE_HALF_WIDTH / 2, cy + gap],
    [cx + SOURCE_HALF_WIDTH / 2, cy + gap],
  ]);
  // + by the long plate, − by the short one, inside the loop.
  const signX = cx + SOURCE_HALF_WIDTH + 5;
  polyline(stroke, [
    [signX - 2.5, cy - gap - 5],
    [signX + 2.5, cy - gap - 5],
  ]);
  polyline(stroke, [
    [signX, cy - gap - 7.5],
    [signX, cy - gap - 2.5],
  ]);
  polyline(stroke, [
    [signX - 2.5, cy + gap + 5],
    [signX + 2.5, cy + gap + 5],
  ]);
  return { stroke, heavy };
}
