/**
 * The graph explorer's paths and chrome, as worklets: each series' curve, an
 * inequality's shaded side, a scatter's markers, and the grid, axes and tick
 * labels for the current bounds. `SkiaGraphCanvas` derives them on the UI
 * thread every frame.
 */
import { Skia, type SkFont } from "@shopify/react-native-skia";

import type { DrawnSeries } from "@/hooks/useInteractiveGraph";
import { GRAPH_TICK_FONT_SIZE } from "@/components/rich/graphPaint";
import {
  axisTicksW,
  dockAxisW,
  formatPiTickW,
  formatTickW,
  mapPointW,
  piTicksW,
  type GraphViewW,
} from "@/lib/math/graphWorklets";

/** The most tick labels drawn on one axis (each is a fixed Skia text slot). */
export const AXIS_SLOTS = 16;
/** Conservative advance before KaTeX_Main has measured the tick (11pt). */
export const MONO_CHAR_PX = 6.7;
const MARKER_RADIUS = 4;

type TickLabel = { px: number; py: number; text: string };

export type Chrome = {
  grid: ReturnType<typeof Skia.Path.Make>;
  axes: ReturnType<typeof Skia.Path.Make>;
  xLabels: TickLabel[];
  yLabels: TickLabel[];
  origin: { px: number; py: number };
  originInView: boolean;
  xNamePos: { px: number; py: number };
  yNamePos: { px: number; py: number };
};

export function buildSeriesPath(
  row: DrawnSeries | undefined,
  b: GraphViewW,
  width: number,
  height: number,
  pad: number,
) {
  "worklet";
  const path = Skia.Path.Make();
  if (!row || !row.visible) return path;
  const segs = row.segments?.filter((seg) => seg.length >= 2);
  const curves = segs && segs.length > 1 ? segs : row.points.length >= 2 ? [row.points] : [];
  for (const seg of curves) {
    let started = false;
    for (const [x, y] of seg) {
      if (!Number.isFinite(x) || !Number.isFinite(y)) {
        started = false;
        continue;
      }
      const { px, py } = mapPointW(x, y, b, width, height, pad);
      if (started) path.lineTo(px, py);
      else {
        path.moveTo(px, py);
        started = true;
      }
    }
  }
  return path;
}

export function buildFillPath(
  row: DrawnSeries | undefined,
  b: GraphViewW,
  width: number,
  height: number,
  pad: number,
) {
  "worklet";
  const path = Skia.Path.Make();
  if (!row || !row.visible || row.cmp === "=") return path;
  const segs = row.segments?.filter((seg) => seg.length >= 2);
  const curve = segs && segs.length > 1 ? segs[0] : row.points.length >= 2 ? row.points : null;
  if (!curve) return path;
  const below = row.cmp === "<" || row.cmp === "<=";
  const edgePy = below ? height - pad : pad;
  let started = false;
  let firstPx = 0;
  let lastPx = 0;
  for (const [x, y] of curve) {
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    const { px, py } = mapPointW(x, y, b, width, height, pad);
    if (!started) {
      path.moveTo(px, py);
      firstPx = px;
      started = true;
    } else {
      path.lineTo(px, py);
    }
    lastPx = px;
  }
  if (started) {
    path.lineTo(lastPx, edgePy);
    path.lineTo(firstPx, edgePy);
    path.close();
  }
  return path;
}

export function buildMarkerPath(
  drawn: DrawnSeries[],
  b: GraphViewW,
  width: number,
  height: number,
  pad: number,
) {
  "worklet";
  const path = Skia.Path.Make();
  const visible = drawn.filter((row) => row.visible);
  if (visible.length !== 1) return path;
  const points = visible[0].points;
  if (points.length > 20) return path;
  for (const [x, y] of points) {
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    if (x < b.xMin || x > b.xMax || y < b.yMin || y > b.yMax) continue;
    const { px, py } = mapPointW(x, y, b, width, height, pad);
    path.addCircle(px, py, MARKER_RADIUS);
  }
  return path;
}

export function computeChrome(
  b: GraphViewW,
  width: number,
  height: number,
  pad: number,
  font: Pick<SkFont, "measureText"> | null,
  xInPi = false,
): Chrome {
  "worklet";
  const measure = (text: string) =>
    font ? font.measureText(text).width : text.length * MONO_CHAR_PX;
  const grid = Skia.Path.Make();
  const axes = Skia.Path.Make();
  const origin = mapPointW(0, 0, b, width, height, pad);
  const xOriginInView = b.xMin <= 0 && b.xMax >= 0;
  const yOriginInView = b.yMin <= 0 && b.yMax >= 0;
  const xTickLabelY = dockAxisW(
    origin.py + 16,
    pad + GRAPH_TICK_FONT_SIZE,
    height - pad - 4,
  );

  const xLabels: TickLabel[] = [];
  for (const n of xInPi ? piTicksW(b.xMin, b.xMax) : axisTicksW(b.xMin, b.xMax)) {
    if (Math.abs(n) < 1e-9) continue;
    const { px } = mapPointW(n, 0, b, width, height, pad);
    grid.moveTo(px, pad);
    grid.lineTo(px, height - pad);
    if (xLabels.length < AXIS_SLOTS) {
      const text = xInPi ? formatPiTickW(n) : formatTickW(n);
      xLabels.push({ px: px - measure(text) / 2, py: xTickLabelY, text });
    }
  }
  const yLabels: TickLabel[] = [];
  for (const n of axisTicksW(b.yMin, b.yMax)) {
    if (Math.abs(n) < 1e-9) continue;
    const { py } = mapPointW(0, n, b, width, height, pad);
    grid.moveTo(pad, py);
    grid.lineTo(width - pad, py);
    if (py >= pad + 12 && yLabels.length < AXIS_SLOTS) {
      const text = formatTickW(n);
      const textWidth = measure(text);
      yLabels.push({
        px: dockAxisW(origin.px - 6 - textWidth, 4, width - textWidth - 4),
        py: py + 4,
        text,
      });
    }
  }

  if (xOriginInView) {
    axes.moveTo(origin.px, pad);
    axes.lineTo(origin.px, height - pad);
  }
  if (yOriginInView) {
    axes.moveTo(pad, origin.py);
    axes.lineTo(width - pad, origin.py);
  }

  const originInView = xOriginInView && yOriginInView;
  return {
    grid,
    axes,
    xLabels,
    yLabels,
    origin,
    originInView,
    xNamePos: {
      px: width - pad,
      py: dockAxisW(origin.py - 8, pad + GRAPH_TICK_FONT_SIZE, height - pad - 4),
    },
    yNamePos: {
      px: dockAxisW(origin.px + 8, 4, width - pad - GRAPH_TICK_FONT_SIZE),
      py: pad + 4,
    },
  };
}
