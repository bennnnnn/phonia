/**
 * Where everything in a ray diagram goes on its canvas: the element at
 * x = 0, the focal marks, the rays and their direction marks, the object and
 * the image, the angle arcs, the measure lines, and every label.
 *
 * Labels go where no ray, mark or other label is: each candidate in turn,
 * and every label placed becomes something the next one avoids. The
 * renderer (`components/rich/diagrams/RayDiagram.tsx`) only draws this.
 */
import {
  angleArc,
  angleLabel,
  elementExtent,
  firstClearLabel,
  focalPoints,
  hatchSegments,
  labelBox,
  layoutMeasure,
  mediumLabelSide,
  mirrorCurve,
  placeLabel,
  polylineSegments,
  RAY_HEAD,
  rayMarks,
  toScreen,
  worldTransform,
  type DiagramAngle,
  type LabelPlacement,
  type MeasureLayout,
  type MeasureVector,
  type Obstacle,
  type OpticsArrow,
  type OpticsSpec,
  type RayMark,
  type ScreenPoint,
  type Segment,
  type WorldBounds,
} from "@/lib/physics/optics";

/** A lens's arrowheads, which stand past the ends of its line. */
export const LENS_HEAD = 8;
/** Longest head an object or image arrow gets. */
const ARROW_HEAD = 8;
const FOCUS_TICK = 4;
const LABEL_GAP = 5;
const MEDIUM_INSET = 8;

/** What the diagram fence carries for a ray scene. */
export type RaySceneSpec = {
  bounds: WorldBounds;
  optics: OpticsSpec;
  angles: DiagramAngle[];
  measures: MeasureVector[];
};

/**
 * The element: a lens's line between the scene's extent (out-turned heads
 * converge light, in-turned ones spread it), an interface's boundary along
 * the axis, or a mirror's face with its hatching behind.
 */
type RayElement =
  | { kind: "lens"; outward: boolean }
  | { kind: "interface" }
  | { kind: "mirror"; curve: ScreenPoint[]; hatches: Segment[] };

/** An object or an image standing on the axis at `x`; `uy` is -1 when it points up. */
export type StandingArrow = { x: number; length: number; uy: number; head: number; virtual: boolean };

type SceneRay = { virtual: boolean; points: ScreenPoint[]; marks: RayMark[] };

type SceneAngle = {
  points: ScreenPoint[];
  endDirection: { ux: number; uy: number };
  arrow: boolean;
  role: "given" | "result";
  label?: string;
};

export type RayScene = {
  axis: number;
  elementX: number;
  extent: { top: number; bottom: number };
  element: RayElement;
  focusTicks: Segment[];
  rays: SceneRay[];
  object: StandingArrow | null;
  image: StandingArrow | null;
  angles: SceneAngle[];
  angleLabels: (LabelPlacement | null)[];
  measures: MeasureLayout[];
  objectLabel: LabelPlacement | null;
  imageLabel: LabelPlacement | null;
  focusLabels: LabelPlacement[];
  media: LabelPlacement[];
};

function standingArrow(arrow: OpticsArrow, x: number, scale: number): StandingArrow {
  const length = Math.abs(arrow.height) * scale;
  return {
    x,
    length,
    uy: arrow.height > 0 ? -1 : 1,
    head: Math.min(ARROW_HEAD, length * 0.45),
    virtual: arrow.virtual,
  };
}

/** The element's shape, and the strokes a label must not straddle. */
function layoutElement(
  optics: OpticsSpec,
  elementX: number,
  axis: number,
  extent: { top: number; bottom: number },
  canvas: { width: number; height: number },
): { element: RayElement; segments: Segment[] } {
  if (optics.element === "converging_lens" || optics.element === "diverging_lens") {
    return {
      element: { kind: "lens", outward: optics.element === "converging_lens" },
      segments: [{ x1: elementX, y1: extent.top - LENS_HEAD, x2: elementX, y2: extent.bottom + LENS_HEAD }],
    };
  }
  if (optics.element === "interface") {
    // The boundary and its normal: an angle's label must not straddle either.
    return {
      element: { kind: "interface" },
      segments: [
        { x1: 0, y1: axis, x2: canvas.width, y2: axis },
        { x1: elementX, y1: 0, x2: elementX, y2: canvas.height },
      ],
    };
  }
  const curve = mirrorCurve(optics.element, elementX, axis, extent.top, extent.bottom);
  const hatches = hatchSegments(curve);
  return { element: { kind: "mirror", curve, hatches }, segments: [...polylineSegments(curve), ...hatches] };
}

/** Each medium's name in its half, on the side away from the rays there. */
function layoutMedia(
  optics: OpticsSpec,
  rays: SceneRay[],
  axis: number,
  canvas: { width: number; height: number },
  measure: (text: string) => number,
): LabelPlacement[] {
  if (optics.element !== "interface" || !optics.media) return [];
  const rayPoints = rays.map((ray) => ray.points);
  return optics.media.map((name, index) => {
    const top = index === 0;
    const nameWidth = measure(name);
    const side = mediumLabelSide(rayPoints, top, axis, canvas.width);
    const left = side === "left" ? MEDIUM_INSET : canvas.width - MEDIUM_INSET - nameWidth;
    return placeLabel(name, nameWidth, { px: left + nameWidth / 2, py: axis }, top ? "above" : "below", 7, canvas);
  });
}

type Frame = {
  transform: ReturnType<typeof worldTransform>;
  canvas: { width: number; height: number };
  axis: number;
};

/**
 * Every label, each in the first of its candidate spots clear of the rays,
 * their marks, the element, the arrows, the measures and every label placed
 * before it. The angle arcs join the obstacles before the angles' labels.
 */
function placeLabels(
  spec: RaySceneSpec,
  { transform, canvas, axis }: Frame,
  drawn: { rays: SceneRay[]; elementSegments: Segment[]; measures: MeasureLayout[]; focus: number[]; angles: SceneAngle[] },
  measure: (text: string) => number,
  focusText: string,
) {
  const { optics } = spec;
  const arrowX = (arrow: OpticsArrow) => toScreen(arrow.x, 0, transform).px;
  const obstacles: Obstacle[] = [
    ...drawn.rays.flatMap((ray) => polylineSegments(ray.points)),
    ...drawn.rays.flatMap((ray) => ray.marks.map((m) => ({ x: m.x - RAY_HEAD, y: m.y - RAY_HEAD, width: RAY_HEAD * 2, height: RAY_HEAD * 2 }))),
    ...drawn.elementSegments,
    ...[optics.object, optics.image].flatMap((arrow) =>
      arrow ? [{ x1: arrowX(arrow), y1: axis, x2: arrowX(arrow), y2: axis - arrow.height * transform.scale }] : [],
    ),
    ...drawn.measures.flatMap((item) => (item.label ? [labelBox(item.label)] : [])),
  ];
  const place = (candidates: LabelPlacement[]) => {
    const label = firstClearLabel(candidates, obstacles);
    obstacles.push(labelBox(label));
    return label;
  };

  const standingLabel = (arrow: OpticsArrow | undefined) => {
    if (!arrow?.label) return null;
    const labelWidth = measure(arrow.label);
    const tip: ScreenPoint = { px: arrowX(arrow), py: axis - arrow.height * transform.scale };
    const foot: ScreenPoint = { px: tip.px, py: axis };
    const upright = arrow.height > 0;
    // Past the tip first, then beside it, then on the far side of the axis.
    return place([
      placeLabel(arrow.label, labelWidth, tip, upright ? "above" : "below", LABEL_GAP, canvas),
      placeLabel(arrow.label, labelWidth, tip, "right", LABEL_GAP, canvas),
      placeLabel(arrow.label, labelWidth, tip, "left", LABEL_GAP, canvas),
      placeLabel(arrow.label, labelWidth, foot, upright ? "below" : "above", LABEL_GAP, canvas),
    ]);
  };
  const objectLabel = standingLabel(optics.object);
  const imageLabel = standingLabel(optics.image);

  const focusWidth = measure(focusText);
  const focusLabels = drawn.focus.map((px) =>
    place([
      placeLabel(focusText, focusWidth, { px, py: axis + FOCUS_TICK }, "below", 3, canvas),
      placeLabel(focusText, focusWidth, { px, py: axis - FOCUS_TICK }, "above", 3, canvas),
    ]),
  );

  for (const angle of drawn.angles) obstacles.push(...polylineSegments(angle.points));
  const angleLabels = drawn.angles.map((angle, index) => {
    if (!angle.label) return null;
    const label = angleLabel(spec.angles[index], angle.label, measure(angle.label), transform, obstacles, canvas);
    obstacles.push(labelBox(label));
    return label;
  });
  return { objectLabel, imageLabel, focusLabels, angleLabels };
}

/** The whole scene at `width` × `height`; `focusText` is the focal mark's label. */
export function layoutRayScene(
  spec: RaySceneSpec,
  width: number,
  height: number,
  measure: (text: string) => number,
  focusText: string,
): RayScene {
  const { optics } = spec;
  const transform = worldTransform(spec.bounds, width, height);
  const canvas = { width, height };
  const axis = transform.offsetY;
  const elementX = toScreen(0, 0, transform).px;
  const extent = elementExtent(optics, spec.bounds, transform, height);
  const { element, segments: elementSegments } = layoutElement(optics, elementX, axis, extent, canvas);

  const focus = focalPoints(optics).map((x) => toScreen(x, 0, transform).px);
  const focusTicks = focus.map((px) => ({ x1: px, y1: axis - FOCUS_TICK, x2: px, y2: axis + FOCUS_TICK }));

  const rays = optics.rays.map((ray) => {
    const points = ray.points.map((p) => toScreen(p.x, p.y, transform));
    return { virtual: ray.virtual, points, marks: ray.virtual ? [] : rayMarks(points, { x: 0, y: 0, width, height }) };
  });

  const standing = (arrow: OpticsArrow | undefined) =>
    arrow ? standingArrow(arrow, toScreen(arrow.x, 0, transform).px, transform.scale) : null;
  const measures = spec.measures.map((vector) => layoutMeasure(vector, transform, canvas, measure));
  const angles = spec.angles.map((angle) => {
    const arc = angleArc(angle, transform);
    return { points: arc.points, endDirection: arc.endDirection, arrow: angle.arrow, role: angle.role, label: angle.label };
  });
  const labels = placeLabels(
    spec,
    { transform, canvas, axis },
    { rays, elementSegments, measures, focus, angles },
    measure,
    focusText,
  );

  return {
    axis,
    elementX,
    extent,
    element,
    focusTicks,
    rays,
    object: standing(optics.object),
    image: standing(optics.image),
    angles,
    measures,
    ...labels,
    media: layoutMedia(optics, rays, axis, canvas, measure),
  };
}
