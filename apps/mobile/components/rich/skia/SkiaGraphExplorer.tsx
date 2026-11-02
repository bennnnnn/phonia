/**
 * Skia graph explorer — the full-screen modal canvas. Bounds live in a
 * Reanimated shared value and every path/label below is a derived value, so
 * pinch/pan/trace render on the UI thread with no React re-render per frame.
 * Loaded lazily and only when isSkiaAvailable() — the SVG explorer stays the
 * fallback for Expo Go and stale dev clients.
 */
import { StyleSheet } from "react-native";
import {
  Canvas,
  Circle,
  DashPathEffect,
  Group,
  Path,
  RoundedRect,
  Skia,
  Text as SkiaText,
  useFont,
  type SkFont,
} from "@shopify/react-native-skia";
import {
  runOnJS,
  useAnimatedReaction,
  useDerivedValue,
  useSharedValue,
} from "react-native-reanimated";

import type { DrawnSeries } from "@/hooks/useInteractiveGraph";
import type { GraphHoleMarker } from "@/components/rich/GraphCanvas";
import {
  GRAPH_TICK_FONT_SIZE,
  INEQUALITY_REGION_OPACITY,
  STRICT_BOUNDARY_DASH,
} from "@/components/rich/graphPaint";
import type { useSkiaGraphViewport } from "@/hooks/useSkiaGraphViewport";
import {
  AXIS_SLOTS,
  buildFillPath,
  buildMarkerPath,
  buildSeriesPath,
  computeChrome,
  MONO_CHAR_PX,
  type Chrome,
} from "@/components/rich/skia/graphPaths";
import { selection } from "@/lib/haptics";
import { formatShortW, mapPointW, nearestTraceSampleW } from "@/lib/math/graphWorklets";
import { NO_TRACE, traceTickW } from "@/lib/math/traceTicks";
import type { Theme } from "@/lib/theme";

const MAX_SERIES_PATHS = 4;
const SLOT_INDICES = Array.from({ length: AXIS_SLOTS }, (_, i) => i);
const SERIES_INDICES = Array.from({ length: MAX_SERIES_PATHS }, (_, i) => i);
const HOLE_INDICES = Array.from({ length: 16 }, (_, i) => i);

type Viewport = ReturnType<typeof useSkiaGraphViewport>;

function TickText({
  chrome,
  axis,
  index,
  font,
  color,
}: {
  chrome: { value: Chrome };
  axis: "xLabels" | "yLabels";
  index: number;
  font: SkFont;
  color: string;
}) {
  const x = useDerivedValue(() => chrome.value[axis][index]?.px ?? -1000);
  const y = useDerivedValue(() => chrome.value[axis][index]?.py ?? -1000);
  const text = useDerivedValue(() => chrome.value[axis][index]?.text ?? "");
  return <SkiaText x={x} y={y} text={text} font={font} color={color} />;
}

export function SkiaGraphCanvas({
  drawn,
  holes = [],
  verticalX,
  xName = "x",
  yName = "y",
  xInPi = false,
  width,
  height,
  pad,
  theme,
  viewport,
  testID = "skia-graph-canvas",
}: {
  drawn: DrawnSeries[];
  holes?: GraphHoleMarker[];
  verticalX?: number;
  xName?: string;
  yName?: string;
  /** Label x in multiples of π (an x-range given as 0…2π). */
  xInPi?: boolean;
  width: number;
  height: number;
  pad: number;
  theme: Theme;
  viewport: Viewport;
  testID?: string;
}) {
  // Project copy of katex/dist/fonts/KaTeX_Main-Regular.ttf. Skia reads a
  // file, and Jest does not transform fonts inside node_modules. Keep this
  // file in sync when the katex dependency changes.
  const font = useFont(
    require("../../../assets/fonts/KaTeX_Main-Regular.ttf"),
    GRAPH_TICK_FONT_SIZE,
  );
  const { bounds, traceActive, tracePos } = viewport;
  const clip = Skia.XYWHRect(
    pad,
    pad,
    Math.max(0, width - pad * 2),
    Math.max(0, height - pad * 2),
  );

  const chrome = useDerivedValue(
    () => computeChrome(bounds.value, width, height, pad, font, xInPi),
    [width, height, pad, font, xInPi],
  );

  const seriesPaths = SERIES_INDICES.map((i) =>
    // eslint-disable-next-line react-hooks/rules-of-hooks -- fixed-length loop
    useDerivedValue(
      () => buildSeriesPath(drawn[i], bounds.value, width, height, pad),
      [drawn, width, height, pad],
    ),
  );
  const fillPaths = SERIES_INDICES.map((i) =>
    // eslint-disable-next-line react-hooks/rules-of-hooks -- fixed-length loop
    useDerivedValue(
      () => buildFillPath(drawn[i], bounds.value, width, height, pad),
      [drawn, width, height, pad],
    ),
  );
  const markerPath = useDerivedValue(
    () => buildMarkerPath(drawn, bounds.value, width, height, pad),
    [drawn, width, height, pad],
  );
  const holeXs = HOLE_INDICES.map((i) =>
    // eslint-disable-next-line react-hooks/rules-of-hooks -- fixed-length loop
    useDerivedValue(() => {
      const marker = holes[i];
      if (!marker) return -1000;
      return mapPointW(marker.point[0], marker.point[1], bounds.value, width, height, pad).px;
    }, [holes, width, height, pad]),
  );
  const holeYs = HOLE_INDICES.map((i) =>
    // eslint-disable-next-line react-hooks/rules-of-hooks -- fixed-length loop
    useDerivedValue(() => {
      const marker = holes[i];
      if (!marker) return -1000;
      return mapPointW(marker.point[0], marker.point[1], bounds.value, width, height, pad).py;
    }, [holes, width, height, pad]),
  );
  const verticalPath = useDerivedValue(() => {
    const path = Skia.Path.Make();
    if (verticalX == null) return path;
    const { px } = mapPointW(verticalX, 0, bounds.value, width, height, pad);
    path.moveTo(px, pad);
    path.lineTo(px, height - pad);
    return path;
  }, [verticalX, width, height, pad]);

  const trace = useDerivedValue(() => {
    if (!traceActive.value) return null;
    return nearestTraceSampleW(
      drawn,
      tracePos.value.px,
      tracePos.value.py,
      bounds.value,
      width,
      height,
      pad,
    );
  }, [drawn, width, height, pad]);

  // A tick when the finger takes a curve and at its roots and turning points,
  // never one per sample (a continuous buzz while scrubbing).
  const traceTicks = useSharedValue(NO_TRACE);
  useAnimatedReaction(
    () => trace.value,
    (sample) => {
      const next = traceTickW(traceTicks.value, sample, Date.now());
      traceTicks.value = next.state;
      if (next.tick) runOnJS(selection)();
    },
  );

  const traceLine = useDerivedValue(() => {
    const path = Skia.Path.Make();
    const t = trace.value;
    if (!t) return path;
    path.moveTo(t.px, pad);
    path.lineTo(t.px, height - pad);
    return path;
  });
  const traceX = useDerivedValue(() => trace.value?.px ?? -1000);
  const traceY = useDerivedValue(() => trace.value?.py ?? -1000);
  const traceColor = useDerivedValue(() => trace.value?.color ?? theme.primary);
  const callout = useDerivedValue(() => {
    const t = trace.value;
    if (!t) return { x: 0, y: 0, w: 0, h: 0, text: "", visible: false };
    const text = `(${formatShortW(t.x)}, ${formatShortW(t.y)})`;
    const w = text.length * MONO_CHAR_PX + 16;
    const h = 26;
    const x = Math.min(Math.max(t.px + 12, 4), width - w - 4);
    const y = Math.max(t.py - 38, 4);
    return { x, y, w, h, text, visible: true };
  }, [width]);
  const calloutX = useDerivedValue(() => callout.value.x);
  const calloutY = useDerivedValue(() => callout.value.y);
  const calloutW = useDerivedValue(() => callout.value.w);
  const calloutH = useDerivedValue(() => callout.value.h);
  const calloutText = useDerivedValue(() => callout.value.text);
  const calloutTextX = useDerivedValue(() => callout.value.x + 8);
  const calloutTextY = useDerivedValue(() => callout.value.y + 17);
  const calloutVisible = useDerivedValue(() => (callout.value.visible ? 1 : 0));

  const gridPath = useDerivedValue(() => chrome.value.grid);
  const axesPath = useDerivedValue(() => chrome.value.axes);
  const originText = useDerivedValue(() => {
    const c = chrome.value;
    return c.originInView ? { x: c.origin.px + 10, y: c.origin.py + 16 } : null;
  });
  const originX = useDerivedValue(() => originText.value?.x ?? -1000);
  const originY = useDerivedValue(() => originText.value?.y ?? -1000);
  const xNameX = useDerivedValue(
    () =>
      chrome.value.xNamePos.px -
      (font ? font.measureText(xName).width : xName.length * MONO_CHAR_PX),
  );
  const xNameY = useDerivedValue(() => chrome.value.xNamePos.py);
  const yNameX = useDerivedValue(() => chrome.value.yNamePos.px);
  const yNameY = useDerivedValue(() => chrome.value.yNamePos.py);

  const canvas = (
      <Canvas style={{ width, height }} testID={testID}>
        <Path path={gridPath} color={theme.border} style="stroke" strokeWidth={1} />
        <Path
          path={axesPath}
          color={theme.textSecondary}
          style="stroke"
          strokeWidth={1.25}
        />
        <Group clip={clip}>
          {verticalX != null ? (
            <Path
              path={verticalPath}
              color={theme.primary}
              style="stroke"
              strokeWidth={2.5}
              strokeCap="round"
            />
          ) : null}
          {SERIES_INDICES.map((i) => (
            <Path
              key={`fill-${i}`}
              path={fillPaths[i]}
              color={drawn[i]?.color ?? theme.primary}
              style="fill"
              opacity={INEQUALITY_REGION_OPACITY}
            />
          ))}
          {SERIES_INDICES.map((i) => (
            <Path
              key={`series-${i}`}
              path={seriesPaths[i]}
              color={drawn[i]?.color ?? theme.primary}
              style="stroke"
              strokeWidth={2.5}
              strokeCap="round"
              strokeJoin="round"
            >
              {drawn[i] && (drawn[i].cmp === "<" || drawn[i].cmp === ">") ? (
                <DashPathEffect intervals={STRICT_BOUNDARY_DASH} />
              ) : null}
            </Path>
          ))}
          <Path path={markerPath} color={drawn[0]?.color ?? theme.primary} style="fill" />
          {HOLE_INDICES.map((i) => (
            <Group key={`hole-${i}`}>
              <Circle
                cx={holeXs[i]}
                cy={holeYs[i]}
                r={5}
                color={theme.elevated}
              />
              <Circle
                cx={holeXs[i]}
                cy={holeYs[i]}
                r={5}
                color={holes[i]?.color ?? theme.primary}
                style="stroke"
                strokeWidth={2.25}
              />
            </Group>
          ))}
          <Path
            path={traceLine}
            color={theme.textTertiary}
            style="stroke"
            strokeWidth={StyleSheet.hairlineWidth}
          />
          <Circle cx={traceX} cy={traceY} r={5.5} color={traceColor} />
          <Circle cx={traceX} cy={traceY} r={2.5} color={theme.surface} />
        </Group>
        {font
          ? SLOT_INDICES.map((i) => (
              <TickText
                key={`tx-${i}`}
                chrome={chrome}
                axis="xLabels"
                index={i}
                font={font}
                color={theme.textSecondary}
              />
            ))
          : null}
        {font
          ? SLOT_INDICES.map((i) => (
              <TickText
                key={`ty-${i}`}
                chrome={chrome}
                axis="yLabels"
                index={i}
                font={font}
                color={theme.textSecondary}
              />
            ))
          : null}
        {font ? (
          <SkiaText
            x={originX}
            y={originY}
            text="0"
            font={font}
            color={theme.textSecondary}
          />
        ) : null}
        {font ? (
          <SkiaText x={xNameX} y={xNameY} text={xName} font={font} color={theme.textSecondary} />
        ) : null}
        {font ? (
          <SkiaText x={yNameX} y={yNameY} text={yName} font={font} color={theme.textSecondary} />
        ) : null}
        <RoundedRect
          x={calloutX}
          y={calloutY}
          width={calloutW}
          height={calloutH}
          r={8}
          color={theme.text}
          opacity={calloutVisible}
        />
        {font ? (
          <SkiaText
            x={calloutTextX}
            y={calloutTextY}
            text={calloutText}
            font={font}
            color={theme.bg}
            opacity={calloutVisible}
          />
        ) : null}
      </Canvas>
  );
  return canvas;
}
