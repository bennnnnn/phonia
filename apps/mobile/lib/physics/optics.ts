/**
 * Parsing and geometry for the ray diagram (`simulation` fence, type `rays`),
 * and the world frame it shares with the wave diagram.
 *
 * The server traces every ray: each arrives as the polyline it follows, with
 * the object and the image already placed. Nothing here refracts or reflects
 * anything. This file maps world units onto the canvas with one scale for
 * both axes, so an angle on screen is the angle the solver used, and works out
 * where the marks around the rays go.
 *
 * The axis is y = 0 and the element stands at x = 0; light travels left to
 * right. An `interface` is the line y = 0 instead, with its normal along x = 0.
 */

import {
  finiteNumber,
  guard,
  optionalBool,
  optionalList,
  optionalText,
  refuse,
  requireNumber,
  requirePoint,
  requireRecord,
} from "@/lib/fenceValidate";
import { boxesOverlap, type Box } from "@/lib/physics/boxes";

type OpticsElement =
  | "converging_lens"
  | "diverging_lens"
  | "concave_mirror"
  | "convex_mirror"
  | "plane_mirror"
  | "interface";

const OPTICS_ELEMENTS: readonly OpticsElement[] = [
  "converging_lens",
  "diverging_lens",
  "concave_mirror",
  "convex_mirror",
  "plane_mirror",
  "interface",
];

type WorldPoint = { x: number; y: number };

/** An object or an image standing on the axis; a negative height is inverted. */
export type OpticsArrow = { x: number; height: number; label?: string; virtual: boolean };

type OpticsRay = { points: WorldPoint[]; virtual: boolean };

export type OpticsSpec = {
  element: OpticsElement;
  focal?: number;
  object?: OpticsArrow;
  image?: OpticsArrow;
  rays: OpticsRay[];
  /** The medium above the interface, then the one below. */
  media?: [string, string];
};

/** An arc at a vertex, degrees counter-clockwise from +x: an angle of incidence. */
export type DiagramAngle = {
  vertex: WorldPoint;
  startDeg: number;
  endDeg: number;
  label?: string;
  arrow: boolean;
  role: "given" | "result";
};

/** An extent drawn at its world length: the λ or the A of a wave. */
export type MeasureVector = { anchor: WorldPoint; dx: number; dy: number; label?: string };

export type WorldBounds = { xMin: number; xMax: number; yMin: number; yMax: number };

const MAX_LABEL = 24;
const MAX_RAYS = 8;
const MAX_RAY_POINTS = 8;
const MAX_MEDIUM = 16;
const MAX_ANGLES = 4;
const MAX_VECTORS = 6;
const VECTOR_ROLES = ["force", "result", "measure", "motion"];

function parseArrow(raw: unknown): OpticsArrow | undefined {
  if (raw === undefined || raw === null) return undefined;
  const row = requireRecord(raw);
  const height = requireNumber(row.height);
  if (height === 0) refuse();
  return {
    x: requireNumber(row.x),
    height,
    label: optionalText(row.label, MAX_LABEL),
    virtual: optionalBool(row.virtual, false),
  };
}

function parseRay(raw: unknown): OpticsRay {
  const row = requireRecord(raw);
  if (!Array.isArray(row.points) || row.points.length < 2 || row.points.length > MAX_RAY_POINTS) {
    refuse();
  }
  return { points: row.points.map(requirePoint), virtual: optionalBool(row.virtual, false) };
}

/**
 * Read the `optics` object of a fence, or null when it is malformed — as the
 * server model would: a lens or a curved mirror without its focal length, a
 * diagram with neither an object nor a ray, a non-finite point anywhere.
 */
export function parseOpticsSpec(raw: unknown): OpticsSpec | null {
  return guard(() => {
    const row = requireRecord(raw);
    if (!OPTICS_ELEMENTS.includes(row.element as OpticsElement)) refuse();
    const element = row.element as OpticsElement;
    let focal: number | undefined;
    if (row.focal !== undefined && row.focal !== null) {
      focal = requireNumber(row.focal);
      if (focal <= 0) refuse();
    }
    const curved = element !== "plane_mirror" && element !== "interface";
    if (curved && focal === undefined) refuse();
    let media: [string, string] | undefined;
    if (row.media !== undefined && row.media !== null) {
      if (!Array.isArray(row.media) || row.media.length !== 2) refuse();
      const names = row.media.map((name) => {
        if (typeof name !== "string" || [...name].length > MAX_MEDIUM) refuse();
        return name;
      });
      media = [names[0], names[1]];
    }
    const rays = optionalList(row.rays, MAX_RAYS).map(parseRay);
    const object = parseArrow(row.object);
    if (rays.length === 0 && !object) refuse();
    return { element, focal, object, image: parseArrow(row.image), rays, media };
  });
}

/** The fence's `angles`, or null when any one is malformed. */
export function parseDiagramAngles(raw: unknown): DiagramAngle[] | null {
  return guard(() =>
    optionalList(raw, MAX_ANGLES).map((entry) => {
      const row = requireRecord(entry);
      const startDeg = requireNumber(row.start_deg);
      const endDeg = requireNumber(row.end_deg);
      if (startDeg === endDeg) refuse();
      const role = row.role ?? "given";
      if (role !== "given" && role !== "result") refuse();
      return {
        vertex: requirePoint(row.vertex),
        startDeg,
        endDeg,
        label: optionalText(row.label, MAX_LABEL),
        arrow: optionalBool(row.arrow, false),
        role,
      };
    }),
  );
}

/**
 * The fence's `measure` vectors, or null when any vector is malformed.
 *
 * Every vector is validated as the server does, but only the measures are
 * returned: a diagram has no bodies for a force to act on, so it draws its
 * extents (the λ and the A of a wave) and nothing else.
 */
export function parseMeasureVectors(raw: unknown): MeasureVector[] | null {
  return guard(() => {
    const out: MeasureVector[] = [];
    for (const entry of optionalList(raw, MAX_VECTORS)) {
      const row = requireRecord(entry);
      const anchor = requirePoint(row.anchor);
      const dx = requireNumber(row.dx);
      const dy = requireNumber(row.dy);
      if (dx === 0 && dy === 0) refuse();
      const role = row.role ?? "force";
      if (!VECTOR_ROLES.includes(role as string)) refuse();
      // There is no body on a diagram for a vector to ride on.
      if (row.body !== undefined && row.body !== null) refuse();
      const label = optionalText(row.label, MAX_LABEL);
      if (role === "measure") out.push({ anchor, dx, dy, label });
    }
    return out;
  });
}

/** The scene box, defaulting like the server's model; null when unordered or non-finite. */
export function parseWorldBounds(row: Record<string, unknown>): WorldBounds | null {
  // The server's fields are plain floats with defaults: absent is the
  // default, but `null` is not a number.
  const read = (key: string, fallback: number) =>
    row[key] === undefined ? fallback : finiteNumber(row[key]);
  const xMin = read("x_min", 0);
  const xMax = read("x_max", 10);
  const yMin = read("y_min", 0);
  const yMax = read("y_max", 10);
  if (xMin === null || xMax === null || yMin === null || yMax === null) return null;
  if (xMax <= xMin || yMax <= yMin) return null;
  return { xMin, xMax, yMin, yMax };
}

// --- world frame (shared with the wave diagram) ---------------------------------

/** Padding inside the canvas around the scene box. */
const DIAGRAM_PAD = 16;
/** Shortest a world-mapped diagram's canvas gets (wide scenes). */
export const DIAGRAM_MIN_HEIGHT = 120;
/** Tallest it gets (square and tall scenes). */
export const DIAGRAM_MAX_HEIGHT = 240;

type WorldTransform = { scale: number; offsetX: number; offsetY: number };
export type ScreenPoint = { px: number; py: number };

/** The canvas height that fits the scene box at the full width, within the limits. */
export function worldViewportHeight(bounds: WorldBounds, width: number): number {
  const innerW = Math.max(width - DIAGRAM_PAD * 2, 1);
  const worldW = bounds.xMax - bounds.xMin;
  const worldH = bounds.yMax - bounds.yMin;
  const fit = (worldH / worldW) * innerW + DIAGRAM_PAD * 2;
  return Math.round(Math.max(DIAGRAM_MIN_HEIGHT, Math.min(DIAGRAM_MAX_HEIGHT, fit)));
}

/**
 * World units to screen pixels with **one** scale for both axes, letterboxed
 * and centred: a 30° ray must leave the interface at 30°.
 */
export function worldTransform(bounds: WorldBounds, width: number, height: number): WorldTransform {
  const innerW = Math.max(width - DIAGRAM_PAD * 2, 1);
  const innerH = Math.max(height - DIAGRAM_PAD * 2, 1);
  const worldW = bounds.xMax - bounds.xMin;
  const worldH = bounds.yMax - bounds.yMin;
  const scale = Math.min(innerW / worldW, innerH / worldH);
  return {
    scale,
    offsetX: DIAGRAM_PAD + (innerW - worldW * scale) / 2 - bounds.xMin * scale,
    // y grows up in the world and down on screen.
    offsetY: DIAGRAM_PAD + innerH - (innerH - worldH * scale) / 2 + bounds.yMin * scale,
  };
}

export function toScreen(x: number, y: number, t: WorldTransform): ScreenPoint {
  "worklet";
  return { px: x * t.scale + t.offsetX, py: t.offsetY - y * t.scale };
}

export type Segment = { x1: number; y1: number; x2: number; y2: number };

/**
 * The part of a segment inside a rectangle (Liang–Barsky), or null when it
 * misses. A ray traced to a point far off the canvas gets its direction mark
 * in the middle of what is actually visible.
 */
export function clipSegment(segment: Segment, rect: Box): Segment | null {
  const dx = segment.x2 - segment.x1;
  const dy = segment.y2 - segment.y1;
  let t0 = 0;
  let t1 = 1;
  const edges: [number, number][] = [
    [-dx, segment.x1 - rect.x],
    [dx, rect.x + rect.width - segment.x1],
    [-dy, segment.y1 - rect.y],
    [dy, rect.y + rect.height - segment.y1],
  ];
  for (const [p, q] of edges) {
    if (p === 0) {
      if (q < 0) return null;
      continue;
    }
    const r = q / p;
    if (p < 0) t0 = Math.max(t0, r);
    else t1 = Math.min(t1, r);
    if (t0 > t1) return null;
  }
  return {
    x1: segment.x1 + dx * t0,
    y1: segment.y1 + dy * t0,
    x2: segment.x1 + dx * t1,
    y2: segment.y1 + dy * t1,
  };
}

// --- labels and measure lines (shared with the wave diagram) --------------------

/** Room a 12 pt label takes above its baseline (caps) and below it (descenders). */
const LABEL_ASCENT = 9;
const LABEL_DESCENT = 3;
const LABEL_INSET = 4;

/** A label: `x` is its left edge, `y` its baseline. */
export type LabelPlacement = { text: string; x: number; y: number; width: number };
export type LabelSide = "above" | "below" | "left" | "right" | "centre";

export function labelBox(label: LabelPlacement): Box {
  return {
    x: label.x,
    y: label.y - LABEL_ASCENT,
    width: label.width,
    height: LABEL_ASCENT + LABEL_DESCENT,
  };
}

/**
 * A label `gap` px to one side of a point (or centred on it), then kept inside
 * the canvas: a label clipped by the edge is worse than one nudged off its mark.
 */
export function placeLabel(
  text: string,
  width: number,
  at: ScreenPoint,
  side: LabelSide,
  gap: number,
  canvas: { width: number; height: number },
): LabelPlacement {
  const middle = (LABEL_ASCENT - LABEL_DESCENT) / 2;
  let x = at.px - width / 2;
  let y = at.py + middle;
  if (side === "above") y = at.py - gap - LABEL_DESCENT;
  if (side === "below") y = at.py + gap + LABEL_ASCENT;
  if (side === "right") x = at.px + gap;
  if (side === "left") x = at.px - gap - width;
  return {
    text,
    width,
    x: Math.max(LABEL_INSET, Math.min(canvas.width - LABEL_INSET - width, x)),
    y: Math.max(LABEL_INSET + LABEL_ASCENT, Math.min(canvas.height - LABEL_INSET - LABEL_DESCENT, y)),
  };
}

/** Something a label must not sit on: a box (a clamp, another label) or a line (a ray, a wall). */
export type Obstacle = Box | Segment;

function isSegment(obstacle: Obstacle): obstacle is Segment {
  return "x1" in obstacle;
}

/** Whether a label touches any obstacle, with a little air around its box. */
export function labelHits(label: LabelPlacement, obstacles: readonly Obstacle[], air = 1.5): boolean {
  const box = labelBox(label);
  const padded = { x: box.x - air, y: box.y - air, width: box.width + air * 2, height: box.height + air * 2 };
  return obstacles.some((obstacle) =>
    isSegment(obstacle) ? clipSegment(obstacle, padded) !== null : boxesOverlap(padded, obstacle),
  );
}

/** The first candidate clear of every obstacle, or the first candidate when none is. */
export function firstClearLabel(
  candidates: readonly LabelPlacement[],
  obstacles: readonly Obstacle[],
): LabelPlacement {
  return candidates.find((label) => !labelHits(label, obstacles)) ?? candidates[0];
}

/** Polyline points as segments, for obstacle checks. */
export function polylineSegments(points: readonly ScreenPoint[]): Segment[] {
  const out: Segment[] = [];
  for (let i = 1; i < points.length; i += 1) {
    out.push({ x1: points[i - 1].px, y1: points[i - 1].py, x2: points[i].px, y2: points[i].py });
  }
  return out;
}

export type MeasureLayout = { from: ScreenPoint; to: ScreenPoint; label?: LabelPlacement };

const MEASURE_LABEL_GAP = 5;

/**
 * A measure at its world length, and its label beside its middle: away from
 * the axis for a level line (a λ under the trough reads below it), to the
 * right of an upright one unless the canvas ends there.
 */
export function layoutMeasure(
  vector: MeasureVector,
  t: WorldTransform,
  canvas: { width: number; height: number },
  measure: (text: string) => number,
): MeasureLayout {
  const from = toScreen(vector.anchor.x, vector.anchor.y, t);
  const to = toScreen(vector.anchor.x + vector.dx, vector.anchor.y + vector.dy, t);
  if (!vector.label) return { from, to };
  const mid = { px: (from.px + to.px) / 2, py: (from.py + to.py) / 2 };
  const width = measure(vector.label);
  let side: LabelSide;
  if (Math.abs(to.px - from.px) >= Math.abs(to.py - from.py)) {
    side = mid.py > t.offsetY + 0.5 ? "below" : "above";
  } else {
    side = mid.px + MEASURE_LABEL_GAP + width > canvas.width - LABEL_INSET ? "left" : "right";
  }
  return { from, to, label: placeLabel(vector.label, width, mid, side, MEASURE_LABEL_GAP, canvas) };
}

// --- ray diagram geometry -------------------------------------------------------

/** A direction mark on a ray: where its head's tip goes, and which way it points. */
export type RayMark = { x: number; y: number; ux: number; uy: number };

/** Visible segments shorter than this carry no direction mark. */
const RAY_MARK_MIN_LENGTH = 18;
export const RAY_HEAD = 6;

/** One mark per visible segment, its tip just past the visible midpoint. */
export function rayMarks(points: readonly ScreenPoint[], rect: Box): RayMark[] {
  const marks: RayMark[] = [];
  for (let i = 1; i < points.length; i += 1) {
    const clipped = clipSegment(
      { x1: points[i - 1].px, y1: points[i - 1].py, x2: points[i].px, y2: points[i].py },
      rect,
    );
    if (!clipped) continue;
    const length = Math.hypot(clipped.x2 - clipped.x1, clipped.y2 - clipped.y1);
    if (length < RAY_MARK_MIN_LENGTH) continue;
    const ux = (clipped.x2 - clipped.x1) / length;
    const uy = (clipped.y2 - clipped.y1) / length;
    const along = length / 2 + RAY_HEAD / 2;
    marks.push({ x: clipped.x1 + ux * along, y: clipped.y1 + uy * along, ux, uy });
  }
  return marks;
}

/**
 * Where the element's line ends on screen, above and below the axis.
 *
 * Tall enough to catch every ray that meets it, and most of the scene box,
 * without running off the canvas.
 */
export function elementExtent(
  spec: OpticsSpec,
  bounds: WorldBounds,
  t: WorldTransform,
  height: number,
  inset = 8,
): { top: number; bottom: number } {
  const hits = spec.rays.flatMap((ray) =>
    ray.points.filter((p) => Math.abs(p.x) < 1e-6).map((p) => Math.abs(p.y)),
  );
  const arrows = [spec.object, spec.image].flatMap((arrow) => (arrow ? [Math.abs(arrow.height)] : []));
  const span = Math.min(Math.abs(bounds.yMax), Math.abs(bounds.yMin)) || Math.max(bounds.yMax, -bounds.yMin);
  const half = Math.max(0.85 * span, ...hits.map((h) => h * 1.15), ...arrows.map((h) => h * 0.8)) * t.scale;
  const axis = t.offsetY;
  return { top: Math.max(inset, axis - half), bottom: Math.min(height - inset, axis + half) };
}

/** The deepest a mirror's arc bows, in px: shallow, so it still reads as a line at x = 0. */
const MIRROR_SAG = 7;

/**
 * A mirror's face as screen points from top to bottom. A concave mirror cups
 * the light, so its ends lean toward the incoming side (left); a convex one
 * bows toward it, so its ends lean away.
 */
export function mirrorCurve(
  element: OpticsElement,
  x: number,
  axis: number,
  top: number,
  bottom: number,
  samples = 24,
): ScreenPoint[] {
  const half = Math.max(axis - top, bottom - axis, 1);
  const lean = element === "concave_mirror" ? -1 : element === "convex_mirror" ? 1 : 0;
  const sag = Math.min(MIRROR_SAG, half * 0.2) * lean;
  const out: ScreenPoint[] = [];
  for (let i = 0; i <= samples; i += 1) {
    const py = top + ((bottom - top) * i) / samples;
    const u = (py - axis) / half;
    out.push({ px: x + sag * u * u, py });
  }
  return out;
}

/** Short diagonal ticks behind a mirror (its right side), every `spacing` px. */
export function hatchSegments(curve: readonly ScreenPoint[], spacing = 7, length = 6): Segment[] {
  if (curve.length < 2) return [];
  const top = curve[0].py;
  const bottom = curve[curve.length - 1].py;
  const out: Segment[] = [];
  for (let py = top + spacing / 2; py <= bottom; py += spacing) {
    const u = (py - top) / (bottom - top);
    const index = Math.min(curve.length - 2, Math.floor(u * (curve.length - 1)));
    const a = curve[index];
    const b = curve[index + 1];
    const f = b.py === a.py ? 0 : (py - a.py) / (b.py - a.py);
    const px = a.px + (b.px - a.px) * f;
    out.push({ x1: px, y1: py, x2: px + length, y2: py - length });
  }
  return out;
}

/**
 * The focal points, in world x. A lens has one each side. A mirror has one:
 * in front of a concave mirror, where reflected light really meets, and
 * behind a convex one, where it only appears to come from.
 */
export function focalPoints(spec: OpticsSpec): number[] {
  if (spec.focal === undefined) return [];
  switch (spec.element) {
    case "converging_lens":
    case "diverging_lens":
      return [-spec.focal, spec.focal];
    case "concave_mirror":
      return [-spec.focal];
    case "convex_mirror":
      return [spec.focal];
    default:
      return [];
  }
}

/** Screen radius of an angle's arc. */
const ANGLE_RADIUS = 26;

/**
 * Where an angle's label goes: inside the wedge on its bisector, moving out
 * until it clears the rays (a narrow wedge is wider further out), else just
 * outside the arc past either edge.
 */
export function angleLabel(
  angle: DiagramAngle,
  text: string,
  width: number,
  t: WorldTransform,
  obstacles: readonly Obstacle[],
  canvas: { width: number; height: number },
  radius = ANGLE_RADIUS,
): LabelPlacement {
  const centre = toScreen(angle.vertex.x, angle.vertex.y, t);
  const at = (deg: number, r: number): ScreenPoint => {
    const rad = (deg * Math.PI) / 180;
    return { px: centre.px + r * Math.cos(rad), py: centre.py - r * Math.sin(rad) };
  };
  const sweep = angle.endDeg - angle.startDeg;
  const mid = angle.startDeg + sweep / 2;
  const candidates: LabelPlacement[] = [];
  for (const out of [14, 22, 30, 40]) {
    candidates.push(placeLabel(text, width, at(mid, radius + out), "centre", 0, canvas));
  }
  const turn = Math.sign(sweep);
  for (const out of [16, 28]) {
    const r = radius + out / 2;
    // Past each edge by about half the label's width, seen from the vertex.
    const beyond = (Math.atan2(width / 2 + out / 2, r) * 180) / Math.PI;
    candidates.push(placeLabel(text, width, at(angle.endDeg + turn * beyond, r), "centre", 0, canvas));
    candidates.push(placeLabel(text, width, at(angle.startDeg - turn * beyond, r), "centre", 0, canvas));
  }
  return firstClearLabel(candidates, obstacles);
}

/** An angle's arc as screen points, and the direction of travel at its end (for an arrowhead). */
export function angleArc(
  angle: DiagramAngle,
  t: WorldTransform,
  radius = ANGLE_RADIUS,
): { points: ScreenPoint[]; endDirection: { ux: number; uy: number } } {
  const centre = toScreen(angle.vertex.x, angle.vertex.y, t);
  const sweep = angle.endDeg - angle.startDeg;
  const steps = Math.max(6, Math.ceil(Math.abs(sweep) / 6));
  const points: ScreenPoint[] = [];
  for (let i = 0; i <= steps; i += 1) {
    const rad = ((angle.startDeg + (sweep * i) / steps) * Math.PI) / 180;
    // Screen y points down, so a counter-clockwise world angle subtracts.
    points.push({ px: centre.px + radius * Math.cos(rad), py: centre.py - radius * Math.sin(rad) });
  }
  const end = (angle.endDeg * Math.PI) / 180;
  const turn = Math.sign(sweep);
  // The tangent at the end, in the direction of travel along the arc.
  return { points, endDirection: { ux: -Math.sin(end) * turn, uy: -Math.cos(end) * turn } };
}

/**
 * Which side of the canvas a medium's name goes in its half: the one farther
 * from the rays drawn there, so the name never sits on the light.
 */
export function mediumLabelSide(
  rays: readonly ScreenPoint[][],
  above: boolean,
  axis: number,
  width: number,
): "left" | "right" {
  const inHalf = rays.flat().filter((p) => (above ? p.py < axis - 1 : p.py > axis + 1));
  if (inHalf.length === 0) return "left";
  const meanX = inHalf.reduce((sum, p) => sum + p.px, 0) / inHalf.length;
  return meanX < width / 2 ? "right" : "left";
}

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** What a screen reader says when the fence has no `alt`. */
export function describeOptics(spec: OpticsSpec, angles: DiagramAngle[], t: Translate): string {
  const sentences = [t("rich.diagram_a11y_rays", { element: t(`rich.diagram_element_${spec.element}`) })];
  if (spec.media) sentences.push(t("rich.diagram_a11y_media", { above: spec.media[0], below: spec.media[1] }));
  if (spec.object) sentences.push(t("rich.diagram_a11y_object"));
  if (spec.image) {
    sentences.push(t(spec.image.virtual ? "rich.diagram_a11y_image_virtual" : "rich.diagram_a11y_image_real"));
  }
  if (spec.rays.length > 0) sentences.push(t("rich.diagram_a11y_ray_count", { count: spec.rays.length }));
  const labels = angles.flatMap((angle) => (angle.label ? [angle.label] : []));
  if (labels.length > 0) sentences.push(labels.join(", "));
  return sentences.map((sentence) => sentence.replace(/[.\s]+$/, "")).join(". ") + ".";
}
