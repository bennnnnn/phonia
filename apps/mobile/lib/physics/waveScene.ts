/**
 * Where everything in a wave diagram goes on its canvas: the sampled curve's
 * screen x and per-frame offsets, the still standing wave's envelope, what
 * holds each end (a clamp, or a pipe's walls and closed caps), the measure
 * lines, and the node and antinode marks with their labels.
 *
 * A node's or antinode's letter goes where no measure, clamp, wall or other
 * letter is. The renderer (`components/rich/diagrams/WaveDiagram.tsx`) only
 * draws this and steps the curve through the frames.
 */
import { type Box } from "@/lib/physics/boxes";
import {
  firstClearLabel,
  labelBox,
  labelHits,
  layoutMeasure,
  placeLabel,
  toScreen,
  worldTransform,
  type LabelPlacement,
  type LabelSide,
  type MeasureLayout,
  type MeasureVector,
  type Obstacle,
  type ScreenPoint,
  type Segment,
  type WorldBounds,
} from "@/lib/physics/optics";
import {
  sampleAt,
  waveCycleLength,
  waveEnvelope,
  waveHasPipe,
  type WaveSpec,
} from "@/lib/physics/wave";

/** A node's dot, which its letter clears. */
export const WAVE_NODE_RADIUS = 3;
const CLAMP_WIDTH = 7;
const PIPE_GAP = 10;
const GUIDE_OVERHANG = 4;
const MARK_GAP = 4;

/** What the diagram fence carries for a wave. */
type WaveSceneSpec = {
  bounds: WorldBounds;
  wave: WaveSpec;
  measures: MeasureVector[];
};

export type WaveScene = {
  /** Screen y of the rest line. */
  axis: number;
  /** Screen x of every sample. */
  xs: number[];
  /** Per frame, each sample's screen offset from the axis, positive up. */
  frames: number[][];
  cycle: number;
  axisLine: Segment;
  /** The upper then the lower edge of the envelope. */
  envelope: ScreenPoint[][];
  clamps: Box[];
  /** The pipe's two walls, or null when no end is a pipe's. */
  pipe: Segment[] | null;
  /** A closed pipe end's cap. */
  caps: Segment[];
  measures: MeasureLayout[];
  nodes: { at: ScreenPoint; label: LabelPlacement }[];
  antinodes: { guide: Segment; label: LabelPlacement }[];
};

/** The canvas a wave is laid out on, shared by every stage below. */
type WaveFrame = {
  transform: ReturnType<typeof worldTransform>;
  canvas: { width: number; height: number };
  /** Screen y of the rest line. */
  axis: number;
  /** Screen x of the first and last sample. */
  first: number;
  last: number;
  /** How far the wave reaches from the axis at its widest, in pixels. */
  reach: number;
  hasPipe: boolean;
  /** From the axis to a pipe's walls, in pixels. */
  wall: number;
};

type WaveEnds = { clamps: Box[]; walls: Segment[]; caps: Segment[] };

/** What holds each end: a clamp, or the walls and cap of a pipe. */
function layoutEnds(wave: WaveSpec, frame: WaveFrame): WaveEnds {
  const { axis, first, last, wall } = frame;
  const clampHalf = Math.max(frame.reach + 8, 12);
  const clamps: Box[] = wave.ends.flatMap((end, index) =>
    end === "fixed"
      ? [{ x: index === 0 ? first - CLAMP_WIDTH : last, y: axis - clampHalf, width: CLAMP_WIDTH, height: clampHalf * 2 }]
      : [],
  );
  const walls: Segment[] = [];
  if (frame.hasPipe) {
    walls.push(
      { x1: first, y1: axis - wall, x2: last, y2: axis - wall },
      { x1: first, y1: axis + wall, x2: last, y2: axis + wall },
    );
  }
  const caps: Segment[] = wave.ends.flatMap((end, index) => {
    if (!frame.hasPipe || end !== "closed") return [];
    const x = index === 0 ? first : last;
    return [{ x1: x, y1: axis - wall, x2: x, y2: axis + wall }];
  });
  return { clamps, walls, caps };
}

/**
 * What a node's or antinode's letter must not sit on. The wave itself is not
 * on the list: it moves through everything between its crests.
 */
function labelObstacles(measures: MeasureLayout[], ends: WaveEnds): Obstacle[] {
  return [
    ...measures.flatMap((line) => [
      { x1: line.from.px, y1: line.from.py, x2: line.to.px, y2: line.to.py },
      ...(line.label ? [labelBox(line.label)] : []),
    ]),
    ...measures.map((line) => ({ x: line.from.px - 5, y: line.from.py - 5, width: 10, height: 10 })),
    ...measures.map((line) => ({ x: line.to.px - 5, y: line.to.py - 5, width: 10, height: 10 })),
    ...ends.clamps,
    ...ends.walls,
    ...ends.caps,
  ];
}

/** A mark's letter on one side, centred or nudged clear of a clamp or a cap. */
function sideCandidates(
  text: string,
  textWidth: number,
  at: ScreenPoint,
  side: LabelSide,
  gap: number,
  canvas: WaveFrame["canvas"],
): LabelPlacement[] {
  const shift = textWidth / 2 + WAVE_NODE_RADIUS + 1;
  return [0, shift, -shift].map((dx) =>
    placeLabel(text, textWidth, { px: at.px + dx, py: at.py }, side, gap, canvas),
  );
}

/** Every node's letter on the same side when that side has room for all, else each where it fits. */
function placeNodeLabels(
  nodePoints: ScreenPoint[],
  text: string,
  textWidth: number,
  frame: WaveFrame,
  obstacles: Obstacle[],
): LabelPlacement[] {
  const { canvas } = frame;
  const gap = WAVE_NODE_RADIUS + MARK_GAP;
  const clear = (label: LabelPlacement) => !labelHits(label, obstacles);
  for (const side of ["below", "above"] as const) {
    const picks = nodePoints.map((at) => sideCandidates(text, textWidth, at, side, gap, canvas).find(clear));
    if (picks.every((pick): pick is LabelPlacement => pick !== undefined)) return picks;
  }
  return nodePoints.map((at) =>
    firstClearLabel(
      [
        ...sideCandidates(text, textWidth, at, "below", gap, canvas),
        ...sideCandidates(text, textWidth, at, "above", gap, canvas),
        ...(frame.hasPipe
          ? [placeLabel(text, textWidth, { px: at.px, py: frame.axis + frame.wall }, "below", 3, canvas)]
          : []),
      ],
      obstacles,
    ),
  );
}

/** Each antinode's dashed guide across the envelope, and its letter past one end (or a wall). */
function layoutAntinodes(
  wave: WaveSpec,
  envelope: number[],
  text: string,
  textWidth: number,
  frame: WaveFrame,
  obstacles: Obstacle[],
): WaveScene["antinodes"] {
  const { transform, canvas, axis, wall } = frame;
  return wave.antinodes.map((x) => {
    const px = toScreen(x, 0, transform).px;
    const half = sampleAt(wave.x, envelope, x) * transform.scale + GUIDE_OVERHANG;
    const top = { px, py: axis - half };
    const bottom = { px, py: axis + half };
    const label = firstClearLabel(
      [
        ...sideCandidates(text, textWidth, top, "above", 3, canvas),
        ...sideCandidates(text, textWidth, bottom, "below", 3, canvas),
        // In a pipe, past the walls.
        ...(frame.hasPipe
          ? [
              placeLabel(text, textWidth, { px, py: axis - wall }, "above", 3, canvas),
              placeLabel(text, textWidth, { px, py: axis + wall }, "below", 3, canvas),
            ]
          : []),
      ],
      obstacles,
    );
    obstacles.push(labelBox(label));
    return { guide: { x1: px, y1: top.py, x2: px, y2: bottom.py }, label };
  });
}

export function layoutWaveScene(
  spec: WaveSceneSpec,
  width: number,
  height: number,
  measure: (text: string) => number,
  text: { node: string; antinode: string },
): WaveScene {
  const { wave } = spec;
  const transform = worldTransform(spec.bounds, width, height);
  const canvas = { width, height };
  const axis = transform.offsetY;
  const xs = wave.x.map((x) => toScreen(x, 0, transform).px);
  const envelopeValues = waveEnvelope(wave);
  const reach = Math.max(...envelopeValues) * transform.scale;
  const frame: WaveFrame = {
    transform,
    canvas,
    axis,
    first: xs[0],
    last: xs[xs.length - 1],
    reach,
    hasPipe: waveHasPipe(wave),
    wall: reach + PIPE_GAP,
  };

  const ends = layoutEnds(wave, frame);
  const measures = spec.measures.map((vector) => layoutMeasure(vector, transform, canvas, measure));
  const obstacles = labelObstacles(measures, ends);
  const nodePoints = wave.nodes.map((x) => toScreen(x, 0, transform));
  const nodeLabels = placeNodeLabels(nodePoints, text.node, measure(text.node), frame, obstacles);
  obstacles.push(...nodeLabels.map(labelBox));
  const antinodes = layoutAntinodes(
    wave,
    envelopeValues,
    text.antinode,
    measure(text.antinode),
    frame,
    obstacles,
  );

  return {
    axis,
    xs,
    // Screen offsets, positive up, so the worklet only indexes and blends.
    frames: wave.frames.map((values) => values.map((value) => value * transform.scale)),
    cycle: waveCycleLength(wave.frames),
    axisLine: { x1: frame.first, y1: axis, x2: frame.last, y2: axis },
    envelope: [1, -1].map((sign) =>
      envelopeValues.map((value, index) => ({ px: xs[index], py: axis - sign * value * transform.scale })),
    ),
    clamps: ends.clamps,
    pipe: frame.hasPipe ? ends.walls : null,
    caps: ends.caps,
    measures,
    nodes: nodePoints.map((at, index) => ({ at, label: nodeLabels[index] })),
    antinodes,
  };
}
