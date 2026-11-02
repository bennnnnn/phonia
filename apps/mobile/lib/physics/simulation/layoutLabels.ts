/**
 * What the nudged labels keep clear of, placed before them: the bodies, the
 * pulley, and the labels that are not nudged (the solids', the planet's and
 * each body's).
 */
import {
  bodyLabelOffset,
  clampBox,
  LABEL_ASCENT,
  placedLabel,
  polylineSegments,
  type BodyLabelSide,
  type LabelBox,
  type PlacedLabel,
  type Segment,
} from "@/lib/physics/simulation/labels";
import { chooseBodyLabelSideAcrossFrames } from "@/lib/physics/simulation/labelSearch";
import { type SceneFrames } from "@/lib/physics/simulation/layoutFrames";
import {
  type DerivedArrow,
  type PulleyLayout,
  type SceneLines,
} from "@/lib/physics/simulation/layoutShapes";
import { isStationary } from "@/lib/physics/simulation/paths";
import { type SimulationSolid } from "@/lib/physics/simulation/spec";
import { type ScreenPoint } from "@/lib/physics/simulation/viewport";

export type BodyLabelLayout = {
  side: BodyLabelSide;
  /** Offset from the body's centre to the label's left edge and baseline. */
  dx: number;
  dy: number;
  width: number;
};

export type SolidLayout = { solid: SimulationSolid; box: LabelBox; label: PlacedLabel | null };

export type PlanetLayout = { centre: ScreenPoint; radius: number; label: PlacedLabel | null };

/** Each frame's boxes a nudged label keeps clear of, with the solids and the planet laid out. */
export function labelObstacles(
  scene: SceneFrames,
  pulley: PulleyLayout | null,
): { fixed: LabelBox[][]; solids: SolidLayout[]; planet: PlanetLayout | null } {
  const { spec, width, height, measureText, fontSize, extents, solidBoxes } = scene;
  const { progresses, positions } = scene;
  const fixed: LabelBox[][] = progresses.map(() => []);
  spec.bodies.forEach((_body, index) => {
    const extent = extents[index];
    positions[index].forEach((point, frame) => {
      fixed[frame].push({
        x: point.px - extent,
        y: point.py - extent,
        width: extent * 2,
        height: extent * 2,
      });
    });
  });
  if (pulley) {
    for (const boxes of fixed) {
      boxes.push({
        x: pulley.centre.px - pulley.radius,
        y: pulley.centre.py - pulley.radius,
        width: pulley.radius * 2,
        height: pulley.radius * 2,
      });
    }
  }

  // Solids are labelled inside, near their top-left corner.
  const solids: SolidLayout[] = spec.solids.map((solid, index) => {
    const box = solidBoxes[index];
    if (!solid.label) return { solid, box, label: null };
    const labelBox = clampBox(
      { x: box.x + 4, y: box.y + 4, width: measureText(solid.label), height: fontSize },
      width,
      height,
    );
    for (const boxes of fixed) boxes.push(labelBox);
    return { solid, box, label: placedLabel(solid.label, labelBox) };
  });

  return { fixed, solids, planet: layoutPlanet(scene, fixed) };
}

/** The planet, and its name where `sceneFrames` placed it. */
function layoutPlanet(scene: SceneFrames, fixed: LabelBox[][]): PlanetLayout | null {
  const { spec, transform, centre, planetName } = scene;
  if (!spec.centralBody || !centre) return null;
  const radius = spec.centralBody.radius * transform.scale;
  let label: PlacedLabel | null = null;
  if (spec.centralBody.label && planetName) {
    for (const boxes of fixed) boxes.push(planetName.box);
    label = placedLabel(spec.centralBody.label, planetName.box);
  }
  return { centre, radius, label };
}

/** Which side of each body its label goes, added to `fixed` at every frame. */
export function layoutBodyLabels(
  scene: SceneFrames,
  lines: SceneLines,
  derived: DerivedArrow[],
  fixed: LabelBox[][],
): (BodyLabelLayout | null)[] {
  const { spec, width, height, measureText, fontSize, extents, tracks } = scene;
  const { floorY, progresses, positions } = scene;
  const { vectorLines, derivedLines, tetherLines, restLines } = lines;
  const groundLine: Segment[] =
    floorY === null ? [] : [{ x1: 0, y1: floorY, x2: width, y2: floorY }];
  return spec.bodies.map((body, index) => {
    if (!body.label) return null;
    const extent = extents[index];
    const labelWidth = measureText(body.label);
    // Its own path counts too: a label riding beside a body that moves
    // sideways would sit on the track it is about to run along.
    const track = isStationary(body) ? [] : polylineSegments(tracks[index]);
    const obstaclesAt = progresses.map((_, frame) => [
      ...vectorLines.flatMap((frames) => (frames[frame] ? [frames[frame]!] : [])),
      ...derived.flatMap((entry, i) => {
        const line = derivedLines[i][frame];
        return entry.body === index && line ? [line] : [];
      }),
      ...tetherLines.flatMap((frames) => (frames[frame] ? [frames[frame]!] : [])),
      ...restLines,
      ...groundLine,
      ...track,
    ]);
    const side = chooseBodyLabelSideAcrossFrames(
      positions[index],
      extent,
      labelWidth,
      fontSize,
      body.role,
      obstaclesAt,
      width,
      height,
    );
    const offset = bodyLabelOffset(side, extent, labelWidth, fontSize);
    positions[index].forEach((point, frame) => {
      // The renderer keeps a moving label on the canvas every frame.
      fixed[frame].push(
        clampBox(
          { x: point.px + offset.dx, y: point.py + offset.dy, width: labelWidth, height: fontSize },
          width,
          height,
        ),
      );
    });
    return {
      side,
      dx: offset.dx,
      dy: offset.dy + fontSize * LABEL_ASCENT,
      width: labelWidth,
    };
  });
}
