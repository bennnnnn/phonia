/** Native Skia trajectory chart; the dot walks the sampled path when played. */
import { useCallback, useMemo } from "react";
import { Text, View } from "react-native";
import { useTranslation } from "react-i18next";
import { Canvas, Circle, Group, Path, Skia, useFont } from "@shopify/react-native-skia";
import { useDerivedValue } from "react-native-reanimated";

import { formatGraphExpr, mapGraphPoint } from "@/lib/math/graphBlock";
import { type GraphSpec } from "@/lib/math/graphSpec";
import {
  trajectoryAxisLayout,
  trajectoryAxisCaptionPosition,
  trajectoryBounds,
  trajectoryOriginLabelPosition,
  trajectoryPointAt,
} from "@/lib/math/trajectory";
import { Motion } from "@/lib/motion";
import { Theme } from "@/lib/theme";
import { PlaybackButton } from "@/components/rich/PlaybackButton";
import { usePlayback } from "@/components/rich/usePlayback";
import { HaloText } from "@/components/rich/skia/HaloText";
import { pointsPath } from "@/components/rich/skia/paths";

/** Changing either breaks TrajectoryGraphTicks.test.tsx, which pins tick geometry. */
const TRAJECTORY_PAD = 40;
const TRAJECTORY_CHART_HEIGHT = 220;

const DOT_RADIUS = 5.5;
const CURVE_STROKE = 2.5;
const TICK_FONT_SIZE = 11;
/** Until the font loads, a rough SpaceMono advance keeps the layout sane. */
const FALLBACK_CHAR_WIDTH = 6.7;

type Props = {
  spec: GraphSpec;
  chartWidth: number;
  styles: { wrap: object; title: object };
  theme: Theme;
};

export function TrajectoryChart({ spec, chartWidth, styles, theme }: Props) {
  const { t } = useTranslation();
  const font = useFont(require("../../assets/fonts/SpaceMono-Regular.ttf"), TICK_FONT_SIZE);

  const bounds = useMemo(() => trajectoryBounds(spec.points), [spec.points]);
  const screenPoints = useMemo(
    () =>
      spec.points.map(([x, y]) =>
        mapGraphPoint(x, y, bounds, chartWidth, TRAJECTORY_CHART_HEIGHT, TRAJECTORY_PAD),
      ),
    [spec.points, bounds, chartWidth],
  );
  const curvePath = useMemo(() => pointsPath(screenPoints), [screenPoints]);
  const axes = useMemo(
    () => trajectoryAxisLayout(bounds, chartWidth, TRAJECTORY_CHART_HEIGHT, TRAJECTORY_PAD),
    [bounds, chartWidth],
  );
  const gridPath = useMemo(() => {
    const path = Skia.Path.Make();
    axes.xTicks.forEach((tick) => {
      path.moveTo(tick.px, TRAJECTORY_PAD);
      path.lineTo(tick.px, TRAJECTORY_CHART_HEIGHT - TRAJECTORY_PAD);
    });
    axes.yTicks.forEach((tick) => {
      path.moveTo(TRAJECTORY_PAD, tick.py - 4);
      path.lineTo(chartWidth - TRAJECTORY_PAD, tick.py - 4);
    });
    return path;
  }, [axes, chartWidth]);
  const axesPath = useMemo(() => {
    const path = Skia.Path.Make();
    path.moveTo(axes.yAxisX, TRAJECTORY_PAD);
    path.lineTo(axes.yAxisX, TRAJECTORY_CHART_HEIGHT - TRAJECTORY_PAD);
    path.moveTo(TRAJECTORY_PAD, axes.xAxisY);
    path.lineTo(chartWidth - TRAJECTORY_PAD, axes.xAxisY);
    return path;
  }, [axes, chartWidth]);
  // The clip keeps a wild sample off the labels; it is grown by the stroke so
  // a curve running along the plot's edge keeps its full width.
  const clip = useMemo(
    () =>
      Skia.XYWHRect(
        TRAJECTORY_PAD - CURVE_STROKE,
        TRAJECTORY_PAD - CURVE_STROKE,
        Math.max(0, chartWidth - TRAJECTORY_PAD * 2 + CURVE_STROKE * 2),
        TRAJECTORY_CHART_HEIGHT - TRAJECTORY_PAD * 2 + CURVE_STROKE * 2,
      ),
    [chartWidth],
  );

  // Not autoplayed: a projectile or spring reply also carries a scene, which
  // is the one moving picture. The graph plays when asked.
  const resetKey = useMemo(() => JSON.stringify(spec.points), [spec.points]);
  const { progress, isPlaying, play, pause } = usePlayback({
    duration: Motion.duration.trajectory,
    animated: screenPoints.length > 1,
    autoplay: false,
    loop: false,
    resetKey,
  });
  const dot = useDerivedValue(() => {
    const point = trajectoryPointAt(screenPoints, progress.value);
    return { x: point.px, y: point.py };
  });

  const xLabel = spec.x_label ?? "x";
  const yLabel = spec.y_label ?? "y";
  const title = formatGraphExpr(spec.title ?? "Trajectory");
  const measure = useCallback(
    (value: string) => font?.measureText(value).width ?? value.length * FALLBACK_CHAR_WIDTH,
    [font],
  );
  const xCaption = trajectoryAxisCaptionPosition(
    measure(xLabel),
    chartWidth,
    TRAJECTORY_CHART_HEIGHT,
    TRAJECTORY_PAD,
  );
  const showOrigin =
    bounds.xMin <= 0 && bounds.xMax >= 0 && bounds.yMin <= 0 && bounds.yMax >= 0;
  const originLabel = trajectoryOriginLabelPosition(axes.origin, measure("0"));
  const label = (key: string, x: number, y: number, text: string) =>
    font ? (
      <HaloText
        key={key}
        x={x}
        y={y}
        text={text}
        font={font}
        color={theme.textSecondary}
        halo={theme.bg}
      />
    ) : null;

  return (
    <View style={styles.wrap}>
      <Text style={styles.title}>{title}</Text>
      <View
        accessible
        accessibilityRole="image"
        accessibilityLabel={t("rich.trajectory_a11y", { title, x: xLabel, y: yLabel })}
        style={{ width: chartWidth, height: TRAJECTORY_CHART_HEIGHT }}
      >
        <Canvas
          testID="trajectory-canvas"
          style={{ width: chartWidth, height: TRAJECTORY_CHART_HEIGHT }}
        >
          <Path path={gridPath} color={theme.border} style="stroke" strokeWidth={1} />
          <Path path={axesPath} color={theme.textSecondary} style="stroke" strokeWidth={1.25} />
          <Group clip={clip}>
            <Path
              path={curvePath}
              color={theme.primary}
              style="stroke"
              strokeWidth={CURVE_STROKE}
              strokeCap="round"
              strokeJoin="round"
            />
          </Group>
          {axes.xTicks.map((tick) =>
            label(`x-${tick.value}`, tick.px - measure(tick.text) / 2, tick.py, tick.text),
          )}
          {axes.yTicks.map((tick) =>
            label(`y-${tick.value}`, Math.max(4, tick.px - measure(tick.text)), tick.py, tick.text),
          )}
          {showOrigin ? label("origin", originLabel.px, originLabel.py, "0") : null}
          {label("x-caption", xCaption.px, xCaption.py, xLabel)}
          {label("y-caption", TRAJECTORY_PAD, TRAJECTORY_PAD - 10, yLabel)}
          <Circle c={dot} r={DOT_RADIUS + 1.5} color={theme.bg} />
          <Circle c={dot} r={DOT_RADIUS} color={theme.primary} />
        </Canvas>
      </View>
      {screenPoints.length > 1 ? (
        <PlaybackButton
          testID="trajectory"
          isPlaying={isPlaying}
          onPlay={play}
          onPause={pause}
          playLabel={t("rich.graph_play_a11y")}
          pauseLabel={t("rich.simulation_pause_a11y")}
        />
      ) : null}
    </View>
  );
}
