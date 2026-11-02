import { type LabelBox, type Segment } from "@/lib/physics/simulation/labels";
import { sceneFrames } from "@/lib/physics/simulation/layoutFrames";
import {
  labelObstacles,
  layoutBodyLabels,
  type BodyLabelLayout,
  type PlanetLayout,
  type SolidLayout,
} from "@/lib/physics/simulation/layoutLabels";
import {
  placeAngleLabels,
  placeArrowLabels,
  placeVectorLabels,
  planVectorLabels,
  separateLabels,
  wantedAngleLabels,
  wantedArrowLabels,
  wantedVectorLabels,
  type ArrowLabelLayout,
  type VectorLayout,
} from "@/lib/physics/simulation/layoutNudgedLabels";
import {
  layoutAngles,
  layoutDerivedArrows,
  layoutTethers,
  layoutVectors,
  type AngleLayout,
  type PulleyLayout,
  type TetherLayout,
} from "@/lib/physics/simulation/layoutShapes";
import { isStationary, strobeIndices } from "@/lib/physics/simulation/paths";
import { type SimulationSpec } from "@/lib/physics/simulation/spec";
import { type ScreenPoint, type SimulationTransform } from "@/lib/physics/simulation/viewport";

export type SceneLayout = {
  radii: number[];
  /** Screen rotation of each box body, in radians; null for a circle. */
  boxAngles: (number | null)[];
  /** Each body's path on screen. */
  tracks: ScreenPoint[][];
  closed: boolean[];
  /** The fastest any body moves, for velocity arrow lengths; 0 without them. */
  maxSpeed: number;
  /** Screen y of the ground line, when the scene has one. */
  floorY: number | null;
  /** Screen rects a derived arrow stops at (solids, not fluids). */
  obstacles: LabelBox[];
  vectors: VectorLayout[];
  bodyLabels: (BodyLabelLayout | null)[];
  angles: AngleLayout[];
  arrowLabels: ArrowLabelLayout[];
  solids: SolidLayout[];
  planet: PlanetLayout | null;
  tethers: TetherLayout[];
  pulley: PulleyLayout | null;
  /** A pendulum's dashed rest line under each pivot. */
  restLines: Segment[];
  /** Where each body's faint strobe copies sit; empty for a body that never moves. */
  strobes: ScreenPoint[][];
};

/**
 * Every static piece of a scene's layout, worked out once per size: stated
 * vectors with their lengths, canvas fit and labels, which side of each body
 * its label goes, the angles, solids, strings and pulley, and where each
 * derived arrow's label sits relative to its tip.
 *
 * `measureText` is the font's width for a string. A scene that moves is
 * checked at `LAYOUT_FRAMES` moments, not just its first: a label riding on a
 * body is nudged once, so it has to be clear all the way through.
 */
export function layoutSimulationScene(
  spec: SimulationSpec,
  transform: SimulationTransform,
  width: number,
  height: number,
  measureText: (text: string) => number,
  fontSize: number,
): SceneLayout {
  const scene = sceneFrames({ spec, transform, width, height, measureText, fontSize });
  const { shafts, vectorLines } = layoutVectors(scene);
  const { derived, derivedLines } = layoutDerivedArrows(scene);
  const { tethers, restLines, tetherLines, pulley } = layoutTethers(scene);
  const { angleShapes, arcLines } = layoutAngles(scene);
  const lines = { vectorLines, derivedLines, tetherLines, restLines, arcLines };
  const { fixed, solids, planet } = labelObstacles(scene, pulley);
  const bodyLabels = layoutBodyLabels(scene, lines, derived, fixed);
  const plans = planVectorLabels(scene, shafts);
  const wanted = [
    ...wantedVectorLabels(scene, shafts, plans, lines),
    ...wantedAngleLabels(scene, angleShapes, lines),
    ...wantedArrowLabels(scene, derived, lines),
  ];
  const outcome = separateLabels(scene, wanted, fixed);
  const vectors = placeVectorLabels(shafts, plans, outcome);
  const angles = placeAngleLabels(angleShapes, outcome);
  const arrowLabels = placeArrowLabels(scene, derived, outcome);
  const { radii, boxAngles, tracks, closed, maxSpeed, floorY, obstacles } = scene;

  const strobes = spec.bodies.map((body, index) =>
    isStationary(body)
      ? []
      : strobeIndices(body.path.length, spec.strobe).map((i) => tracks[index][i]),
  );

  return {
    radii,
    boxAngles,
    tracks,
    closed,
    maxSpeed,
    floorY,
    obstacles,
    vectors,
    bodyLabels,
    angles,
    arrowLabels,
    solids,
    planet,
    tethers,
    pulley,
    restLines,
    strobes,
  };
}
