/**
 * How a simulation scene is laid out on the canvas: how long each arrow is,
 * that every arrow stays on the canvas, where the labels go, and what a
 * screen reader hears.
 *
 * The rule throughout is that the phone re-derives no physics. A length is
 * either the world length the server stated (a vector-sum part, a dimension
 * line) or a ratio between magnitudes the server stated; a speed is read off
 * how far the body moves between samples taken at uniform time.
 */
import { derivedArrowGeometry, layoutSimulationScene, parseSimulationSpec, PIVOT_SIZE, simulationTransform, simulationViewportHeight, tangentAt, worldToScreen, type ScreenPoint, type SimulationSpec } from "@/lib/physics/simulation";
import { ARROW_EDGE_INSET, ARROW_MAX_LENGTH, ARROW_MIN_LENGTH, fitArrowLength, leverLoadAnchor, vectorScreenLengths, velocityArrowLength, VELOCITY_MIN_LENGTH } from "@/lib/physics/simulation/arrows";
import { bodyLabelOffset, segmentHitsBox, type LabelBox } from "@/lib/physics/simulation/labels";
import { describeSimulation } from "@/lib/physics/simulation/describe";
import { isClosedPath, maxTrackSpeed } from "@/lib/physics/simulation/paths";
import { projectPath } from "@/lib/physics/simulation/viewport";

const WIDTH = 312;
const FONT = 11;
/** A monospace stand-in for the font: 6.6 px a character. */
const measure = (text: string) => text.length * 6.6;

function parse(spec: object): SimulationSpec {
  const parsed = parseSimulationSpec(JSON.stringify(spec));
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

const VECTOR_SUM = {
  type: "vector_sum",
  bodies: [],
  vectors: [
    { anchor: [0, 0], dx: 100, dy: 0, label: "100 N", role: "force" },
    { anchor: [0, 0], dx: 0, dy: 2, label: "2 N", role: "force" },
    { anchor: [0, 0], dx: 100, dy: 2, label: "100 N", role: "result" },
  ],
  x_min: -26,
  x_max: 126,
  y_min: -26,
  y_max: 28,
  arrows: [],
};

const RESOLVE = {
  type: "vector_sum",
  title: "Forces",
  bodies: [],
  vectors: [
    { anchor: [0, 0], dx: 43.3, dy: 0, label: "43.3 N", role: "force" },
    { anchor: [43.3, 0], dx: 0, dy: 25, label: "25 N", role: "force" },
    { anchor: [0, 0], dx: 43.3, dy: 25, label: "50 N", role: "result" },
  ],
  x_min: -13,
  x_max: 56.3,
  y_min: -13,
  y_max: 38,
  arrows: [],
};

const LEVER = {
  type: "lever",
  title: "Moments",
  bodies: [],
  beam: [-12.5, 0, 12.5, 0],
  pivot: [0, 0],
  vectors: [
    { anchor: [-10, 0], dx: 0, dy: -2, label: "2 N at 10 m", role: "force" },
    { anchor: [0.1, 0], dx: 0, dy: -200, label: "200 N at 0.1 m", role: "result" },
  ],
  x_min: -14.4,
  x_max: 14.4,
  y_min: -6.9,
  y_max: 6.9,
  arrows: [],
};

const FREE_BODY = {
  type: "free_body",
  title: "Free-Body Diagram",
  bodies: [{ radius: 0.32, role: "primary", label: "5 kg", path: [[0, 0], [0, 0]] }],
  vectors: [
    { anchor: [0, 0], dx: 0, dy: 59.05, label: "T = 59.1 N", role: "result" },
    { anchor: [0, 0], dx: 0, dy: -49.05, label: "W = 49.1 N", role: "force" },
  ],
  x_min: -2,
  x_max: 2,
  y_min: -2,
  y_max: 2,
  arrows: [],
};

describe("the motion role", () => {
  it("is read as its own role", () => {
    const spec = parse({
      ...FREE_BODY,
      vectors: [{ anchor: [0, -0.9], dx: 1, dy: 0, label: "a = 4 m/s²", role: "motion" }],
    });
    expect(spec.vectors[0].role).toBe("motion");
  });

  it("falls back to a force for a role this build does not know", () => {
    const spec = parse({
      ...FREE_BODY,
      vectors: [{ anchor: [0, 0], dx: 1, dy: 0, role: "torque" }],
    });
    expect(spec.vectors[0].role).toBe("force");
  });
});

describe("vectorScreenLengths", () => {
  it("draws vector-sum parts at their true length, however small", () => {
    // The 38 px floor used to inflate a 2 N component nine times over.
    const spec = parse(VECTOR_SUM);
    const [big, small, result] = vectorScreenLengths(spec, 2);

    expect(big).toBeCloseTo(200, 6);
    expect(small).toBeCloseTo(4, 6);
    expect(result).toBeCloseTo(2 * Math.hypot(100, 2), 6);
  });

  it("draws a measure line at its world length in any scene", () => {
    const spec = parse({
      ...FREE_BODY,
      vectors: [
        { anchor: [0, 0], dx: 0, dy: -1, label: "W = 19.6 N", role: "force" },
        { anchor: [-0.9, 0], dx: 0, dy: 1.5, label: "h = 1.5 m", role: "measure" },
      ],
    });
    expect(vectorScreenLengths(spec, 30)[1]).toBeCloseTo(45, 6);
  });

  it("scales other vectors relative to the largest, with a floor", () => {
    const spec = parse(LEVER);
    const [small, large] = vectorScreenLengths(spec, 10);

    expect(large).toBe(ARROW_MAX_LENGTH);
    // 2 N against 200 N would be half a pixel; it stays a visible arrow.
    expect(small).toBe(ARROW_MIN_LENGTH);

    const tension = vectorScreenLengths(parse(FREE_BODY), 10);
    expect(tension[0]).toBe(ARROW_MAX_LENGTH);
    expect(tension[1]).toBeCloseTo((ARROW_MAX_LENGTH * 49.05) / 59.05, 6);
  });

  it("normalises motion arrows apart from forces", () => {
    // Newtons and m/s² share no scale, so each family has its own longest.
    const spec = parse({
      ...FREE_BODY,
      vectors: [
        { anchor: [0, 0], dx: 20, dy: 0, label: "F = 20 N", role: "force" },
        { anchor: [0, -0.9], dx: 4, dy: 0, label: "a = 4 m/s²", role: "motion" },
      ],
    });
    expect(vectorScreenLengths(spec, 10)).toEqual([ARROW_MAX_LENGTH, ARROW_MAX_LENGTH]);
  });

  it("draws an old server's unit vectors all at the full length", () => {
    const spec = parse({
      ...LEVER,
      vectors: LEVER.vectors.map((v) => ({ ...v, dy: -1 })),
    });
    expect(vectorScreenLengths(spec, 10)).toEqual([ARROW_MAX_LENGTH, ARROW_MAX_LENGTH]);
  });
});

describe("arrows stay on the canvas", () => {
  it("shortens an arrow that would leave the canvas", () => {
    // 100 px from the bottom of a 240 px canvas, pointing down.
    expect(fitArrowLength(50, 200, 0, 1, 80, 300, 240)).toBe(240 - ARROW_EDGE_INSET - 200);
    // Diagonal toward the right edge: the x limit binds first.
    const s = Math.SQRT1_2;
    const length = fitArrowLength(280, 100, s, s, 80, 300, 240);
    expect(280 + s * length).toBeCloseTo(300 - ARROW_EDGE_INSET, 6);
  });

  it("leaves an arrow that fits alone", () => {
    expect(fitArrowLength(150, 120, 1, 0, 48, 300, 240)).toBe(48);
  });

  it("keeps the old torque arrow's tip and head inside", () => {
    // A unit direction once came out hundreds of pixels long and lost its
    // head off the bottom of the canvas.
    const spec = parse({
      type: "lever",
      bodies: [],
      beam: [-0.375, 0, 0.375, 0],
      pivot: [0, 0],
      vectors: [{ anchor: [0.3, 0], dx: 0, dy: -1, label: "50 N at 0.3 m", role: "force" }],
      x_min: -0.43,
      x_max: 0.43,
      y_min: -0.21,
      y_max: 0.21,
      arrows: [],
    });
    const { height, scene } = layout(spec);
    for (const { tip, from } of scene.vectors) {
      expect(Math.hypot(tip.px - from.px, tip.py - from.py)).toBeLessThanOrEqual(
        ARROW_MAX_LENGTH + 1e-9,
      );
      expect(tip.py).toBeLessThanOrEqual(height - ARROW_EDGE_INSET);
    }
  });

  it("shortens a derived arrow at the edge and starts it at the body's rim", () => {
    const context = {
      tangent: { dx: 0, dy: 0 },
      maxSpeed: 0,
      centre: null,
      slope: null,
      width: 300,
      height: 150,
    };
    const ball = { px: 40, py: 120 };
    const gravity = derivedArrowGeometry("gravity", ball, 6, context)!;

    expect(gravity.fromY).toBe(126);
    expect(gravity.fromY + gravity.length).toBeCloseTo(150 - ARROW_EDGE_INSET, 6);
  });

  it("never runs a centripetal arrow past the centre", () => {
    const centre = { px: 100, py: 100 };
    const arrow = derivedArrowGeometry("centripetal", { px: 130, py: 100 }, 5, {
      tangent: { dx: 0, dy: 0 },
      maxSpeed: 0,
      centre,
      slope: null,
      width: 300,
      height: 300,
    })!;
    expect(arrow.fromX + arrow.ux * arrow.length).toBeGreaterThan(centre.px);
  });
});

describe("velocity length follows speed", () => {
  it("is the full length at top speed, in proportion below it, floored, and absent at rest", () => {
    expect(velocityArrowLength(10, 10)).toBe(ARROW_MAX_LENGTH);
    expect(velocityArrowLength(5, 10)).toBe(ARROW_MAX_LENGTH / 2);
    expect(velocityArrowLength(0.1, 10)).toBe(VELOCITY_MIN_LENGTH);
    expect(velocityArrowLength(0, 10)).toBe(0);
  });

  it("reads speed per sample, so the ends of a steady path are not half speed", () => {
    // The window is cut in half at the ends; dividing by its span keeps the
    // speed at t = 0 the same as in the middle.
    const steady: ScreenPoint[] = Array.from({ length: 51 }, (_, i) => ({ px: i * 2, py: 0 }));
    for (const progress of [0, 0.5, 1]) {
      expect(tangentAt(steady, progress)).toEqual({ dx: 2, dy: 0 });
    }
  });

  it("is shorter at the apex of a throw than at launch", () => {
    // Sampled at uniform time: x steps evenly, y rises then falls.
    const throwPath: ScreenPoint[] = Array.from({ length: 41 }, (_, i) => {
      const time = i / 40;
      return { px: time * 200, py: 200 - (400 * time - 400 * time * time) };
    });
    const max = maxTrackSpeed(throwPath);
    const launch = tangentAt(throwPath, 0);
    const apex = tangentAt(throwPath, 0.5);
    const atLaunch = velocityArrowLength(Math.hypot(launch.dx, launch.dy), max);
    const atApex = velocityArrowLength(Math.hypot(apex.dx, apex.dy), max);

    expect(atLaunch).toBeGreaterThan(atApex * 1.5);
  });
});

describe("closed paths", () => {
  const N = 96;
  const orbit: ScreenPoint[] = Array.from({ length: N + 1 }, (_, i) => {
    const angle = (2 * Math.PI * i) / N;
    // Counter-clockwise in the world is clockwise on screen (y down).
    return { px: 100 + 50 * Math.cos(angle), py: 100 - 50 * Math.sin(angle) };
  });

  it("recognises a loop the motion carries on round", () => {
    expect(isClosedPath(orbit)).toBe(true);
  });

  it("does not take a throw caught where it started for a loop", () => {
    // Back to the start, but arriving the opposite way: wrapping would
    // average the throw with the catch.
    const upAndDown: ScreenPoint[] = Array.from({ length: 21 }, (_, i) => ({
      px: 0,
      py: -(10 * i - 0.5 * i * i),
    }));
    expect(isClosedPath(upAndDown)).toBe(false);
    expect(isClosedPath(orbit.slice(0, 50))).toBe(false);
    expect(isClosedPath([{ px: 1, py: 1 }, { px: 1, py: 1 }, { px: 1, py: 1 }, { px: 1, py: 1 }])).toBe(
      false,
    );
  });

  it("keeps an orbit's velocity tangent at the start and the end", () => {
    // Clamping the window at the ends tilted the arrow about 7.6° there.
    for (const progress of [0, 1]) {
      const v = tangentAt(orbit, progress, true);
      // At (150, 100) the radius is horizontal, so the tangent is vertical.
      expect(Math.abs(Math.atan2(v.dx, -v.dy))).toBeLessThan(1e-9);
    }
    const clamped = tangentAt(orbit, 0, false);
    expect(Math.abs(Math.atan2(clamped.dx, -clamped.dy) * (180 / Math.PI))).toBeGreaterThan(5);
  });

  it("turns smoothly between samples instead of snapping to the nearest one", () => {
    // 95 laps' worth of samples puts t = 0.5 halfway between two of them.
    const odd: ScreenPoint[] = Array.from({ length: 96 }, (_, i) => {
      const angle = (2 * Math.PI * i) / 95;
      return { px: 100 + 50 * Math.cos(angle), py: 100 - 50 * Math.sin(angle) };
    });
    const v = tangentAt(odd, 0.5, true);
    // Halfway round, at (50, 100): the tangent is straight down the screen.
    expect(Math.abs(Math.atan2(v.dx, v.dy))).toBeLessThan(1e-9);
  });

  it("keeps the orbit speed even round the join", () => {
    const start = tangentAt(orbit, 0, true);
    const middle = tangentAt(orbit, 0.37, true);
    expect(Math.hypot(start.dx, start.dy)).toBeCloseTo(Math.hypot(middle.dx, middle.dy), 1);
  });
});

describe("body labels", () => {
  it("centres the label above the body, its baseline six points over the top", () => {
    const offset = bodyLabelOffset("above", 10, 40, FONT);
    const box = { x: offset.dx, y: offset.dy, width: 40, height: FONT };
    expect(box.x + box.width / 2).toBe(0);
    expect(box.y + FONT * 0.8).toBeCloseTo(-16, 6);
  });

  it("puts a collision's two labels above one ball and below the other", () => {
    const spec = parse({
      type: "collision",
      bodies: [
        { radius: 0.38, role: "primary", label: "2 kg", path: [[-2, 0], [-0.38, 0], [-0.1, 0]] },
        { radius: 0.3, role: "secondary", label: "1 kg", path: [[0.3, 0], [0.3, 0], [1.2, 0]] },
      ],
      x_min: -3.1,
      x_max: 3.7,
      y_min: -1.2,
      y_max: 1.2,
      arrows: ["velocity"],
    });
    const { scene } = layout(spec);
    const [primary, secondary] = scene.bodyLabels;

    expect(primary!.side).toBe("above");
    expect(secondary!.side).toBe("below");
    // Above the centre line for one, below it for the other: "2 kg" and
    // "1 kg" can no longer run together as "2 kg1 kg".
    expect(primary!.dy).toBeLessThan(0);
    expect(secondary!.dy).toBeGreaterThan(0);
  });

  it("moves a free body's label off the arrows that leave it up and down", () => {
    const { scene } = layout(parse(FREE_BODY));
    expect(scene.bodyLabels[0]!.side).toBe("right");
  });
});

describe("vector labels", () => {
  it("labels components beside their middles and the result at its tip", () => {
    const { scene } = layout(parse(RESOLVE));
    const [horizontal, vertical, result] = scene.vectors;
    const middle = (v: (typeof scene.vectors)[number]) => ({
      px: (v.from.px + v.tip.px) / 2,
      py: (v.from.py + v.tip.py) / 2,
    });
    const centre = (box: LabelBox) => ({ px: box.x + box.width / 2, py: box.y + box.height / 2 });

    // Horizontal component: label below its middle, outside the triangle.
    expect(centre(horizontal.label!.box).px).toBeCloseTo(middle(horizontal).px, 6);
    expect(centre(horizontal.label!.box).py).toBeGreaterThan(middle(horizontal).py);
    // Vertical component: label to the right of its middle.
    expect(centre(vertical.label!.box).px).toBeGreaterThan(middle(vertical).px);
    expect(centre(vertical.label!.box).py).toBeCloseTo(middle(vertical).py, 6);
    // The result past its own tip.
    expect(centre(result.label!.box).px).toBeGreaterThan(result.tip.px);
    expect(centre(result.label!.box).py).toBeLessThan(result.tip.py);
  });

  it("never overprints two labels in the scenes that used to", () => {
    for (const fixture of [RESOLVE, VECTOR_SUM, LEVER, FREE_BODY]) {
      const { scene } = layout(parse(fixture));
      const boxes = scene.vectors.flatMap((v) => (v.label ? [v.label.box] : []));
      for (let i = 0; i < boxes.length; i += 1) {
        for (let j = i + 1; j < boxes.length; j += 1) {
          expect(overlaps(boxes[i], boxes[j])).toBe(false);
        }
      }
    }
  });

  it("keeps every label on the canvas", () => {
    for (const fixture of [RESOLVE, VECTOR_SUM, LEVER, FREE_BODY]) {
      const { height, scene } = layout(parse(fixture));
      for (const { label } of scene.vectors) {
        if (!label) continue;
        expect(label.box.x).toBeGreaterThanOrEqual(0);
        expect(label.box.y).toBeGreaterThanOrEqual(0);
        expect(label.box.x + label.box.width).toBeLessThanOrEqual(WIDTH);
        expect(label.box.y + label.box.height).toBeLessThanOrEqual(height);
      }
    }
  });

  it("keeps a label off another arrow's line", () => {
    // The weight's label used to sit across the dashed height line beside it.
    const spec = parse({
      type: "free_body",
      title: "Free-Body Diagram",
      bodies: [{ radius: 0.32, role: "primary", label: "2 kg", path: [[0, 5], [0, 5]] }],
      vectors: [
        { anchor: [0, 5], dx: 0, dy: -1, label: "W = 19.6 N", role: "force" },
        { anchor: [-0.9, 0], dx: 0, dy: 5, label: "h = 5 m", role: "measure" },
      ],
      x_min: -2,
      x_max: 2,
      y_min: -0.7,
      y_max: 6,
      arrows: [],
      ground: true,
    });
    const { scene } = layout(spec);
    const [weight, height] = scene.vectors;
    const line = { x1: height.from.px, y1: height.from.py, x2: height.tip.px, y2: height.tip.py };
    expect(segmentHitsBox(line, weight.label!.box)).toBe(false);
    expect(overlaps(weight.label!.box, height.label!.box)).toBe(false);
  });
});

describe("lever loads", () => {
  it("keeps a load near the pivot clear of the wedge", () => {
    const pivot = { px: 150, py: 100 };
    const shifted = leverLoadAnchor({ px: 152, py: 100 }, 1, pivot);
    expect(shifted.px - pivot.px).toBeGreaterThanOrEqual(PIVOT_SIZE + 6);
    expect(shifted.py).toBe(100);

    const left = leverLoadAnchor({ px: 147, py: 100 }, 1, pivot);
    expect(pivot.px - left.px).toBeGreaterThanOrEqual(PIVOT_SIZE + 6);
  });

  it("leaves a load that is already clear, or one pulling up", () => {
    const pivot = { px: 150, py: 100 };
    expect(leverLoadAnchor({ px: 60, py: 100 }, 1, pivot)).toEqual({ px: 60, py: 100 });
    expect(leverLoadAnchor({ px: 151, py: 100 }, -1, pivot)).toEqual({ px: 151, py: 100 });
  });

  it("draws a 0.1 m load beside the fulcrum, not on it", () => {
    const spec = parse(LEVER);
    const { t, scene } = layout(spec);
    const pivot = worldToScreen(0, 0, t);
    expect(Math.abs(scene.vectors[1].from.px - pivot.px)).toBeGreaterThan(PIVOT_SIZE);
  });
});

describe("describeSimulation", () => {
  const t = (key: string, options?: Record<string, unknown>) => {
    const words: Record<string, string> = {
      "rich.simulation_title": "Simulation",
      "rich.simulation_a11y_body": "Object",
      "rich.simulation_a11y_slope": "Slope at {{degrees}}°",
      "rich.simulation_a11y_arrows": "Arrows: {{list}}",
      "rich.simulation_arrow_velocity": "velocity",
      "rich.simulation_arrow_gravity": "gravity",
    };
    return (words[key] ?? key).replace(/\{\{(\w+)\}\}/g, (_, name) => String(options?.[name]));
  };

  it("names the scene, its bodies and its arrows", () => {
    const spec = parse({
      type: "projectile_motion",
      title: "Projectile",
      bodies: [{ radius: 0.5, role: "primary", path: [[0, 0], [10, 5], [20, 0]] }],
      x_min: 0,
      x_max: 21,
      y_min: 0,
      y_max: 7,
      arrows: ["velocity", "gravity"],
      ground: true,
    });
    expect(describeSimulation(spec, t)).toBe("Projectile. Object. Arrows: velocity, gravity.");
  });

  it("reads out the values the solver stated", () => {
    expect(describeSimulation(parse(FREE_BODY), t)).toBe(
      "Free-Body Diagram. 5 kg. T = 59.1 N, W = 49.1 N.",
    );
  });

  it("states the slope angle of an incline", () => {
    const spec = parse({
      type: "incline",
      bodies: [{ radius: 0.36, role: "primary", path: [[0, 3], [0, 3]] }],
      x_min: -1,
      x_max: 6.2,
      y_min: -1,
      y_max: 4,
      arrows: ["gravity"],
      incline_deg: 30,
    });
    expect(describeSimulation(spec, t)).toBe("Simulation. Object. Slope at 30°. Arrows: gravity.");
  });
});

describe("projectPath stays the one mapping", () => {
  it("puts a still body's arrows at its rim, so the visible lengths keep their ratio", () => {
    const spec = parse(FREE_BODY);
    const { t, scene } = layout(spec);
    const body = projectPath(spec.bodies[0].path, t)[0];
    const radius = scene.radii[0];
    for (const vector of scene.vectors) {
      expect(Math.hypot(vector.from.px - body.px, vector.from.py - body.py)).toBeCloseTo(radius, 6);
    }
    const [up, down] = scene.vectors.map((v) => Math.hypot(v.tip.px - v.from.px, v.tip.py - v.from.py));
    expect(down / up).toBeCloseTo(49.05 / 59.05, 6);
  });
});
