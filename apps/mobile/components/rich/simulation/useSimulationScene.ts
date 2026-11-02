/** What `SimulationBlock` draws from: the scene read from its fence, laid out, and its clock. */
import { useCallback, useMemo } from "react";
import { useWindowDimensions } from "react-native";
import { useTranslation } from "react-i18next";
import { useFont, type SkFont } from "@shopify/react-native-skia";

import {
  inclineDirections,
  inclineSurface,
  inclineWedge,
  layoutSimulationScene,
  parseSimulationSpec,
  sceneTitle,
  SIMULATION_HEIGHT,
  SIMULATION_MIN_HEIGHT,
  SIMULATION_PAD,
  simulationAccessibilityLabel,
  simulationIsAnimated,
  simulationTransform,
  simulationViewportHeight,
  worldToScreen,
  type SceneLayout,
  type SimulationSpec,
} from "@/lib/physics/simulation";
import { DIAGRAM_KINDS } from "@/lib/physics/diagramKind";
import { SCENE_KINDS } from "@/lib/physics/simulation/parse";
import { Motion } from "@/lib/motion";
import { useTheme } from "@/lib/theme";
import { makeFigureFrameStyles } from "@/components/rich/diagrams/DiagramFrame";
import { figureWidth } from "@/components/rich/figure";
import { usePlayback } from "@/components/rich/usePlayback";
import { measureRuns } from "@/components/rich/skia/fontRuns";
import { pointsPath } from "@/components/rich/skia/paths";
import { LABEL_FONT_SIZE } from "@/components/rich/simulation/labels";
import { useFenceRefused } from "@/components/rich/useFenceRefused";

/** The math faces set a size larger, so a τ stands as tall as SpaceMono's x-height beside it. */
const FALLBACK_FONT_SIZE = 13;
/** Until the font loads, a rough SpaceMono advance keeps the layout sane. */
const FALLBACK_CHAR_WIDTH = 6.7;

/** A circuit, rays and a wave reach `PhysicsDiagram`; any other type is no kind this build draws. */
const SCENE_BODY = { json: true, kinds: { field: "type", known: [...SCENE_KINDS, ...DIAGRAM_KINDS] } };

/** Periodic motion goes round again while playing; the rest hold their end. */
const PERIODIC: readonly SimulationSpec["type"][] = ["orbit", "spring", "pendulum"];

export function useSimulationScene(content: string) {
  const theme = useTheme();
  const { t } = useTranslation();
  const { width: screenWidth } = useWindowDimensions();
  const font = useFont(require("@/assets/fonts/SpaceMono-Regular.ttf"), LABEL_FONT_SIZE);
  // SpaceMono has no Greek: τ, θ, λ and Ω come from the math faces instead,
  // upright for units and capitals, italic for lower-case variables.
  const upright = useFont(require("@/assets/fonts/KaTeX_Main-Regular.ttf"), FALLBACK_FONT_SIZE);
  const italic = useFont(require("@/assets/fonts/KaTeX_Math-Italic.ttf"), FALLBACK_FONT_SIZE);
  const fallbacks = useMemo(() => [upright, italic], [italic, upright]);
  const spec = useMemo(() => parseSimulationSpec(content), [content]);
  useFenceRefused("simulation", content, spec === null, SCENE_BODY);
  const width = figureWidth(screenWidth);
  const styles = useMemo(() => makeFigureFrameStyles(theme), [theme]);
  const height = useMemo(
    () =>
      spec
        ? simulationViewportHeight(
            spec,
            width,
            SIMULATION_PAD,
            SIMULATION_MIN_HEIGHT,
            SIMULATION_HEIGHT,
          )
        : SIMULATION_HEIGHT,
    [spec, width],
  );
  const transform = useMemo(
    () => (spec ? simulationTransform(spec, width, height, SIMULATION_PAD) : null),
    [height, spec, width],
  );
  const animated = useMemo(() => (spec ? simulationIsAnimated(spec) : false), [spec]);
  const measure = useCallback(
    (text: string) =>
      font
        ? measureRuns(text, [font, ...fallbacks.filter((face): face is SkFont => face !== null)])
        : text.length * FALLBACK_CHAR_WIDTH,
    [fallbacks, font],
  );
  const layout = useMemo(
    () =>
      spec && transform
        ? layoutSimulationScene(spec, transform, width, height, measure, LABEL_FONT_SIZE)
        : null,
    [height, measure, spec, transform, width],
  );
  // A spring's coil already runs along its path, so a trail would only
  // stripe the coil.
  const trackPaths = useMemo(
    () => (spec?.type === "spring" || !layout ? [] : layout.tracks.map(pointsPath)),
    [layout, spec],
  );
  const description = useMemo(() => (spec ? simulationAccessibilityLabel(spec, t) : ""), [spec, t]);
  const title = useMemo(() => (spec ? sceneTitle(spec, t) : ""), [spec, t]);
  const playback = usePlayback({
    duration: Motion.duration.simulation,
    animated,
    autoplay: true,
    loop: spec !== null && PERIODIC.includes(spec.type),
    resetKey: content,
  });
  return {
    theme,
    t,
    font,
    fallbacks,
    spec,
    width,
    styles,
    height,
    transform,
    animated,
    layout,
    trackPaths,
    description,
    title,
    ...playback,
  };
}

/** Where the scene's fixed parts sit on screen: what its lines run along and its arrows aim at. */
export function sceneAnchors(
  spec: SimulationSpec,
  transform: ReturnType<typeof simulationTransform>,
  layout: SceneLayout,
) {
  const centre = spec.centre ? worldToScreen(spec.centre.x, spec.centre.y, transform) : null;
  const groundY = worldToScreen(0, 0, transform).py;
  const surface = inclineSurface(spec, transform);
  const wedge = inclineWedge(spec, transform);
  const slope = spec.inclineDeg !== undefined ? inclineDirections(spec.inclineDeg) : null;
  const beam = spec.beam
    ? {
        a: worldToScreen(spec.beam.x1, spec.beam.y1, transform),
        b: worldToScreen(spec.beam.x2, spec.beam.y2, transform),
      }
    : null;
  const pivot = spec.pivot ? worldToScreen(spec.pivot.x, spec.pivot.y, transform) : null;
  const anchor =
    spec.type === "spring" && spec.anchor
      ? worldToScreen(spec.anchor.x, spec.anchor.y, transform)
      : null;
  const wheel = layout.pulley
    ? { cx: layout.pulley.centre.px, cy: layout.pulley.centre.py, radius: layout.pulley.radius }
    : null;
  return { centre, groundY, surface, wedge, slope, beam, pivot, anchor, wheel };
}

