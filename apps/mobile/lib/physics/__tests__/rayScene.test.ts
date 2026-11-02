/**
 * The ray diagram's scene as a pure function: where the element, the rays,
 * the focal marks, the object and image and every label land on the canvas.
 */
import { type Box } from "@/lib/physics/boxes";
import {
  elementExtent,
  labelBox,
  labelHits,
  layoutMeasure,
  parseDiagramAngles,
  parseMeasureVectors,
  parseOpticsSpec,
  parseWorldBounds,
  polylineSegments,
  rayMarks,
  toScreen,
  worldTransform,
  worldViewportHeight,
} from "@/lib/physics/optics";
import { layoutRayScene, type RaySceneSpec } from "@/lib/physics/rayScene";

/** Roughly Source Sans at 12 pt; the real table lives with the renderer. */
const measure = (text: string) => [...text].length * 6;
const WIDTH = 360;

function scene(fence: Record<string, unknown>) {
  const optics = parseOpticsSpec(fence.optics);
  const bounds = parseWorldBounds(fence);
  const angles = parseDiagramAngles(fence.angles);
  const measures = parseMeasureVectors(fence.vectors);
  if (!optics || !bounds || !angles || !measures) throw new Error("expected the fence to parse");
  const spec: RaySceneSpec = { optics, bounds, angles, measures };
  const height = worldViewportHeight(bounds, WIDTH);
  const t = worldTransform(bounds, WIDTH, height);
  return { spec, height, t, layout: layoutRayScene(spec, WIDTH, height, measure, "F") };
}

function overlaps(a: Box, b: Box): boolean {
  return a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
}

/** The server's lens example: an object 30 cm from a 10 cm converging lens. */
const LENS = {
  x_min: -34,
  x_max: 24,
  y_min: -6,
  y_max: 6,
  optics: {
    element: "converging_lens",
    focal: 10,
    object: { x: -30, height: 4, label: "object" },
    image: { x: 15, height: -2, label: "image" },
    rays: [
      { points: [[-30, 4], [0, 4], [15, -2]] },
      { points: [[-30, 4], [0, 0], [15, -2]] },
      { points: [[-30, 4], [0, -2], [15, -2]] },
    ],
  },
};

/** The server's refraction example: air over glass. */
const REFRACTION = {
  x_min: -2.2,
  x_max: 2.2,
  y_min: -2.2,
  y_max: 2.2,
  angles: [
    { vertex: [0, 0], start_deg: 90, end_deg: 120, label: "30°" },
    { vertex: [0, 0], start_deg: -90, end_deg: -70.53, label: "19.5°", role: "result", arrow: true },
  ],
  optics: {
    element: "interface",
    rays: [{ points: [[-1, 1.732], [0, 0], [0.667, -1.886]] }],
    media: ["air", "glass"],
  },
};

describe("layoutRayScene", () => {
  it("maps every ray onto the canvas with a mark on each long visible segment", () => {
    const { spec, height, t, layout } = scene(LENS);
    expect(layout.rays).toHaveLength(3);
    layout.rays.forEach((ray, index) => {
      const points = spec.optics.rays[index].points.map((p) => toScreen(p.x, p.y, t));
      expect(ray.points).toEqual(points);
      expect(ray.marks).toEqual(rayMarks(points, { x: 0, y: 0, width: WIDTH, height }));
    });
  });

  it("gives a virtual ray no direction marks", () => {
    const { layout } = scene({
      ...LENS,
      optics: { ...LENS.optics, rays: [{ points: [[0, 4], [-10, 0]], virtual: true }] },
    });
    expect(layout.rays[0]).toMatchObject({ virtual: true, marks: [] });
  });

  it("stands the element at x = 0 across every ray it meets", () => {
    const { spec, height, t, layout } = scene(LENS);
    expect(layout.axis).toBe(t.offsetY);
    expect(layout.elementX).toBe(toScreen(0, 0, t).px);
    expect(layout.extent).toEqual(elementExtent(spec.optics, spec.bounds, t, height));
    expect(layout.element).toEqual({ kind: "lens", outward: true });
    const diverging = scene({ ...LENS, optics: { ...LENS.optics, element: "diverging_lens" } });
    expect(diverging.layout.element).toEqual({ kind: "lens", outward: false });
  });

  it("curves a concave mirror toward the light and hatches it behind", () => {
    const { layout } = scene({ ...LENS, optics: { ...LENS.optics, element: "concave_mirror" } });
    if (layout.element.kind !== "mirror") throw new Error("expected a mirror");
    const { curve, hatches } = layout.element;
    expect(curve).toHaveLength(25);
    expect(curve[0].px).toBeLessThan(layout.elementX);
    expect(curve[24].px).toBeLessThan(layout.elementX);
    expect(curve[12].px).toBeCloseTo(layout.elementX, 6);
    expect(hatches.length).toBeGreaterThan(5);
    for (const hatch of hatches) expect(hatch.x2).toBeGreaterThan(hatch.x1);
  });

  it("stands the object and an inverted image on the axis at their world size", () => {
    const { t, layout } = scene(LENS);
    expect(layout.object).toEqual({
      x: toScreen(-30, 0, t).px,
      length: 4 * t.scale,
      uy: -1,
      head: 8,
      virtual: false,
    });
    expect(layout.image).toMatchObject({ x: toScreen(15, 0, t).px, length: 2 * t.scale, uy: 1, virtual: false });
    const short = scene({ ...LENS, optics: { ...LENS.optics, object: { x: -30, height: 0.1, virtual: true } } });
    expect(short.layout.object?.head).toBeCloseTo(0.1 * short.t.scale * 0.45, 9);
    expect(short.layout.object?.virtual).toBe(true);
    expect(short.layout.objectLabel).toBeNull();
  });

  it("labels the object past its tip and the inverted image below its tip", () => {
    const { t, layout } = scene(LENS);
    const objectTip = toScreen(-30, 4, t);
    expect(layout.objectLabel!.y).toBeLessThan(objectTip.py);
    expect(layout.objectLabel!.x + layout.objectLabel!.width / 2).toBeCloseTo(objectTip.px, 6);
    const imageTip = toScreen(15, -2, t);
    expect(labelBox(layout.imageLabel!).y).toBeGreaterThan(imageTip.py);
  });

  it("ticks each focal point and labels it under the axis, over it where a ray crosses", () => {
    const { t, layout } = scene(LENS);
    const focus = [-10, 10].map((x) => toScreen(x, 0, t).px);
    expect(layout.focusTicks).toEqual(
      focus.map((px) => ({ x1: px, y1: layout.axis - 4, x2: px, y2: layout.axis + 4 })),
    );
    expect(layout.focusLabels.map((label) => label.text)).toEqual(["F", "F"]);
    expect(labelBox(layout.focusLabels[0]).y).toBeGreaterThan(layout.axis);
    const far = labelBox(layout.focusLabels[1]);
    expect(far.y + far.height).toBeLessThan(layout.axis);
  });

  it("moves a label to its next spot when a ray crosses the first", () => {
    const below = { points: [[-34, -3], [0, -3]] };
    const plain = scene({ ...LENS, optics: { ...LENS.optics, object: { x: -20, height: 2, label: "A" }, image: null, rays: [below] } });
    const tip = toScreen(-20, 2, plain.t);
    expect(plain.layout.objectLabel!.y).toBeLessThan(tip.py);
    const over = 2 + 10 / plain.t.scale;
    const blocked = scene({
      ...LENS,
      optics: { ...LENS.optics, object: { x: -20, height: 2, label: "A" }, image: null, rays: [below, { points: [[-34, over], [0, over]] }] },
    });
    expect(blocked.layout.objectLabel!.x).toBeCloseTo(tip.px + 5, 6);
  });

  it("keeps the refraction's labels off its ray and off each other", () => {
    const { layout } = scene(REFRACTION);
    const ray = polylineSegments(layout.rays[0].points);
    const labels = [...layout.media, ...layout.angleLabels.flatMap((label) => (label ? [label] : []))];
    expect(labels.map((label) => label.text)).toEqual(["air", "glass", "30°", "19.5°"]);
    for (const label of labels) expect(labelHits(label, ray, 0)).toBe(false);
    labels.forEach((a, i) =>
      labels.slice(i + 1).forEach((b) => expect(overlaps(labelBox(a), labelBox(b))).toBe(false)),
    );
  });

  it("names each medium in its half, away from the ray there", () => {
    const { layout } = scene(REFRACTION);
    const [air, glass] = layout.media;
    expect(air.x + air.width).toBeCloseTo(WIDTH - 8, 6);
    expect(labelBox(air).y + labelBox(air).height).toBeLessThan(layout.axis);
    expect(glass.x).toBeCloseTo(8, 6);
    expect(labelBox(glass).y).toBeGreaterThan(layout.axis);
    expect(scene({ ...REFRACTION, optics: { ...REFRACTION.optics, media: null } }).layout.media).toEqual([]);
  });

  it("arcs each angle at its vertex and keeps whether it ends in an arrow", () => {
    const { t, layout } = scene(REFRACTION);
    const centre = toScreen(0, 0, t);
    expect(layout.angles.map((angle) => [angle.role, angle.arrow, angle.label])).toEqual([
      ["given", false, "30°"],
      ["result", true, "19.5°"],
    ]);
    for (const point of layout.angles[0].points) {
      expect(Math.hypot(point.px - centre.px, point.py - centre.py)).toBeCloseTo(26, 6);
    }
  });

  it("lays out each measure at its world length", () => {
    const fence = { ...LENS, vectors: [{ anchor: [-30, -3], dx: 30, dy: 0, label: "u = 30 cm", role: "measure" }] };
    const { t, height, layout } = scene(fence);
    expect(layout.measures).toEqual([
      layoutMeasure({ anchor: { x: -30, y: -3 }, dx: 30, dy: 0, label: "u = 30 cm" }, t, { width: WIDTH, height }, measure),
    ]);
  });
});
