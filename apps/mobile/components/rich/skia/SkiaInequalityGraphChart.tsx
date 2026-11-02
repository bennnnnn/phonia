import { useMemo } from "react";
import { View } from "react-native";
import {
  Canvas,
  Circle,
  DashPathEffect,
  Group,
  Path,
  Skia,
  Text as SkiaText,
  useFont,
} from "@shopify/react-native-skia";

import {
  GRAPH_CHART_PAD,
  GRAPH_TICK_FONT_SIZE,
  INEQUALITY_REGION_OPACITY,
  STRICT_BOUNDARY_DASH,
} from "@/components/rich/graphPaint";
import {
  formatAxisNumber,
  graphAxisTicks,
  mapGraphPoint,
} from "@/lib/math/graphBlock";
import { tickCountW } from "@/lib/math/graphWorklets";
import { type InequalityGraphSpec } from "@/lib/math/graphSpec";
import { clipInequalityRegion } from "@/lib/math/inequalityGraph";
import type { Theme } from "@/lib/theme";


type Props = {
  spec: InequalityGraphSpec;
  width: number;
  height: number;
  theme: Theme;
  accessibilityLabel: string;
};

export function SkiaInequalityGraphChart({
  spec,
  width,
  height,
  theme,
  accessibilityLabel,
}: Props) {
  const font = useFont(
    require("../../../assets/fonts/KaTeX_Main-Regular.ttf"),
    GRAPH_TICK_FONT_SIZE,
  );
  const geometry = useMemo(() => clipInequalityRegion(spec), [spec]);
  const bounds = useMemo(
    () => ({
      xMin: spec.x_min,
      xMax: spec.x_max,
      yMin: spec.y_min,
      yMax: spec.y_max,
    }),
    [spec.x_max, spec.x_min, spec.y_max, spec.y_min],
  );
  const origin = mapGraphPoint(0, 0, bounds, width, height, GRAPH_CHART_PAD);
  const yAxisX = Math.max(GRAPH_CHART_PAD, Math.min(width - GRAPH_CHART_PAD, origin.px));
  const xAxisY = Math.max(GRAPH_CHART_PAD, Math.min(height - GRAPH_CHART_PAD, origin.py));
  const xTicks = useMemo(
    () =>
      graphAxisTicks(
        bounds.xMin,
        bounds.xMax,
        tickCountW(bounds.xMin, bounds.xMax),
        true,
      ),
    [bounds.xMax, bounds.xMin],
  );
  const yTicks = useMemo(
    () =>
      graphAxisTicks(
        bounds.yMin,
        bounds.yMax,
        tickCountW(bounds.yMin, bounds.yMax),
        true,
      ),
    [bounds.yMax, bounds.yMin],
  );

  const gridPath = useMemo(() => {
    const path = Skia.Path.Make();
    xTicks.forEach((value) => {
      if (Math.abs(value) < 1e-9) return;
      const { px } = mapGraphPoint(value, 0, bounds, width, height, GRAPH_CHART_PAD);
      path.moveTo(px, GRAPH_CHART_PAD);
      path.lineTo(px, height - GRAPH_CHART_PAD);
    });
    yTicks.forEach((value) => {
      if (Math.abs(value) < 1e-9) return;
      const { py } = mapGraphPoint(0, value, bounds, width, height, GRAPH_CHART_PAD);
      path.moveTo(GRAPH_CHART_PAD, py);
      path.lineTo(width - GRAPH_CHART_PAD, py);
    });
    return path;
  }, [bounds, height, width, xTicks, yTicks]);

  const axesPath = useMemo(() => {
    const path = Skia.Path.Make();
    path.moveTo(yAxisX, GRAPH_CHART_PAD);
    path.lineTo(yAxisX, height - GRAPH_CHART_PAD);
    path.moveTo(GRAPH_CHART_PAD, xAxisY);
    path.lineTo(width - GRAPH_CHART_PAD, xAxisY);
    return path;
  }, [height, width, xAxisY, yAxisX]);

  const regionPath = useMemo(() => {
    const path = Skia.Path.Make();
    geometry?.region.forEach(([x, y], index) => {
      const point = mapGraphPoint(x, y, bounds, width, height, GRAPH_CHART_PAD);
      if (index === 0) path.moveTo(point.px, point.py);
      else path.lineTo(point.px, point.py);
    });
    if ((geometry?.region.length ?? 0) >= 3) path.close();
    return path;
  }, [bounds, geometry, height, width]);

  const boundaryPath = useMemo(() => {
    const path = Skia.Path.Make();
    geometry?.boundary.forEach(([x, y], index) => {
      const point = mapGraphPoint(x, y, bounds, width, height, GRAPH_CHART_PAD);
      if (index === 0) path.moveTo(point.px, point.py);
      else path.lineTo(point.px, point.py);
    });
    return path;
  }, [bounds, geometry, height, width]);

  if (!geometry) return null;
  const strict = spec.comparator === "<" || spec.comparator === ">";
  const boundaryPoint =
    !strict && geometry.boundary.length === 1
      ? mapGraphPoint(
          geometry.boundary[0][0],
          geometry.boundary[0][1],
          bounds,
          width,
          height,
          GRAPH_CHART_PAD,
        )
      : null;
  const clip = Skia.XYWHRect(GRAPH_CHART_PAD, GRAPH_CHART_PAD, width - GRAPH_CHART_PAD * 2, height - GRAPH_CHART_PAD * 2);
  const originVisible =
    bounds.xMin <= 0 && bounds.xMax >= 0 && bounds.yMin <= 0 && bounds.yMax >= 0;

  return (
    <View
      accessible
      accessibilityRole="image"
      accessibilityLabel={accessibilityLabel}
      style={{ width, height }}
    >
      <Canvas testID="skia-inequality-canvas" style={{ width, height }}>
        {geometry.region.length >= 3 ? (
          <Path path={regionPath} color={theme.primary} style="fill" opacity={INEQUALITY_REGION_OPACITY} />
        ) : null}
        <Path path={gridPath} color={theme.border} style="stroke" strokeWidth={1} />
        <Path
          path={axesPath}
          color={theme.textSecondary}
          style="stroke"
          strokeWidth={1.25}
        />
        <Group clip={clip}>
          {geometry.boundary.length >= 2 ? (
            <Path
              path={boundaryPath}
              color={theme.primary}
              style="stroke"
              strokeWidth={2.5}
              strokeCap="butt"
            >
              {strict ? <DashPathEffect intervals={STRICT_BOUNDARY_DASH} /> : null}
            </Path>
          ) : null}
        </Group>
        {boundaryPoint ? (
          <Circle cx={boundaryPoint.px} cy={boundaryPoint.py} r={3.5} color={theme.primary} />
        ) : null}
        {font
          ? xTicks.map((value) => {
              if (Math.abs(value) < 1e-9) return null;
              const text = formatAxisNumber(value, true);
              const { px } = mapGraphPoint(value, 0, bounds, width, height, GRAPH_CHART_PAD);
              return (
                <SkiaText
                  key={`x-${text}`}
                  x={px - font.measureText(text).width / 2}
                  y={xAxisY + 16}
                  text={text}
                  font={font}
                  color={theme.textSecondary}
                />
              );
            })
          : null}
        {font
          ? yTicks.map((value) => {
              if (Math.abs(value) < 1e-9) return null;
              const { py } = mapGraphPoint(0, value, bounds, width, height, GRAPH_CHART_PAD);
              if (py < GRAPH_CHART_PAD + 12) return null;
              const text = formatAxisNumber(value, true);
              return (
                <SkiaText
                  key={`y-${text}`}
                  x={Math.max(4, yAxisX - 6 - font.measureText(text).width)}
                  y={py + 4}
                  text={text}
                  font={font}
                  color={theme.textSecondary}
                />
              );
            })
          : null}
        {font && originVisible ? (
          <SkiaText
            x={origin.px + 10}
            y={origin.py + 16}
            text="0"
            font={font}
            color={theme.textSecondary}
          />
        ) : null}
        {font ? (
          <SkiaText
            x={width - GRAPH_CHART_PAD - font.measureText("x").width}
            y={xAxisY - 6}
            text="x"
            font={font}
            color={theme.textSecondary}
          />
        ) : null}
        {font ? (
          <SkiaText
            x={Math.max(yAxisX - GRAPH_TICK_FONT_SIZE, 2)}
            y={GRAPH_CHART_PAD - 2}
            text="y"
            font={font}
            color={theme.textSecondary}
          />
        ) : null}
      </Canvas>
    </View>
  );
}
