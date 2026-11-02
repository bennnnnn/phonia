/**
 * The ray diagram's reading and geometry, and the world frame it shares with
 * the wave diagram: equal-aspect mapping, label placement, measure lines.
 */
import {
  angleArc,
  angleLabel,
  clipSegment,
  describeOptics,
  DIAGRAM_MAX_HEIGHT,
  DIAGRAM_MIN_HEIGHT,
  elementExtent,
  firstClearLabel,
  focalPoints,
  hatchSegments,
  labelBox,
  labelHits,
  layoutMeasure,
  mediumLabelSide,
  mirrorCurve,
  parseDiagramAngles,
  parseMeasureVectors,
  parseOpticsSpec,
  parseWorldBounds,
  placeLabel,
  rayMarks,
  toScreen,
  worldTransform,
  worldViewportHeight,
  type OpticsSpec,
} from "@/lib/physics/optics";

/** The server's lens example: an object 30 cm from a 10 cm converging lens. */
const LENS = {
  element: "converging_lens",
  focal: 10,
  object: { x: -30, height: 4, label: "object", virtual: false },
  image: { x: 15, height: -2, label: "image", virtual: false },
  rays: [
    { points: [[-30, 4], [0, 4], [15, -2]], virtual: false },
    { points: [[-30, 4], [0, 0], [15, -2]], virtual: false },
    { points: [[-30, 4], [0, -2], [15, -2]], virtual: false },
  ],
  media: null,
};

/** The server's refraction example: air over glass. */
const REFRACTION = {
  element: "interface",
  focal: null,
  object: null,
  image: null,
  rays: [{ points: [[-1, 1.7320508075688774], [0, 0], [0.6666666666666666, -1.8856180831641267]], virtual: false }],
  media: ["air", "glass n = 1.5"],
};

function parse(raw: unknown): OpticsSpec {
  const spec = parseOpticsSpec(raw);
  if (!spec) throw new Error("expected the optics to parse");
  return spec;
}

describe("parseOpticsSpec", () => {
  it("reads the server's lens and refraction examples", () => {
    const lens = parse(LENS);
    expect(lens.element).toBe("converging_lens");
    expect(lens.focal).toBe(10);
    expect(lens.image).toEqual({ x: 15, height: -2, label: "image", virtual: false });
    expect(lens.rays[0].points[1]).toEqual({ x: 0, y: 4 });
    const refraction = parse(REFRACTION);
    expect(refraction.media).toEqual(["air", "glass n = 1.5"]);
    expect(refraction.object).toBeUndefined();
    expect(refraction.focal).toBeUndefined();
  });

  it("needs no focal length for a plane mirror or an interface", () => {
    expect(parseOpticsSpec({ element: "plane_mirror", object: { x: -2, height: 1 } })).not.toBeNull();
    expect(parseOpticsSpec({ element: "interface", rays: [{ points: [[0, 1], [0, 0]] }] })).not.toBeNull();
  });

  it.each([
    ["an unknown element", { ...LENS, element: "prism" }],
    ["a lens without its focal length", { ...LENS, focal: null }],
    ["a curved mirror without its focal length", { ...LENS, element: "concave_mirror", focal: undefined }],
    ["a zero focal length", { ...LENS, focal: 0 }],
    ["a negative focal length", { ...LENS, focal: -10 }],
    ["a focal length given as text", { ...LENS, focal: "10" }],
    ["an object of zero height", { ...LENS, object: { x: -30, height: 0 } }],
    ["an object with no place", { ...LENS, object: { height: 4 } }],
    ["a ray of one point", { ...LENS, rays: [{ points: [[0, 0]] }] }],
    ["a ray of nine points", { ...LENS, rays: [{ points: Array.from({ length: 9 }, (_, i) => [i, 0]) }] }],
    ["a ray point that is null", { ...LENS, rays: [{ points: [[0, 0], [1, null]] }] }],
    ["a ray point of three numbers", { ...LENS, rays: [{ points: [[0, 0], [1, 2, 3]] }] }],
    ["nine rays", { ...LENS, rays: Array.from({ length: 9 }, () => LENS.rays[0]) }],
    ["a virtual flag that is not a boolean", { ...LENS, rays: [{ points: [[0, 0], [1, 1]], virtual: "yes" }] }],
    ["neither an object nor a ray", { ...LENS, object: null, rays: [] }],
    ["one medium", { ...REFRACTION, media: ["air"] }],
    ["a medium name over 16 characters", { ...REFRACTION, media: ["air", "crown glass n = 1.52"] }],
    ["a label over 24 characters", { ...LENS, object: { x: -30, height: 4, label: "o".repeat(25) } }],
  ])("refuses %s", (_name, raw) => {
    expect(parseOpticsSpec(raw)).toBeNull();
  });
});

describe("parseDiagramAngles and parseMeasureVectors", () => {
  it("reads the refraction example's angles", () => {
    const angles = parseDiagramAngles([
      { vertex: [0, 0], start_deg: 90, end_deg: 120, label: "30°", arrow: false, role: "given" },
      { vertex: [0, 0], start_deg: -90, end_deg: -70.53, label: "19.5°", role: "result" },
    ]);
    expect(angles).toHaveLength(2);
    expect(angles![1]).toMatchObject({ startDeg: -90, endDeg: -70.53, role: "result", arrow: false });
  });

  it.each([
    ["no sweep", [{ vertex: [0, 0], start_deg: 10, end_deg: 10 }]],
    ["an unknown role", [{ vertex: [0, 0], start_deg: 0, end_deg: 10, role: "answer" }]],
    ["a vertex that is not a pair", [{ vertex: [0], start_deg: 0, end_deg: 10 }]],
    ["five angles", Array.from({ length: 5 }, () => ({ vertex: [0, 0], start_deg: 0, end_deg: 10 }))],
  ])("refuses angles with %s", (_name, raw) => {
    expect(parseDiagramAngles(raw)).toBeNull();
  });

  it("keeps the measures and validates every vector", () => {
    const measures = parseMeasureVectors([
      { anchor: [0, -0.09], dx: 0.8, dy: 0, label: "λ = 0.8 m", role: "measure" },
      { anchor: [0, 0], dx: 1, dy: 0, role: "force" },
    ]);
    expect(measures).toEqual([{ anchor: { x: 0, y: -0.09 }, dx: 0.8, dy: 0, label: "λ = 0.8 m" }]);
    expect(parseMeasureVectors(undefined)).toEqual([]);
  });

  it.each([
    ["no direction", [{ anchor: [0, 0], dx: 0, dy: 0, role: "measure" }]],
    ["an unknown role", [{ anchor: [0, 0], dx: 1, dy: 0, role: "length" }]],
    ["a body to ride on", [{ anchor: [0, 0], dx: 1, dy: 0, role: "measure", body: 0 }]],
    ["seven vectors", Array.from({ length: 7 }, () => ({ anchor: [0, 0], dx: 1, dy: 0 }))],
  ])("refuses vectors with %s", (_name, raw) => {
    expect(parseMeasureVectors(raw)).toBeNull();
  });

  it("reads the scene box with the server's defaults", () => {
    expect(parseWorldBounds({})).toEqual({ xMin: 0, xMax: 10, yMin: 0, yMax: 10 });
    expect(parseWorldBounds({ x_min: -2, x_max: 2, y_min: -1, y_max: 1 })).toEqual({ xMin: -2, xMax: 2, yMin: -1, yMax: 1 });
    expect(parseWorldBounds({ x_min: 3, x_max: 2 })).toBeNull();
    expect(parseWorldBounds({ y_min: null })).toBeNull();
    expect(parseWorldBounds({ x_max: "10" })).toBeNull();
  });
});

describe("the world frame", () => {
  const square = { xMin: -2.2, xMax: 2.2, yMin: -2.2, yMax: 2.2 };
  const wide = { xMin: -34, xMax: 24, yMin: -6, yMax: 6 };

  it("sizes the canvas to the scene within its limits", () => {
    expect(worldViewportHeight(square, 312)).toBe(DIAGRAM_MAX_HEIGHT);
    expect(worldViewportHeight(wide, 312)).toBe(DIAGRAM_MIN_HEIGHT);
  });

  it("keeps one scale for both axes, so a 30° ray stays at 30°", () => {
    const height = worldViewportHeight(wide, 312);
    const t = worldTransform(wide, 312, height);
    const from = toScreen(0, 0, t);
    const to = toScreen(Math.cos(Math.PI / 6), Math.sin(Math.PI / 6), t);
    const angle = (Math.atan2(from.py - to.py, to.px - from.px) * 180) / Math.PI;
    expect(angle).toBeCloseTo(30, 6);
  });

  it("letterboxes and centres the scene box", () => {
    const t = worldTransform(wide, 312, 200);
    const topLeft = toScreen(wide.xMin, wide.yMax, t);
    const bottomRight = toScreen(wide.xMax, wide.yMin, t);
    expect(topLeft.px).toBeCloseTo(312 - bottomRight.px, 6);
    expect(topLeft.py).toBeCloseTo(200 - bottomRight.py, 6);
  });

  it("clips a segment to a rectangle", () => {
    const rect = { x: 0, y: 0, width: 10, height: 10 };
    expect(clipSegment({ x1: -5, y1: 5, x2: 15, y2: 5 }, rect)).toEqual({ x1: 0, y1: 5, x2: 10, y2: 5 });
    expect(clipSegment({ x1: -5, y1: -5, x2: -1, y2: -1 }, rect)).toBeNull();
  });

  it("keeps a label inside the canvas", () => {
    const label = placeLabel("λ = 0.8 m", 60, { px: 2, py: 2 }, "above", 5, { width: 100, height: 50 });
    const box = labelBox(label);
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(100);
  });

  it("picks the first label candidate clear of every obstacle", () => {
    const canvas = { width: 200, height: 200 };
    const below = placeLabel("F", 7, { px: 100, py: 100 }, "below", 3, canvas);
    const above = placeLabel("F", 7, { px: 100, py: 100 }, "above", 3, canvas);
    const ray = { x1: 80, y1: 108, x2: 120, y2: 108 };
    expect(labelHits(below, [ray])).toBe(true);
    expect(firstClearLabel([below, above], [ray])).toBe(above);
    // When nothing is clear the first choice stands.
    expect(firstClearLabel([below], [ray])).toBe(below);
  });

  it("draws a measure at its world length, its label away from the axis", () => {
    const bounds = { xMin: -0.05, xMax: 1.25, yMin: -0.12, yMax: 0.12 };
    const height = worldViewportHeight(bounds, 312);
    const t = worldTransform(bounds, 312, height);
    const measure = layoutMeasure(
      { anchor: { x: 0, y: -0.09 }, dx: 0.8, dy: 0, label: "λ = 0.8 m" },
      t,
      { width: 312, height },
      (text) => text.length * 6,
    );
    expect(measure.to.px - measure.from.px).toBeCloseTo(0.8 * t.scale, 6);
    // Below the axis, so the label goes under the line.
    expect(measure.label!.y).toBeGreaterThan(measure.from.py);
    const upright = layoutMeasure(
      { anchor: { x: 0.2, y: 0 }, dx: 0, dy: 0.1, label: "A" },
      t,
      { width: 312, height },
      () => 8,
    );
    expect(upright.label!.x).toBeGreaterThan(upright.from.px);
  });
});

describe("ray diagram geometry", () => {
  it("puts one direction mark on each visible segment, pointing along it", () => {
    const rect = { x: 0, y: 0, width: 300, height: 100 };
    const marks = rayMarks(
      [
        { px: 10, py: 20 },
        { px: 150, py: 20 },
        { px: 290, py: 80 },
      ],
      rect,
    );
    expect(marks).toHaveLength(2);
    expect(marks[0].ux).toBeCloseTo(1);
    expect(marks[0].uy).toBeCloseTo(0);
    expect(marks[1].uy).toBeGreaterThan(0);
    // A segment wholly off the canvas gets no mark.
    expect(rayMarks([{ px: -50, py: -50 }, { px: -10, py: -10 }], rect)).toEqual([]);
  });

  it("places the focal points: both sides of a lens, one for a mirror", () => {
    const lens = parse(LENS);
    expect(focalPoints(lens)).toEqual([-10, 10]);
    expect(focalPoints({ ...lens, element: "diverging_lens" })).toEqual([-10, 10]);
    // In front of a concave mirror; behind a convex one, where light only seems to meet.
    expect(focalPoints({ ...lens, element: "concave_mirror" })).toEqual([-10]);
    expect(focalPoints({ ...lens, element: "convex_mirror" })).toEqual([10]);
    expect(focalPoints({ ...lens, element: "plane_mirror", focal: undefined })).toEqual([]);
  });

  it("bows a concave mirror toward the light and a convex one away", () => {
    const concave = mirrorCurve("concave_mirror", 100, 50, 10, 90);
    const convex = mirrorCurve("convex_mirror", 100, 50, 10, 90);
    const plane = mirrorCurve("plane_mirror", 100, 50, 10, 90);
    const middle = Math.floor(concave.length / 2);
    expect(concave[0].px).toBeLessThan(concave[middle].px);
    expect(convex[0].px).toBeGreaterThan(convex[middle].px);
    expect(plane.every((p) => p.px === 100)).toBe(true);
    // Hatching sits behind the mirror, on the right.
    for (const tick of hatchSegments(concave)) expect(tick.x2).toBeGreaterThan(tick.x1);
  });

  it("makes the element tall enough for every ray that meets it", () => {
    const lens = parse(LENS);
    const bounds = { xMin: -34, xMax: 24, yMin: -6, yMax: 6 };
    const height = worldViewportHeight(bounds, 312);
    const t = worldTransform(bounds, 312, height);
    const extent = elementExtent(lens, bounds, t, height);
    const hit = toScreen(0, 4, t).py;
    expect(extent.top).toBeLessThan(hit);
    expect(extent.top).toBeGreaterThanOrEqual(0);
    expect(extent.bottom).toBeLessThanOrEqual(height);
  });

  it("sweeps an angle's arc counter-clockwise from its start", () => {
    const t = { scale: 10, offsetX: 100, offsetY: 100 };
    const arc = angleArc({ vertex: { x: 0, y: 0 }, startDeg: 90, endDeg: 120, arrow: false, role: "given" }, t);
    const first = arc.points[0];
    const last = arc.points[arc.points.length - 1];
    expect(first.px).toBeCloseTo(100);
    expect(first.py).toBeLessThan(100);
    expect(last.px).toBeLessThan(100);
  });

  it("finds an angle's label a place off the rays", () => {
    const t = { scale: 45, offsetX: 156, offsetY: 120 };
    const angle = { vertex: { x: 0, y: 0 }, startDeg: -90, endDeg: -70.53, label: "19.5°", arrow: false, role: "result" as const };
    const ray = { x1: 156, y1: 120, x2: 156 + 0.667 * 45, y2: 120 + 1.886 * 45 };
    const normal = { x1: 156, y1: 0, x2: 156, y2: 240 };
    const label = angleLabel(angle, "19.5°", 26, t, [ray, normal], { width: 312, height: 240 });
    expect(labelHits(label, [ray, normal])).toBe(false);
  });

  it("names each medium on the side its half's rays leave free", () => {
    const rays = [[{ px: 40, py: 20 }, { px: 156, py: 120 }, { px: 190, py: 230 }]];
    expect(mediumLabelSide(rays, true, 120, 312)).toBe("right");
    expect(mediumLabelSide(rays, false, 120, 312)).toBe("left");
  });
});

describe("describeOptics", () => {
  const t = (key: string, options?: Record<string, unknown>) =>
    options ? `${key}(${Object.values(options).join(",")})` : key;

  it("says what the element is, what is drawn and the angles", () => {
    const text = describeOptics(parse(REFRACTION), parseDiagramAngles([{ vertex: [0, 0], start_deg: 90, end_deg: 120, label: "30°" }])!, t);
    expect(text).toBe(
      "rich.diagram_a11y_rays(rich.diagram_element_interface). rich.diagram_a11y_media(air,glass n = 1.5). rich.diagram_a11y_ray_count(1). 30°.",
    );
    expect(describeOptics({ ...parse(LENS), image: { x: 5, height: 1, virtual: true } }, [], t)).toContain(
      "rich.diagram_a11y_image_virtual",
    );
  });
});
