/**
 * A wave, stepped through the frames the server sampled over its fixed x
 * samples, looping. Nodes, antinodes, what holds the ends and the λ / A
 * measures are drawn around it; a still standing wave also shows its envelope.
 */
import { useMemo } from "react";
import { useWindowDimensions } from "react-native";
import { useTranslation } from "react-i18next";
import { Circle, DashPathEffect, Group, Path, Skia } from "@shopify/react-native-skia";
import { useDerivedValue } from "react-native-reanimated";

import { figureWidth } from "@/components/rich/figure";
import { PlaybackButton } from "@/components/rich/PlaybackButton";
import { usePlayback } from "@/components/rich/usePlayback";
import { linePath, segmentsPath } from "@/components/rich/skia/paths";
import {
  DiagramFrame,
  useDiagramFont,
  useDiagramTitle,
} from "@/components/rich/diagrams/DiagramFrame";
import { DiagramLabel, MeasureLine, rectPath } from "@/components/rich/diagrams/marks";
import type { WaveDiagramSpec } from "@/components/rich/diagrams/spec";
import { measureDiagramText } from "@/components/rich/diagrams/textWidth";
import { worldViewportHeight, type ScreenPoint } from "@/lib/physics/optics";
import { describeWave, isStandingWave, waveSamplesAt } from "@/lib/physics/wave";
import { layoutWaveScene, WAVE_NODE_RADIUS, type WaveScene } from "@/lib/physics/waveScene";
import { useTheme, withAlpha } from "@/lib/theme";

/**
 * One loop of the frames. Fixed rather than the real period, which ranges
 * from milliseconds (sound) to seconds (a rope): the shape and the way it
 * moves are the lesson, and the labels state the numbers.
 */
const WAVE_LOOP_MS = 2400;
const WAVE_STROKE = 2;

/** Two polylines in one path: the envelope's upper and lower edges. */
function polylinesPath(lines: readonly ScreenPoint[][]) {
  const path = Skia.Path.Make();
  for (const line of lines) {
    line.forEach((point, index) => {
      if (index === 0) path.moveTo(point.px, point.py);
      else path.lineTo(point.px, point.py);
    });
  }
  return path;
}

/** The scene's fixed strokes as Skia paths; only the curve changes per frame. */
function scenePaths(scene: WaveScene) {
  return {
    axisLine: linePath(scene.axisLine.x1, scene.axisLine.y1, scene.axisLine.x2, scene.axisLine.y2),
    envelope: polylinesPath(scene.envelope),
    clamps: scene.clamps.map((box) => rectPath(box.x, box.y, box.width, box.height)),
    pipe: scene.pipe ? segmentsPath(scene.pipe) : null,
    caps: segmentsPath(scene.caps),
    guides: scene.antinodes.map(({ guide }) => linePath(guide.x1, guide.y1, guide.x2, guide.y2)),
  };
}

export function WaveDiagram({ spec, content }: { spec: WaveDiagramSpec; content: string }) {
  const theme = useTheme();
  const { t } = useTranslation();
  const { width: screenWidth } = useWindowDimensions();
  const width = figureWidth(screenWidth);
  const font = useDiagramFont();
  const title = useDiagramTitle(spec);
  const height = useMemo(() => worldViewportHeight(spec.bounds, width), [spec, width]);
  // The title is its own text above the canvas, so the description does not repeat it.
  const description = useMemo(() => {
    const labels = spec.measures.flatMap((measure) => (measure.label ? [measure.label] : []));
    return spec.alt ?? describeWave(spec.wave, labels, t);
  }, [spec, t]);

  const scene = useMemo(
    () =>
      layoutWaveScene(spec, width, height, measureDiagramText, {
        node: t("rich.diagram_mark_node"),
        antinode: t("rich.diagram_mark_antinode"),
      }),
    [height, spec, t, width],
  );
  const paths = useMemo(() => scenePaths(scene), [scene]);

  const { progress, isPlaying, play, pause, reduceMotion } = usePlayback({
    duration: WAVE_LOOP_MS,
    animated: true,
    autoplay: true,
    loop: true,
    resetKey: content,
  });

  const { xs, frames, cycle, axis } = scene;
  const curve = useDerivedValue(() => {
    const ys = waveSamplesAt(frames, cycle, progress.value);
    const path = Skia.Path.Make();
    for (let i = 0; i < xs.length; i += 1) {
      if (i === 0) path.moveTo(xs[i], axis - ys[i]);
      else path.lineTo(xs[i], axis - ys[i]);
    }
    return path;
  });

  const standing = isStandingWave(spec.wave);
  // A still frame is a moment of the motion; the envelope shows the rest of it.
  const showEnvelope = standing && !isPlaying;
  const markers = [
    "diagram-wave",
    ...spec.wave.nodes.map(() => "diagram-node"),
    ...spec.wave.antinodes.map(() => "diagram-antinode"),
    ...spec.wave.ends.filter((end) => end !== "none").map((end) => `diagram-end-${end}`),
    ...spec.measures.map(() => "diagram-measure"),
    ...(showEnvelope ? ["diagram-envelope"] : []),
    ...(reduceMotion === true ? ["diagram-static"] : []),
  ];

  return (
    <DiagramFrame
      testID="wave-canvas"
      title={title}
      description={description}
      width={width}
      height={height}
      markers={markers}
      footer={
        <PlaybackButton
          testID="wave"
          isPlaying={isPlaying}
          onPlay={play}
          onPause={pause}
          playLabel={t("rich.diagram_wave_play_a11y")}
          pauseLabel={t("rich.diagram_wave_pause_a11y")}
        />
      }
    >
      <Group clip={Skia.XYWHRect(0, 0, width, height)}>
        <Path path={paths.axisLine} color={theme.textTertiary} style="stroke" strokeWidth={1} />
        {paths.pipe ? (
          <>
            <Path path={paths.pipe} color={theme.textSecondary} style="stroke" strokeWidth={2} strokeCap="round" />
            <Path path={paths.caps} color={theme.textSecondary} style="stroke" strokeWidth={3} strokeCap="round" />
          </>
        ) : null}
        {paths.clamps.map((path, index) => (
          <Path key={`clamp-${index}`} path={path} color={theme.textSecondary} />
        ))}
        {paths.guides.map((guide, index) => (
          <Path
            key={`antinode-${index}`}
            path={guide}
            color={withAlpha(theme.textTertiary, 0.7)}
            style="stroke"
            strokeWidth={1}
          >
            <DashPathEffect intervals={[2, 3]} />
          </Path>
        ))}
        {showEnvelope ? (
          <Path path={paths.envelope} color={withAlpha(theme.primary, 0.35)} style="stroke" strokeWidth={1}>
            <DashPathEffect intervals={[3, 3]} />
          </Path>
        ) : null}
        {scene.measures.map((measure, index) => (
          <MeasureLine key={`measure-${index}`} layout={measure} color={theme.textSecondary} />
        ))}
        <Path path={curve} color={theme.primary} style="stroke" strokeWidth={WAVE_STROKE} strokeJoin="round" strokeCap="round" />
        {scene.nodes.map((node, index) => (
          <Circle key={`node-${index}`} cx={node.at.px} cy={node.at.py} r={WAVE_NODE_RADIUS} color={theme.text} />
        ))}
      </Group>
      {font ? (
        <>
          {scene.nodes.map((node, index) => (
            <DiagramLabel key={`node-label-${index}`} label={node.label} font={font} color={theme.textSecondary} theme={theme} />
          ))}
          {scene.antinodes.map((antinode, index) => (
            <DiagramLabel
              key={`antinode-label-${index}`}
              label={antinode.label}
              font={font}
              color={theme.textTertiary}
              theme={theme}
            />
          ))}
          {scene.measures.map((measure, index) =>
            measure.label ? (
              <DiagramLabel
                key={`measure-label-${index}`}
                label={measure.label}
                font={font}
                color={theme.textSecondary}
                theme={theme}
              />
            ) : null,
          )}
        </>
      ) : null}
    </DiagramFrame>
  );
}
