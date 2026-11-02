/**
 * The v2 scene fields: strings and pulleys, planets, angles, solids, arrow
 * labels, strobes, a screen-reader sentence and a translatable title.
 *
 * Each new field is optional and as strict as the server's model: a stored
 * reply without them reads exactly as before, and a malformed one refuses the
 * whole scene rather than drawing half of it. The geometry is asserted as
 * plain functions; `components/__tests__/SimulationBlock.test.tsx` covers what
 * only a render can.
 */
import { derivedArrowGeometry, derivedLabelOrigin, inclineSurface, inclineWedge, layoutSimulationScene, parseSimulationSpec, placeNudgedLabel, riddenVectorGeometry, sceneTitle, simulationAccessibilityLabel, simulationTransform, simulationViewportHeight, tangentAt, tetherEnd, worldToScreen, type ScreenPoint, type SimulationSpec } from "@/lib/physics/simulation";
import { angleArcPoints, angleArrowHead, angleLabelBox, angleRadius, ANGLE_MAX_RADIUS, ANGLE_RADIUS, onPulleyRim, pulleyRope, supportGeometry } from "@/lib/physics/simulation/parts";
import { ARROW_MAX_LENGTH, bodyBoxAngle, bodyEdgeDistance, bodyExtent, clipArrowAtCircle, clipArrowLength, MIN_CLIPPED_ARROW } from "@/lib/physics/simulation/arrows";
import { clearanceAlong, tipLabelOrigin, type LabelBox } from "@/lib/physics/simulation/labels";
import { describeSimulation } from "@/lib/physics/simulation/describe";
import { SCENE_TITLE_KEYS } from "@/lib/physics/simulation/spec";
import { strobeIndices } from "@/lib/physics/simulation/paths";

const WIDTH = 312;
const FONT = 11;
const measure = (text: string) => text.length * 6.6;

function parse(spec: object) {
  return parseSimulationSpec(JSON.stringify(spec));
}

function mustParse(spec: object): SimulationSpec {
  const parsed = parse(spec);
  if (!parsed) throw new Error("fixture did not parse");
  return parsed;
}

function layout(spec: SimulationSpec) {
  const height = simulationViewportHeight(spec, WIDTH, 24, 136, 240);
  const t = simulationTransform(spec, WIDTH, height, 24);
  return { height, t, scene: layoutSimulationScene(spec, t, WIDTH, height, measure, FONT) };
}

function overlaps(a: LabelBox, b: LabelBox): boolean {
  return a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
}

/** One full swing of a 1 m pendulum, 15° either side, as the server samples it. */
const SWING = Array.from({ length: 61 }, (_, i) => {
  const theta = ((15 * Math.PI) / 180) * Math.cos((2 * Math.PI * i) / 60);
  return [Math.sin(theta), -Math.cos(theta)];
});

const PENDULUM = {
  type: "pendulum",
  title: "Pendulum",
  bodies: [{ label: "0.5 kg", radius: 0.06, path: SWING, role: "primary" }],
  x_min: -0.6,
  x_max: 0.6,
  y_min: -1.2,
  y_max: 0.15,
  arrows: ["velocity", "gravity"],
  centre: null,
  ground: false,
  incline_deg: null,
  vectors: [],
  beam: null,
  pivot: null,
  tethers: [{ anchor: [0, 0], body: 0 }],
  angles: [
    { vertex: [0, 0], start_deg: -90, end_deg: -75, label: "15°", arrow: false, role: "given" },
  ],
  arrow_labels: { velocity: "v", gravity: "mg" },
  alt: "A 1 m pendulum swinging 15° either side; period 2.01 s.",
  title_key: "pendulum",
};

const fall = Array.from({ length: 50 }, (_, i) => Math.min(0.5 * 2.45 * (i * 0.025) ** 2, 1.5));
const ATWOOD = {
  type: "free_body",
  title: "Atwood Machine",
  bodies: [
    { label: "5 kg", radius: 0.25, path: fall.map((s) => [-0.5, 2.2 - s]), role: "primary", shape: "box" },
    { label: "3 kg", radius: 0.21, path: fall.map((s) => [0.5, 0.7 + s]), role: "secondary", shape: "box" },
  ],
  x_min: -1.6,
  x_max: 1.6,
  y_min: 0,
  y_max: 3.9,
  arrows: [],
  vectors: [
    { anchor: [0, 0.25], dx: 0, dy: 36.8, label: "T = 36.8 N", role: "result", body: 0 },
    { anchor: [0, 0.21], dx: 0, dy: 36.8, label: "T = 36.8 N", role: "result", body: 1 },
    { anchor: [0.4, 0], dx: 0, dy: -2.45, label: "a = 2.45 m/s²", role: "motion", body: 0 },
    { anchor: [0.4, 0], dx: 0, dy: 2.45, label: "a", role: "motion", body: 1 },
  ],
  tethers: [
    { anchor: [-0.5, 3.2], body: 0 },
    { anchor: [0.5, 3.2], body: 1 },
  ],
  pulley: { centre: [0, 3.2], radius: 0.5 },
  title_key: "atwood",
};

const TABLE = {
  type: "projectile_motion",
  title: "Projectile",
  bodies: [
    {
      radius: 0.05,
      role: "primary",
      path: Array.from({ length: 41 }, (_, i) => {
        const time = (0.4946 * i) / 40;
        return [3 * time, 1.25 - 4.905 * time * time];
      }),
    },
  ],
  x_min: -0.9,
  x_max: 1.8,
  y_min: -0.25,
  y_max: 1.5,
  arrows: ["velocity", "gravity"],
  ground: true,
  vectors: [{ anchor: [0, -0.12], dx: 1.484, dy: 0, label: "d = 1.48 m", role: "measure" }],
  solids: [{ rect: [-0.6, 0, 0, 1.2], kind: "solid", label: "table" }],
  arrow_labels: { velocity: "v", gravity: "mg" },
  strobe: 6,
};

const LEVER = {
  type: "lever",
  title: "Moments",
  bodies: [],
  x_min: -0.46,
  x_max: 0.46,
  y_min: -0.22,
  y_max: 0.22,
  vectors: [{ anchor: [0.3, 0], dx: 0, dy: -50, label: "50 N at 0.3 m", role: "force" }],
  beam: [-0.4, 0, 0.4, 0],
  pivot: [0, 0],
  angles: [
    { vertex: [0, 0], start_deg: 60, end_deg: -30, label: "τ = 15 N·m", arrow: true, role: "result" },
  ],
};

const ORBIT = {
  type: "orbit",
  bodies: [
    {
      radius: 0.3,
      role: "primary",
      path: Array.from({ length: 73 }, (_, i) => [
        6.771 * Math.cos((2 * Math.PI * i) / 72),
        6.771 * Math.sin((2 * Math.PI * i) / 72),
      ]),
    },
  ],
  x_min: -7.8,
  x_max: 7.8,
  y_min: -7.8,
  y_max: 7.8,
  arrows: ["velocity", "centripetal"],
  centre: [0, 0],
  central_body: { radius: 6.371, label: "Earth" },
  arrow_labels: { velocity: "v = 7.67 km/s", centripetal: "g" },
};

describe("parseSimulationSpec: v2 fields", () => {
  it("reads every new field of a pendulum", () => {
    const spec = mustParse(PENDULUM);

    expect(spec.type).toBe("pendulum");
    expect(spec.tethers).toEqual([{ anchor: { x: 0, y: 0 }, body: 0 }]);
    expect(spec.angles).toEqual([
      { vertex: { x: 0, y: 0 }, startDeg: -90, endDeg: -75, label: "15°", arrow: false, role: "given" },
    ]);
    expect(spec.arrowLabels).toEqual({ velocity: "v", gravity: "mg" });
    expect(spec.alt).toMatch(/^A 1 m pendulum/);
    expect(spec.titleKey).toBe("pendulum");
    expect(spec.bodies[0].shape).toBe("circle");
  });

  it("reads boxes, a pulley and vectors riding on bodies", () => {
    const spec = mustParse(ATWOOD);

    expect(spec.bodies.map((body) => body.shape)).toEqual(["box", "box"]);
    expect(spec.pulley).toEqual({ centre: { x: 0, y: 3.2 }, radius: 0.5 });
    expect(spec.vectors.map((vector) => vector.body)).toEqual([0, 1, 0, 1]);
  });

  it("reads solids, a strobe, a planet and a moment arrow", () => {
    const table = mustParse(TABLE);
    expect(table.solids).toEqual([
      { rect: { xMin: -0.6, yMin: 0, xMax: 0, yMax: 1.2 }, kind: "solid", label: "table" },
    ]);
    expect(table.strobe).toBe(6);

    expect(mustParse(ORBIT).centralBody).toEqual({ radius: 6.371, label: "Earth" });
    expect(mustParse(LEVER).angles[0]).toMatchObject({ arrow: true, role: "result" });
  });

  it("reads an old reply with none of them exactly as before", () => {
    const { solids, arrow_labels, strobe, ...old } = TABLE;
    void [solids, arrow_labels, strobe];
    const spec = mustParse(old);

    expect(spec.tethers).toEqual([]);
    expect(spec.angles).toEqual([]);
    expect(spec.solids).toEqual([]);
    expect(spec.arrowLabels).toEqual({});
    expect(spec.pulley).toBeUndefined();
    expect(spec.centralBody).toBeUndefined();
    expect(spec.strobe).toBeUndefined();
    expect(spec.alt).toBeUndefined();
    expect(spec.titleKey).toBeUndefined();
    expect(spec.vectors[0].body).toBeUndefined();
  });

  it("treats null optional objects as absent, as the server's model does", () => {
    const spec = mustParse({
      ...PENDULUM,
      pulley: null,
      central_body: null,
      strobe: null,
      alt: null,
      title_key: null,
      angles: [{ ...PENDULUM.angles[0], label: null }],
    });
    expect(spec.pulley).toBeUndefined();
    expect(spec.angles[0].label).toBeUndefined();
  });

  it("drops a label for an arrow it cannot draw without refusing the scene", () => {
    // No centre, so no centripetal arrow — and so no label for one.
    const spec = mustParse({ ...ORBIT, centre: undefined, central_body: undefined });
    expect(spec.arrows).toEqual(["velocity"]);
    expect(spec.arrowLabels).toEqual({ velocity: "v = 7.67 km/s" });
  });

  it.each([
    ["a circuit", { type: "circuit" }],
    ["a ray diagram", { type: "rays" }],
    ["a wave", { type: "wave" }],
  ])("leaves %s to the diagram renderer", (_label, kind) => {
    expect(parse({ ...PENDULUM, ...kind })).toBeNull();
  });

  const body = ATWOOD.bodies[0];
  const angle = PENDULUM.angles[0];
  it.each([
    ["an unknown body shape", { ...ATWOOD, bodies: [{ ...body, shape: "triangle" }, ATWOOD.bodies[1]] }],
    ["a null body shape", { ...ATWOOD, bodies: [{ ...body, shape: null }, ATWOOD.bodies[1]] }],
    ["a vector riding a missing body", { ...ATWOOD, vectors: [{ ...ATWOOD.vectors[0], body: 2 }] }],
    ["a fractional body index", { ...ATWOOD, vectors: [{ ...ATWOOD.vectors[0], body: 0.5 }] }],
    ["a negative body index", { ...ATWOOD, vectors: [{ ...ATWOOD.vectors[0], body: -1 }] }],
    ["a string body index", { ...ATWOOD, vectors: [{ ...ATWOOD.vectors[0], body: "0" }] }],
    ["a tether to a missing body", { ...PENDULUM, tethers: [{ anchor: [0, 0], body: 1 }] }],
    ["a tether with no anchor", { ...PENDULUM, tethers: [{ body: 0 }] }],
    ["five tethers", { ...PENDULUM, tethers: Array(5).fill({ anchor: [0, 0], body: 0 }) }],
    ["tethers that are not a list", { ...PENDULUM, tethers: null }],
    ["a pulley of no size", { ...ATWOOD, pulley: { centre: [0, 3.2], radius: 0 } }],
    ["a pulley with no centre", { ...ATWOOD, pulley: { radius: 0.5 } }],
    ["a planet with no centre", { ...ORBIT, centre: undefined, arrows: ["velocity"], arrow_labels: {} }],
    ["a planet of negative size", { ...ORBIT, central_body: { radius: -1 } }],
    ["a planet's name over 24 characters", { ...ORBIT, central_body: { radius: 6, label: "x".repeat(25) } }],
    ["an angle with no sweep", { ...PENDULUM, angles: [{ ...angle, end_deg: -90 }] }],
    ["an angle with a non-finite end", { ...PENDULUM, angles: [{ ...angle, end_deg: "75" }] }],
    ["an angle whose arrow is not a boolean", { ...PENDULUM, angles: [{ ...angle, arrow: 1 }] }],
    ["an angle with an unknown role", { ...PENDULUM, angles: [{ ...angle, role: "answer" }] }],
    ["an angle with a long label", { ...PENDULUM, angles: [{ ...angle, label: "θ".repeat(25) }] }],
    ["five angles", { ...PENDULUM, angles: Array(5).fill(angle) }],
    ["a solid with unordered corners", { ...TABLE, solids: [{ rect: [0, 0, -0.6, 1.2] }] }],
    ["a solid with three corners", { ...TABLE, solids: [{ rect: [0, 0, 1] }] }],
    ["a solid of an unknown kind", { ...TABLE, solids: [{ rect: [-0.6, 0, 0, 1.2], kind: "gas" }] }],
    ["a label for an arrow the scene does not draw", { ...PENDULUM, arrow_labels: { normal: "N" } }],
    ["a label for an unknown arrow", { ...PENDULUM, arrow_labels: { lift: "L" } }],
    ["an arrow label over 24 characters", { ...PENDULUM, arrow_labels: { velocity: "v".repeat(25) } }],
    ["arrow labels as a list", { ...PENDULUM, arrow_labels: ["v"] }],
    ["a strobe of one", { ...TABLE, strobe: 1 }],
    ["a strobe of thirteen", { ...TABLE, strobe: 13 }],
    ["a fractional strobe", { ...TABLE, strobe: 2.5 }],
    ["an alt over 300 characters", { ...PENDULUM, alt: "a".repeat(301) }],
    ["an alt that is not text", { ...PENDULUM, alt: 3 }],
    ["a title key that is not text", { ...PENDULUM, title_key: 3 }],
    ["a pendulum with no string", { ...PENDULUM, tethers: [] }],
    ["a pendulum with two bobs", { ...PENDULUM, bodies: [PENDULUM.bodies[0], PENDULUM.bodies[0]] }],
  ])("refuses %s", (_label, bad) => {
    expect(parse(bad)).toBeNull();
  });

  it("draws a scene whose title key is newer than this build, under its English title", () => {
    const scene = parse({ ...PENDULUM, title_key: "explosion" });
    expect(scene).not.toBeNull();
    expect(scene?.titleKey).toBeUndefined();
  });

  it("knows every title key the server can send", () => {
    expect(SCENE_TITLE_KEYS).toHaveLength(23);
    for (const key of SCENE_TITLE_KEYS) {
      expect(parse({ ...PENDULUM, title_key: key })?.titleKey).toBe(key);
    }
  });
});

describe("the title and what a screen reader hears", () => {
  const words: Record<string, string> = {
    "rich.scene_title_pendulum": "Pendel",
    "rich.simulation_title": "Simulation",
    "rich.simulation_a11y_body": "Object",
    "rich.simulation_a11y_arrows": "Arrows: {{list}}",
    "rich.simulation_arrow_velocity": "velocity",
    "rich.simulation_arrow_gravity": "gravity",
  };
  // i18next hands an unknown key back unchanged.
  const t = (key: string, options?: Record<string, unknown>) =>
    (words[key] ?? key).replace(/\{\{(\w+)\}\}/g, (_, name) => String(options?.[name]));

  it("uses the translated title for a key it knows", () => {
    expect(sceneTitle(mustParse(PENDULUM), t)).toBe("Pendel");
  });

  it("falls back to the server's title when the key is not translated", () => {
    expect(sceneTitle(mustParse(ATWOOD), t)).toBe("Atwood Machine");
    expect(sceneTitle(mustParse({ ...ATWOOD, title: undefined }), t)).toBe("Simulation");
  });

  it("says the server's sentence when it sent one", () => {
    expect(simulationAccessibilityLabel(mustParse(PENDULUM), t)).toBe(PENDULUM.alt);
  });

  it("otherwise describes the scene, with its arrow and angle labels", () => {
    const { alt, ...noAlt } = PENDULUM;
    void alt;
    const description = simulationAccessibilityLabel(mustParse(noAlt), t);
    expect(description).toBe(describeSimulation(mustParse(noAlt), t));
    expect(description).toBe("Pendel. 0.5 kg. Arrows: velocity v, gravity mg. 15°.");
  });
});

describe("strobe", () => {
  it("spaces the copies evenly, first and last sample included", () => {
    expect(strobeIndices(41, 6)).toEqual([0, 8, 16, 24, 32, 40]);
    expect(strobeIndices(50, 4)).toEqual([0, 16, 33, 49]);
  });

  it("draws none without a count, and never the same sample twice", () => {
    expect(strobeIndices(41, undefined)).toEqual([]);
    expect(strobeIndices(3, 12)).toEqual([0, 1, 2]);
  });

  it("puts the copies on the body's path, and none on a body that never moves", () => {
    const { t, scene } = layout(mustParse(TABLE));
    const path = TABLE.bodies[0].path;
    expect(scene.strobes[0]).toEqual(
      [0, 8, 16, 24, 32, 40].map((i) => worldToScreen(path[i][0], path[i][1], t)),
    );

    const still = mustParse({ ...TABLE, bodies: [{ ...TABLE.bodies[0], path: [[0, 1], [0, 1]] }] });
    expect(layout(still).scene.strobes[0]).toEqual([]);
  });
});

describe("box bodies", () => {
  it("lies on the slope in an incline scene and stands upright elsewhere", () => {
    const incline = mustParse({
      type: "incline",
      bodies: [{ radius: 0.2, path: [[1, 1.4], [1, 1.4]], shape: "box" }],
      x_min: -0.2,
      x_max: 3.8,
      y_min: -0.2,
      y_max: 2.4,
      incline_deg: 30,
      arrows: ["gravity"],
    });
    expect(bodyBoxAngle(incline, incline.bodies[0])).toBeCloseTo(Math.PI / 6, 10);
    const atwood = mustParse(ATWOOD);
    expect(bodyBoxAngle(atwood, atwood.bodies[0])).toBe(0);
    const ball = mustParse(PENDULUM);
    expect(bodyBoxAngle(ball, ball.bodies[0])).toBeNull();
  });

  it("starts an arrow at the box's edge, further out toward a corner", () => {
    expect(bodyEdgeDistance(10, 0, 1, null)).toBe(10);
    expect(bodyEdgeDistance(10, 0, 1, 0)).toBeCloseTo(10, 10);
    expect(bodyEdgeDistance(10, Math.SQRT1_2, Math.SQRT1_2, 0)).toBeCloseTo(10 * Math.SQRT2, 10);
    // Straight down from a box turned 30°: past the bottom face's centre.
    expect(bodyEdgeDistance(10, 0, 1, Math.PI / 6)).toBeCloseTo(10 / Math.cos(Math.PI / 6), 10);
    expect(bodyExtent(10, Math.PI / 6)).toBeCloseTo(10 * (Math.cos(Math.PI / 6) + 0.5), 10);
  });

  it("starts a derived arrow on the box", () => {
    const arrow = derivedArrowGeometry("gravity", { px: 100, py: 50 }, 10, {
      tangent: { dx: 0, dy: 0 },
      maxSpeed: 0,
      centre: null,
      slope: null,
      width: 300,
      height: 300,
      boxAngle: Math.PI / 6,
    })!;
    expect(arrow.fromY - 50).toBeCloseTo(10 / Math.cos(Math.PI / 6), 10);
  });
});

describe("vectors riding on a body", () => {
  it("starts from the body's position plus the stated offset", () => {
    const spec = mustParse(ATWOOD);
    const { t, scene } = layout(spec);
    const [tension] = scene.vectors;
    const expected = worldToScreen(-0.5, 2.2 + 0.25, t);

    expect(tension.body).toBe(0);
    expect(tension.from.px).toBeCloseTo(expected.px, 6);
    expect(tension.from.py).toBeCloseTo(expected.py, 6);
    expect(tension.ride).toMatchObject({ ux: 0, uy: -1 });
  });

  it("goes where the body goes, every frame", () => {
    const spec = mustParse(ATWOOD);
    const { t, height, scene } = layout(spec);
    const motion = scene.vectors[2];
    const ride = motion.ride!;
    const track = scene.tracks[0];
    const last = track[track.length - 1];
    const fromX = motion.from.px + last.px - track[0].px;
    const fromY = motion.from.py + last.py - track[0].py;
    const end = riddenVectorGeometry(fromX, fromY, ride.ux, ride.uy, ride.desired, WIDTH, height, null);

    const anchor = worldToScreen(-0.5 + 0.4, 0.7, t);
    expect(fromX).toBeCloseTo(anchor.px, 6);
    expect(fromY).toBeCloseTo(anchor.py, 6);
    expect(end).not.toBeNull();
  });

  it("starts an arrow anchored on the body's centre at its edge", () => {
    const spec = mustParse({
      ...ATWOOD,
      vectors: [{ anchor: [0, 0], dx: 0, dy: 1, label: "T", role: "force", body: 1 }],
    });
    const { scene } = layout(spec);
    const centre = scene.tracks[1][0];
    expect(centre.py - scene.vectors[0].from.py).toBeCloseTo(scene.radii[1], 6);
  });

  it("stops a tension at the pulley's wheel instead of running into it", () => {
    // From 39 px below a wheel of radius 24, straight up its side.
    const along = riddenVectorGeometry(76, 139, 0, -1, 48, 300, 300, { cx: 100, cy: 100, radius: 24 })!;
    expect(along.length).toBeLessThan(39);
    expect(along.length).toBeGreaterThan(30);
    // Clear of the wheel, the arrow keeps its length.
    expect(riddenVectorGeometry(40, 139, 0, -1, 48, 300, 300, { cx: 100, cy: 100, radius: 24 })).toEqual({
      length: 48,
    });
    // Cut to nothing, it is not drawn.
    expect(riddenVectorGeometry(76, 112, 0, -1, 48, 300, 300, { cx: 100, cy: 100, radius: 24 })).toBeNull();
  });

  it("meets a circle where the line enters it", () => {
    expect(clipArrowAtCircle(0, 0, 1, 0, 100, 50, 0, 10)).toBeCloseTo(40, 10);
    expect(clipArrowAtCircle(0, 0, 1, 0, 30, 50, 0, 10)).toBe(30);
    expect(clipArrowAtCircle(0, 0, -1, 0, 100, 50, 0, 10)).toBe(100);
  });

  it("keeps the riding labels of an Atwood machine apart at the start", () => {
    const { scene } = layout(mustParse(ATWOOD));
    const boxes = scene.vectors.flatMap((vector) => (vector.label ? [vector.label.box] : []));
    for (let i = 0; i < boxes.length; i += 1) {
      for (let j = i + 1; j < boxes.length; j += 1) {
        expect(overlaps(boxes[i], boxes[j])).toBe(false);
      }
    }
  });
});

describe("strings, supports and pulleys", () => {
  it("ends a string at a ball's edge, on the line to its centre", () => {
    const end = tetherEnd({ px: 0, py: 0 }, { px: 30, py: 40 }, 5, null)!;
    expect(end.px).toBeCloseTo(27, 10);
    expect(end.py).toBeCloseTo(36, 10);
  });

  it("ends a string at a box's face", () => {
    const end = tetherEnd({ px: 50, py: 0 }, { px: 50, py: 100 }, 10, 0)!;
    expect(end).toEqual({ px: 50, py: 90 });
  });

  it("has no string when the anchor is inside the body", () => {
    expect(tetherEnd({ px: 1, py: 1 }, { px: 0, py: 0 }, 5, null)).toBeNull();
  });

  it("hangs a pendulum from a level ceiling, hatched above it", () => {
    // Even with the bob at full swing, the support stays level.
    const support = supportGeometry({ px: 100, py: 20 }, { px: 130, py: 130 });
    expect(support.bar.y1).toBe(20);
    expect(support.bar.y2).toBe(20);
    for (const hatch of support.hatches) expect(hatch.y2).toBeLessThan(hatch.y1);
  });

  it("draws a wall for a string pulled sideways, hatched away from the body", () => {
    const support = supportGeometry({ px: 100, py: 20 }, { px: 0, py: 25 });
    expect(support.bar.x1).toBe(100);
    expect(support.bar.x2).toBe(100);
    for (const hatch of support.hatches) expect(hatch.x2).toBeGreaterThan(hatch.x1);
  });

  it("gives a string leaving a pulley's rim no support of its own", () => {
    const { scene } = layout(mustParse(ATWOOD));
    expect(scene.tethers.map((tether) => tether.support)).toEqual([null, null]);
    expect(scene.pulley).not.toBeNull();
    expect(onPulleyRim(scene.tethers[0].anchor, scene.pulley!.centre, scene.pulley!.radius)).toBe(true);

    const pendulum = layout(mustParse(PENDULUM)).scene;
    expect(pendulum.tethers[0].support).not.toBeNull();
  });

  it("runs the rope over the top of the wheel", () => {
    const centre = { px: 100, py: 100 };
    const rope = pulleyRope(centre, 20, [
      { px: 80, py: 100 },
      { px: 120, py: 100 },
    ])!;
    expect(rope[0]).toEqual({ px: 80, py: expect.closeTo(100, 6) });
    expect(rope[rope.length - 1].px).toBeCloseTo(120, 6);
    // Every point is on the rim, at or above the centre.
    for (const point of rope) {
      expect(Math.hypot(point.px - centre.px, point.py - centre.py)).toBeCloseTo(20, 6);
      expect(point.py).toBeLessThanOrEqual(100 + 1e-9);
    }
    expect(pulleyRope(centre, 20, [{ px: 80, py: 100 }])).toBeNull();
  });
});

describe("a pendulum", () => {
  it("wraps its clock, so the bob at full swing has no velocity", () => {
    const { scene } = layout(mustParse(PENDULUM));
    expect(scene.closed[0]).toBe(true);
    expect(tangentAt(scene.tracks[0], 0, true)).toEqual({ dx: expect.closeTo(0, 6), dy: expect.closeTo(0, 6) });
  });

  it("draws its rest line straight down from the pivot, as long as the string", () => {
    const { t, scene } = layout(mustParse(PENDULUM));
    const pivot = worldToScreen(0, 0, t);
    const [rest] = scene.restLines;
    expect(rest.x1).toBeCloseTo(pivot.px, 6);
    expect(rest.x2).toBeCloseTo(pivot.px, 6);
    expect(rest.y2 - rest.y1).toBeCloseTo(t.scale, 3);
  });

  it("keeps the bob's label off its string, its weight and its path", () => {
    const { scene } = layout(mustParse(PENDULUM));
    expect(["above", "below", "right", "left"]).not.toContain(scene.bodyLabels[0]!.side);
  });
});

describe("angles", () => {
  const vertex: ScreenPoint = { px: 100, py: 100 };

  it("draws the arc counter-clockwise from +x, with y up", () => {
    const arc = angleArcPoints(vertex, 0, 90, 26);
    expect(arc[0]).toEqual({ px: 126, py: 100 });
    expect(arc[arc.length - 1].px).toBeCloseTo(100, 10);
    expect(arc[arc.length - 1].py).toBeCloseTo(74, 10);
    for (const point of arc) {
      expect(Math.hypot(point.px - 100, point.py - 100)).toBeCloseTo(26, 10);
    }
  });

  it("uses the usual radius, and a longer one for a narrow angle so it is an arc, not a tick", () => {
    expect(angleRadius(150, 180)).toBeCloseTo(26.74, 2);
    expect(angleRadius(0, 90)).toBe(ANGLE_RADIUS);
    expect(angleRadius(-90, -75)).toBeGreaterThan(ANGLE_RADIUS);
    expect(angleRadius(0, 2)).toBe(ANGLE_MAX_RADIUS);
  });

  it("points a moment arrow's head the way it turns", () => {
    // 60° round to −30°: clockwise, ending below and right of the pivot,
    // heading down and to the left.
    const head = angleArrowHead(vertex, 60, -30, 26);
    expect(head.tip.px).toBeGreaterThan(100);
    expect(head.tip.py).toBeGreaterThan(100);
    expect(head.ux).toBeLessThan(0);
    expect(head.uy).toBeGreaterThan(0);
    expect(Math.hypot(head.ux, head.uy)).toBeCloseTo(1, 10);
  });

  it("puts the label outside the arc, centred on its middle angle", () => {
    const box = angleLabelBox(vertex, 0, 90, 26, 20, FONT);
    const centre = { px: box.x + box.width / 2, py: box.y + box.height / 2 };
    // Middle angle 45°: up and to the right on screen.
    expect(Math.atan2(vertex.py - centre.py, centre.px - vertex.px)).toBeCloseTo(Math.PI / 4, 10);
    // No corner of the box is inside the arc.
    for (const [x, y] of [
      [box.x, box.y],
      [box.x + box.width, box.y],
      [box.x, box.y + box.height],
      [box.x + box.width, box.y + box.height],
    ]) {
      expect(Math.hypot(x - vertex.px, y - vertex.py)).toBeGreaterThan(26);
    }
  });

  it("lays out a moment arrow with its head and its label in the answer's place", () => {
    const { scene } = layout(mustParse(LEVER));
    const [moment] = scene.angles;
    expect(moment.head).not.toBeNull();
    expect(moment.label?.text).toBe("τ = 15 N·m");
    // The stroke stops under the head, so its cap never pokes through.
    const lastArc = moment.arc[moment.arc.length - 1];
    expect(Math.hypot(lastArc.px - moment.head!.tip.px, lastArc.py - moment.head!.tip.py)).toBeGreaterThan(2);
  });
});

describe("ground and solids stop derived arrows", () => {
  const context = {
    tangent: { dx: 3, dy: 4 },
    maxSpeed: 5,
    centre: null,
    slope: null,
    width: 300,
    height: 300,
  };

  it("stops the weight at the ground line", () => {
    const arrow = derivedArrowGeometry("gravity", { px: 50, py: 150 }, 5, { ...context, floorY: 180 })!;
    expect(arrow.fromY + arrow.length).toBeCloseTo(180, 10);
    expect(arrow.length).toBeLessThan(ARROW_MAX_LENGTH);
  });

  it("hides an arrow with too little left above the ground", () => {
    // A ball resting on the floor: its weight would point straight into it.
    expect(derivedArrowGeometry("gravity", { px: 50, py: 175 }, 5, { ...context, floorY: 180 })).toBeNull();
    const short = derivedArrowGeometry("gravity", { px: 50, py: 175 - MIN_CLIPPED_ARROW - 1 }, 5, {
      ...context,
      floorY: 180,
    });
    expect(short).not.toBeNull();
  });

  it("stops a velocity heading into the ground too", () => {
    const arrow = derivedArrowGeometry("velocity", { px: 50, py: 140 }, 5, { ...context, floorY: 180 })!;
    expect(arrow.fromY + arrow.uy * arrow.length).toBeCloseTo(180, 10);
  });

  it("leaves an arrow pointing up alone", () => {
    const up = derivedArrowGeometry("velocity", { px: 50, py: 175 }, 5, {
      ...context,
      tangent: { dx: 3, dy: -4 },
      floorY: 180,
    })!;
    expect(up.length).toBe(ARROW_MAX_LENGTH);
  });

  it("stops at a solid, not at a fluid", () => {
    const table = { x: 40, y: 170, width: 40, height: 60 };
    expect(clipArrowLength(60, 150, 0, 1, 48, null, [table])).toBeCloseTo(20, 10);
    expect(clipArrowLength(100, 150, 0, 1, 48, null, [table])).toBe(48);
    const { scene } = layout(mustParse({ ...TABLE, solids: [{ rect: [-0.6, 0, 0, 1.2], kind: "fluid" }] }));
    expect(scene.obstacles).toEqual([]);
    expect(layout(mustParse(TABLE)).scene.obstacles).toHaveLength(1);
  });

  it("puts a clipped arrow's label beside its head, not in the ground", () => {
    const arrow = { fromX: 50, fromY: 150, ux: 0, uy: 1, length: 30 };
    const origin = derivedLabelOrigin(arrow, 14, FONT, 180, []);
    expect(origin.y + FONT).toBeLessThanOrEqual(180);
    expect(origin.x).toBeGreaterThan(50);
    expect(derivedLabelOrigin(arrow, 14, FONT, null, [])).toEqual(tipLabelOrigin(50, 180, 0, 1, 14, FONT));
  });

  it("ends a slope that stands on the ground where it meets it, as a wedge", () => {
    const spec = mustParse({
      type: "incline",
      bodies: [{ radius: 0.2, path: [[1, 1.4], [1, 1.4]], shape: "box" }],
      x_min: -0.2,
      x_max: 3.8,
      y_min: -0.2,
      y_max: 2.4,
      incline_deg: 30,
      ground: true,
      arrows: ["gravity"],
    });
    const t = simulationTransform(spec, WIDTH, 220, 24);
    const surface = inclineSurface(spec, t)!;
    const floor = worldToScreen(0, 0, t).py;
    expect(surface.y2).toBeCloseTo(floor, 6);
    expect(inclineWedge(spec, t)).toHaveLength(3);
    expect(inclineWedge({ ...spec, ground: false }, t)).toBeNull();
  });
});

describe("labels", () => {
  it("sits a wide label just past a slanted arrow's tip, not a label-width away", () => {
    const ux = 0.5;
    const uy = -Math.sqrt(3) / 2;
    const reach = clearanceAlong(ux, uy, 70, FONT, 6);
    expect(reach).toBeLessThan(6 + 35 * ux + 5.5 * -uy);
    // Still clear of the tip by the gap.
    const origin = tipLabelOrigin(100, 100, ux, uy, 70, FONT);
    const dx = Math.max(origin.x - 100, 100 - (origin.x + 70), 0);
    const dy = Math.max(origin.y - 100, 100 - (origin.y + FONT), 0);
    expect(Math.hypot(dx, dy)).toBeCloseTo(6, 3);
  });

  it("places a nudged label the way the layout checked it, on the canvas", () => {
    expect(placeNudgedLabel(-10, 50, 20, FONT, 4, 2, 300, 200)).toEqual({ x: 8, y: 52, baseline: 52 + FONT * 0.8 });
    expect(placeNudgedLabel(290, 195, 20, FONT, 0, 0, 300, 200).x).toBe(276);
  });

  it("labels each derived arrow the scene names", () => {
    const { scene } = layout(mustParse(TABLE));
    expect(scene.arrowLabels.map((label) => [label.kind, label.text])).toEqual([
      ["velocity", "v"],
      ["gravity", "mg"],
    ]);
  });

  it("names a planet in its disc, clear of a labelled centripetal arrow", () => {
    const { t, scene } = layout(mustParse(ORBIT));
    const centre = worldToScreen(0, 0, t);
    const box = scene.planet!.label!.box;
    // Inside the disc, below the middle where the arrow's label turns round.
    expect(box.y).toBeGreaterThan(centre.py);
    expect(box.y + box.height).toBeLessThan(centre.py + scene.planet!.radius);

    const unlabelled = layout(mustParse({ ...ORBIT, arrow_labels: {} })).scene.planet!.label!.box;
    expect(unlabelled.y + unlabelled.height / 2).toBeCloseTo(centre.py, 6);
  });

  it("keeps gravity's arrow and its label off the planet's name all the way round", () => {
    // A satellite 2000 km up: gravity points at the centre, so drawn at full length its
    // arrow struck through "Earth" for a fifth of the orbit.
    const spec = mustParse({
      ...ORBIT,
      bodies: [
        {
          radius: 0.3,
          role: "primary",
          path: Array.from({ length: 73 }, (_, i) => [
            8.371 * Math.cos((2 * Math.PI * i) / 72),
            8.371 * Math.sin((2 * Math.PI * i) / 72),
          ]),
        },
      ],
      x_min: -9.5,
      x_max: 9.5,
      y_min: -9.5,
      y_max: 9.5,
      arrow_labels: { velocity: "v = 6900 m/s", centripetal: "gravity" },
    });
    const { height, scene } = layout(spec);
    const name = scene.planet!.label!.box;
    const gravity = scene.arrowLabels.find((label) => label.kind === "centripetal")!;
    let drawn = 0;
    for (let frame = 0; frame <= 100; frame += 1) {
      const track = scene.tracks[gravity.body];
      const at = track[Math.round((frame / 100) * (track.length - 1))];
      const arrow = derivedArrowGeometry("centripetal", at, scene.radii[0], {
        tangent: { dx: 0, dy: 0 },
        maxSpeed: scene.maxSpeed,
        centre: scene.planet!.centre,
        slope: null,
        width: WIDTH,
        height,
        floorY: scene.floorY,
        solids: scene.obstacles,
      });
      if (!arrow) continue;
      drawn += 1;
      const tip = { x: arrow.fromX + arrow.ux * arrow.length, y: arrow.fromY + arrow.uy * arrow.length };
      expect(overlaps({ x: tip.x - 1, y: tip.y - 1, width: 2, height: 2 }, name)).toBe(false);
      const origin = derivedLabelOrigin(arrow, gravity.width, FONT, scene.floorY, scene.obstacles, gravity.beside);
      const place = placeNudgedLabel(origin.x, origin.y, gravity.width, FONT, gravity.dx, gravity.dy, WIDTH, height);
      expect(overlaps({ x: place.x, y: place.baseline - FONT * 0.8, width: gravity.width, height: FONT }, name)).toBe(false);
    }
    expect(drawn).toBe(101);
  });

  it("labels a solid inside its top-left corner", () => {
    const { scene } = layout(mustParse(TABLE));
    const [solid] = scene.solids;
    expect(solid.label!.box.x).toBeGreaterThan(solid.box.x);
    expect(solid.label!.box.y).toBeGreaterThan(solid.box.y);
  });
});
