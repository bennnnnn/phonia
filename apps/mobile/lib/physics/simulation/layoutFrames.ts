import { bodyBoxAngle, bodyExtent } from "@/lib/physics/simulation/arrows";
import { clampBox, LABEL_GAP, type LabelBox } from "@/lib/physics/simulation/labels";
import {
  endsWhereItStarts,
  isClosedPath,
  maxTrackSpeed,
  samplePathAt,
  simulationIsAnimated,
} from "@/lib/physics/simulation/paths";
import { type SimulationSpec } from "@/lib/physics/simulation/spec";
import {
  projectPath,
  worldToScreen,
  type ScreenPoint,
  type SimulationTransform,
} from "@/lib/physics/simulation/viewport";

/** Progress values the label pass checks a moving scene at. */
const LAYOUT_FRAMES = 17;

/** The smallest a body is drawn, so a 2 cm ball is still a dot. */
const MIN_BODY_RADIUS = 4;

/** Room an arrowhead or a label keeps from a planet's name. */
const NAME_CLEARANCE = 3;

function padded(box: LabelBox, by: number): LabelBox {
  return { x: box.x - by, y: box.y - by, width: box.width + 2 * by, height: box.height + 2 * by };
}

/**
 * What every stage of `layoutSimulationScene` reads: the scene on screen, and
 * where each body is at each frame the layout checks.
 */
export type SceneFrames = {
  spec: SimulationSpec;
  transform: SimulationTransform;
  width: number;
  height: number;
  measureText: (text: string) => number;
  fontSize: number;
  radii: number[];
  boxAngles: (number | null)[];
  extents: number[];
  tracks: ScreenPoint[][];
  closed: boolean[];
  maxSpeed: number;
  floorY: number | null;
  /** Each solid's rect on screen, fluids too. */
  solidBoxes: LabelBox[];
  /** What an arrow stops at and a label keeps off: the solids, and a planet's name inside it. */
  obstacles: LabelBox[];
  centre: ScreenPoint | null;
  /** The planet's name, in the middle of it or under it if it does not fit. */
  planetName: { box: LabelBox; inside: boolean } | null;
  progresses: number[];
  /** Each body's centre at each sampled frame. */
  positions: ScreenPoint[][];
  /** How far each body has moved by each sampled frame. */
  shifts: { dx: number; dy: number }[][];
  pulleyCentre: ScreenPoint | null;
  pulleyRadius: number;
};

type SceneInput = Pick<
  SceneFrames,
  "spec" | "transform" | "width" | "height" | "measureText" | "fontSize"
>;

export function sceneFrames(input: SceneInput): SceneFrames {
  const { spec, transform } = input;
  const radii = spec.bodies.map((body) => Math.max(body.radius * transform.scale, MIN_BODY_RADIUS));
  const boxAngles = spec.bodies.map((body) => bodyBoxAngle(spec, body));
  const extents = radii.map((radius, index) => bodyExtent(radius, boxAngles[index]));
  const tracks = spec.bodies.map((body) => projectPath(body.path, transform));
  // A pendulum is sampled over whole swings, and turns round at the join, so
  // `isClosedPath` (which wants motion carrying straight on) never says so;
  // wrapping its window there is what gives the bob no velocity at full swing.
  const closed = tracks.map(
    (track) => isClosedPath(track) || (spec.type === "pendulum" && endsWhereItStarts(track)),
  );
  const maxSpeed = spec.arrows.includes("velocity")
    ? tracks.reduce((best, track, index) => Math.max(best, maxTrackSpeed(track, closed[index])), 0)
    : 0;
  const floorY = spec.ground ? worldToScreen(0, 0, transform).py : null;
  const solidBoxes = spec.solids.map((solid) => {
    const topLeft = worldToScreen(solid.rect.xMin, solid.rect.yMax, transform);
    const bottomRight = worldToScreen(solid.rect.xMax, solid.rect.yMin, transform);
    return {
      x: topLeft.px,
      y: topLeft.py,
      width: bottomRight.px - topLeft.px,
      height: bottomRight.py - topLeft.py,
    };
  });
  const centre = spec.centre ? worldToScreen(spec.centre.x, spec.centre.y, transform) : null;
  const planetName = planetNameBox(input, centre);
  // Gravity points at the planet's centre, so its arrow ran through the name in a
  // fifth of an orbit. A name inside the disc stops the arrow, and its label steps
  // aside; one under the disc is where the body itself passes, so it stays clear.
  const obstacles = [
    ...solidBoxes.filter((_, index) => spec.solids[index].kind === "solid"),
    ...(planetName?.inside ? [padded(planetName.box, NAME_CLEARANCE)] : []),
  ];

  const animated = simulationIsAnimated(spec);
  const progresses = animated
    ? Array.from({ length: LAYOUT_FRAMES }, (_, i) => i / (LAYOUT_FRAMES - 1))
    : [0];
  const positions = tracks.map((track) =>
    progresses.map((progress) => samplePathAt(track, progress * (track.length - 1))),
  );
  const shifts = positions.map((frames) =>
    frames.map((point) => ({ dx: point.px - frames[0].px, dy: point.py - frames[0].py })),
  );

  const pulleyCentre = spec.pulley
    ? worldToScreen(spec.pulley.centre.x, spec.pulley.centre.y, transform)
    : null;
  const pulleyRadius = spec.pulley ? spec.pulley.radius * transform.scale : 0;

  return {
    ...input,
    radii,
    boxAngles,
    extents,
    tracks,
    closed,
    maxSpeed,
    floorY,
    solidBoxes,
    obstacles,
    centre,
    planetName,
    progresses,
    positions,
    shifts,
    pulleyCentre,
    pulleyRadius,
  };
}

function planetNameBox(
  input: SceneInput,
  centre: ScreenPoint | null,
): { box: LabelBox; inside: boolean } | null {
  const { spec, transform, width, height, measureText, fontSize } = input;
  const label = spec.centralBody?.label;
  if (!spec.centralBody || !label || !centre) return null;
  const radius = spec.centralBody.radius * transform.scale;
  const labelWidth = measureText(label);
  // A labelled centripetal arrow ends near the centre, label and all, so the
  // name moves down to where its chord still holds it.
  const drop = spec.arrowLabels.centripetal ? 0.55 : 0;
  const chord = 2 * radius * Math.sqrt(1 - drop * drop);
  const inside = labelWidth + 8 <= chord * 0.9 && fontSize + 4 <= radius * 2 * (1 - drop);
  const box = clampBox(
    {
      x: centre.px - labelWidth / 2,
      y: inside ? centre.py + radius * drop - fontSize / 2 : centre.py + radius + LABEL_GAP,
      width: labelWidth,
      height: fontSize,
    },
    width,
    height,
  );
  return { box, inside };
}
