/**
 * P14: parsing and geometry for the `simulation` fence.
 *
 * The scene's arithmetic is asserted here as plain functions; what only a
 * render can prove — that nothing autoplays, that Reduce Motion still draws
 * something — is in `components/__tests__/SimulationBlock.test.tsx`.
 *
 * The property this file exists for is the uniform scale. A graph stretches
 * each axis to fill its box, and doing that here would turn an orbit into an
 * ellipse and a 30° launch into some other angle — a picture that contradicts
 * the verified number printed beside it.
 */
import { clampCanvasLabelBaseline, clampCanvasLabelX, derivedArrowGeometry, inclineDirections, inclineSurface, parseSimulationSpec, simulationTransform, simulationViewportHeight, tangentAt, worldToScreen } from "@/lib/physics/simulation";
import { maxTrackSpeed } from "@/lib/physics/simulation/paths";
import { projectPath } from "@/lib/physics/simulation/viewport";

const PROJECTILE = {
  type: "projectile_motion",
  title: "Projectile",
  bodies: [
    {
      radius: 0.5,
      role: "primary",
      path: [
        [0, 0],
        [10, 7],
        [20, 10],
        [30, 7],
        [40, 0],
      ],
    },
  ],
  x_min: 0,
  x_max: 40,
  y_min: 0,
  y_max: 20,
  arrows: ["velocity", "gravity"],
  ground: true,
};

const ORBIT = {
  type: "orbit",
  bodies: [
    {
      radius: 0.4,
      role: "primary",
      path: [
        [5, 0],
        [0, 5],
        [-5, 0],
        [0, -5],
        [5, 0],
      ],
    },
  ],
  x_min: -6,
  x_max: 6,
  y_min: -6,
  y_max: 6,
  arrows: ["velocity", "centripetal"],
  centre: [0, 0],
  ground: false,
};

function parse(spec: object) {
  return parseSimulationSpec(JSON.stringify(spec));
}

describe("parseSimulationSpec", () => {
  it("reads a projectile scene", () => {
    const spec = parse(PROJECTILE);

    expect(spec).not.toBeNull();
    expect(spec!.type).toBe("projectile_motion");
    expect(spec!.bodies).toHaveLength(1);
    expect(spec!.bodies[0].path).toHaveLength(5);
    expect(spec!.arrows).toEqual(["velocity", "gravity"]);
    expect(spec!.ground).toBe(true);
  });

  it("reads a spring scene only when the wall is stated", () => {
    const spring = {
      type: "spring",
      bodies: [
        {
          radius: 0.2,
          role: "primary",
          path: [
            [-1, 0.2],
            [0, 0.2],
            [1, 0.2],
          ],
        },
      ],
      x_min: -2,
      x_max: 1.5,
      y_min: 0,
      y_max: 1,
      ground: true,
      anchor: [-1.8, 0.2],
    };

    const spec = parse(spring);
    expect(spec!.type).toBe("spring");
    expect(spec!.anchor).toEqual({ x: -1.8, y: 0.2 });
    expect(parse({ ...spring, anchor: undefined })).toBeNull();
  });

  it("reads an orbit scene with its centre", () => {
    const spec = parse(ORBIT);

    expect(spec!.type).toBe("orbit");
    expect(spec!.centre).toEqual({ x: 0, y: 0 });
    expect(spec!.arrows).toContain("centripetal");
  });

  it("drops a centripetal arrow that has no centre to point at", () => {
    // "Toward the centre" with no centre would be drawn toward the origin of
    // the scene box, which is a different place and a wrong picture.
    const spec = parse({ ...ORBIT, centre: undefined });

    expect(spec!.arrows).toEqual(["velocity"]);
  });

  it.each([
    ["an unknown type", { ...PROJECTILE, type: "explosion" }],
    ["no bodies", { ...PROJECTILE, bodies: [] }],
    ["a one-sample path", { ...PROJECTILE, bodies: [{ ...PROJECTILE.bodies[0], path: [[0, 0]] }] }],
    ["a non-finite sample", {
      ...PROJECTILE,
      bodies: [{ ...PROJECTILE.bodies[0], path: [[0, 0], [1, null]] }],
    }],
    ["inverted bounds", { ...PROJECTILE, x_min: 40, x_max: 0 }],
  ])("refuses %s", (_label, bad) => {
    expect(parse(bad)).toBeNull();
  });

  it("refuses bodies sampled at different rates", () => {
    // One clock walks every body, so mismatched lengths would show a two-body
    // scene out of step — a collision at the wrong moment.
    const spec = parse({
      ...PROJECTILE,
      bodies: [
        PROJECTILE.bodies[0],
        { ...PROJECTILE.bodies[0], path: [[0, 0], [1, 1], [2, 2]] },
      ],
    });

    expect(spec).toBeNull();
  });

  it("refuses text that is not JSON", () => {
    expect(parseSimulationSpec("not json at all")).toBeNull();
  });
});

describe("simulationTransform", () => {
  it("uses a compact viewport for every wide scene and a full one for square scenes", () => {
    const wide = parse({ ...PROJECTILE, x_max: 42, y_max: 14 })!;
    const square = parse(ORBIT)!;

    expect(simulationViewportHeight(wide, 360, 24, 136, 240)).toBe(152);
    expect(simulationViewportHeight(square, 360, 24, 136, 240)).toBe(240);
  });

  it("uses one scale for both axes", () => {
    // The whole reason this is not `mapGraphPoint`. A 12x12 world in a
    // 360x240 box is limited by height, so both axes take the height's scale.
    const spec = parse(ORBIT)!;
    const t = simulationTransform(spec, 360, 240, 24);

    const right = worldToScreen(5, 0, t);
    const top = worldToScreen(0, 5, t);
    const centre = worldToScreen(0, 0, t);

    expect(right.px - centre.px).toBeCloseTo(centre.py - top.py, 6);
  });

  it("keeps a circular path circular", () => {
    const spec = parse(ORBIT)!;
    const t = simulationTransform(spec, 360, 240, 24);
    const centre = worldToScreen(0, 0, t);

    const radii = projectPath(spec.bodies[0].path, t).map((p) =>
      Math.hypot(p.px - centre.px, p.py - centre.py),
    );

    for (const r of radii) expect(r).toBeCloseTo(radii[0], 6);
  });

  it("centres the scene in whichever direction has slack", () => {
    const spec = parse(ORBIT)!;
    const t = simulationTransform(spec, 360, 240, 24);
    const left = worldToScreen(-6, 0, t);
    const right = worldToScreen(6, 0, t);

    expect((left.px + right.px) / 2).toBeCloseTo(180, 6);
  });

  it("puts world y upward and screen y downward", () => {
    const spec = parse(PROJECTILE)!;
    const t = simulationTransform(spec, 360, 240, 24);

    expect(worldToScreen(0, 10, t).py).toBeLessThan(worldToScreen(0, 0, t).py);
  });
});

describe("canvas label safety", () => {
  it("keeps labels inside both horizontal edges", () => {
    expect(clampCanvasLabelX(-30, 80, 360)).toBe(4);
    expect(clampCanvasLabelX(350, 80, 360)).toBe(276);
  });

  it("keeps the full line of text inside both vertical edges", () => {
    expect(clampCanvasLabelBaseline(-20, 11, 152)).toBe(15);
    expect(clampCanvasLabelBaseline(180, 11, 152)).toBe(148);
  });
});

describe("tangentAt", () => {
  it("points along the direction of travel", () => {
    const spec = parse(PROJECTILE)!;
    const t = simulationTransform(spec, 360, 240, 24);
    const track = projectPath(spec.bodies[0].path, t);

    // Rising at launch: x increases, and screen y decreases going up.
    const start = tangentAt(track, 0);
    expect(start.dx).toBeGreaterThan(0);
    expect(start.dy).toBeLessThan(0);

    // Falling at the end: still moving right, now moving down the screen.
    const end = tangentAt(track, 1);
    expect(end.dx).toBeGreaterThan(0);
    expect(end.dy).toBeGreaterThan(0);
  });

  it("returns zero for a body that is not moving", () => {
    // Collisions made this a real case rather than a rounding artefact: a ball
    // waiting to be hit genuinely has no velocity, and a held block never
    // moves at all. An earlier draft returned a default direction here, which
    // would draw a confident velocity arrow on a stationary ball.
    //
    // The random-flip hazard this replaces is handled by the window: a body
    // that moved at all over 4% of its journey has a non-zero delta, even
    // where two adjacent samples round to the same pixel.
    const stationary = [
      { px: 10, py: 10 },
      { px: 10, py: 10 },
      { px: 10, py: 10 },
    ];

    expect(tangentAt(stationary, 0.5)).toEqual({ dx: 0, dy: 0 });
  });

  it("a zero direction draws no arrow at all", () => {
    // The other half of the same decision: no geometry renders nothing, so
    // the velocity arrow appears at the moment of the collision — which is
    // the moment it means something.
    expect(
      derivedArrowGeometry("velocity", { px: 5, py: 5 }, 4, {
        tangent: { dx: 0, dy: 0 },
        maxSpeed: 10,
        centre: null,
        slope: null,
        width: 360,
        height: 240,
      }),
    ).toBeNull();
  });

  it("clamps progress outside 0..1", () => {
    const spec = parse(PROJECTILE)!;
    const t = simulationTransform(spec, 360, 240, 24);
    const track = projectPath(spec.bodies[0].path, t);

    expect(tangentAt(track, -3)).toEqual(tangentAt(track, 0));
    expect(tangentAt(track, 9)).toEqual(tangentAt(track, 1));
  });
});

// --- the two scenes P14's second slice added -------------------------------

const COLLISION = {
  type: "collision",
  bodies: [
    {
      radius: 0.38,
      role: "primary",
      path: [
        [-2, 0],
        [-1, 0],
        [-0.38, 0],
      ],
    },
    {
      radius: 0.3,
      role: "secondary",
      path: [
        [0.3, 0],
        [0.3, 0],
        [0.3, 0],
      ],
    },
  ],
  x_min: -3,
  x_max: 3,
  y_min: -1,
  y_max: 1,
  arrows: ["velocity"],
};

const INCLINE = {
  type: "incline",
  bodies: [
    {
      radius: 0.36,
      role: "primary",
      path: [
        [0, 3],
        [0, 3],
      ],
    },
  ],
  x_min: -1,
  x_max: 6.2,
  y_min: -1,
  y_max: 4,
  arrows: ["gravity", "normal", "friction"],
  incline_deg: 30,
};

describe("collision and incline scenes", () => {
  it("reads a two-body collision", () => {
    const spec = parse(COLLISION);

    expect(spec!.type).toBe("collision");
    expect(spec!.bodies.map((b) => b.role)).toEqual(["primary", "secondary"]);
    // The heavier ball is drawn larger, which is how you tell them apart.
    expect(spec!.bodies[0].radius).toBeGreaterThan(spec!.bodies[1].radius);
  });

  it("gives a ball at rest no velocity arrow until it moves", () => {
    // Body 2 sits still for the whole of this fixture. Its tangent is zero, so
    // no arrow is drawn — the arrow appears at the collision.
    const spec = parse(COLLISION)!;
    const t = simulationTransform(spec, 360, 240, 24);
    const still = projectPath(spec.bodies[1].path, t);
    const moving = projectPath(spec.bodies[0].path, t);
    const context = (tangent: { dx: number; dy: number }) => ({
      tangent,
      maxSpeed: maxTrackSpeed(moving),
      centre: null,
      slope: null,
      width: 360,
      height: 240,
    });

    expect(derivedArrowGeometry("velocity", still[1], 4, context(tangentAt(still, 0.5)))).toBeNull();
    expect(
      derivedArrowGeometry("velocity", moving[1], 4, context(tangentAt(moving, 0.5))),
    ).not.toBeNull();
  });

  it("reads an incline with its slope angle", () => {
    const spec = parse(INCLINE);

    expect(spec!.type).toBe("incline");
    expect(spec!.inclineDeg).toBe(30);
    expect(spec!.arrows).toEqual(["gravity", "normal", "friction"]);
  });

  it("drops normal and friction arrows when no slope is stated", () => {
    // Both are read off the slope, not off the motion. Without one they would
    // be drawn in some default direction, and a normal force pointing the
    // wrong way is a more confident lie than no arrow.
    const spec = parse({ ...INCLINE, incline_deg: undefined });

    expect(spec!.arrows).toEqual(["gravity"]);
  });
});

describe("inclineDirections", () => {
  it("keeps the normal perpendicular to the slope", () => {
    // The property the name promises. A normal that is not normal to the
    // surface it acts on is the one mistake this diagram must not make.
    for (const deg of [0, 15, 30, 45, 60, 80]) {
      const { normal, friction } = inclineDirections(deg);
      const downhill = { dx: -friction.dx, dy: -friction.dy };

      expect(normal.dx * downhill.dx + normal.dy * downhill.dy).toBeCloseTo(0, 10);
      expect(Math.hypot(normal.dx, normal.dy)).toBeCloseTo(1, 10);
    }
  });

  it("points the normal away from the surface and friction up the slope", () => {
    const { normal, friction } = inclineDirections(30);

    // Screen y is downward, so "away from the surface" is a negative dy.
    expect(normal.dy).toBeLessThan(0);
    // The block slides down to the right, so friction opposes it: up and left.
    expect(friction.dx).toBeLessThan(0);
    expect(friction.dy).toBeLessThan(0);
  });

  it("is straight up and straight back on the flat", () => {
    const { normal, friction } = inclineDirections(0);

    expect(normal).toEqual({ dx: 0, dy: -1 });
    expect(friction.dx).toBeCloseTo(-1, 10);
    expect(friction.dy).toBeCloseTo(0, 10);
  });
});

describe("inclineSurface", () => {
  it("draws a line that descends left to right", () => {
    const spec = parse(INCLINE)!;
    const t = simulationTransform(spec, 360, 240, 24);
    const line = inclineSurface(spec, t)!;

    expect(line.x1).toBeLessThan(line.x2);
    // Descending in the world means a larger screen y on the right.
    expect(line.y2).toBeGreaterThan(line.y1);
  });

  it("passes under the block rather than through it", () => {
    // The block rests *on* the slope, so the surface is one radius away along
    // the normal — not through the centre of the body.
    const spec = parse(INCLINE)!;
    const t = simulationTransform(spec, 360, 240, 24);
    const line = inclineSurface(spec, t)!;
    const body = projectPath(spec.bodies[0].path, t)[0];

    // Distance from the body centre to the line, in pixels.
    const dx = line.x2 - line.x1;
    const dy = line.y2 - line.y1;
    const distance =
      Math.abs(dy * body.px - dx * body.py + line.x2 * line.y1 - line.y2 * line.x1) /
      Math.hypot(dx, dy);

    expect(distance).toBeCloseTo(spec.bodies[0].radius * t.scale, 4);
  });

  it("returns nothing when the scene has no slope", () => {
    const spec = parse(PROJECTILE)!;
    const t = simulationTransform(spec, 360, 240, 24);

    expect(inclineSurface(spec, t)).toBeNull();
  });
});

// --- the still figures ------------------------------------------------------
//
// Four scene types have something moving; three do not. A see-saw, a free-body
// diagram and a sum of force vectors are pictures of forces, not of motion, and
// their arrows are *stated* by the solver rather than read off a path — because
// the direction of a resultant is the answer, not a consequence of it.

const LEVER = {
  type: "lever",
  title: "Moments",
  bodies: [],
  beam: [-2.5, 0, 2.5, 0],
  pivot: [0, 0],
  vectors: [
    { anchor: [-2, 0], dx: 0, dy: -1, label: "5 N at 2 m", role: "force" },
    { anchor: [1, 0], dx: 0, dy: -1, label: "10 N at 1.00 m", role: "result" },
  ],
  x_min: -2.9,
  x_max: 2.9,
  y_min: -1.4,
  y_max: 1.4,
  arrows: [],
};

const VECTOR_SUM = {
  type: "vector_sum",
  bodies: [],
  vectors: [
    { anchor: [0, 0], dx: 3, dy: 0, label: "3 N", role: "force" },
    { anchor: [0, 0], dx: 0, dy: 4, label: "4 N", role: "force" },
    { anchor: [0, 0], dx: 3, dy: 4, label: "5.00 N", role: "result" },
  ],
  x_min: -1.6,
  x_max: 6.5,
  y_min: -1.6,
  y_max: 6.5,
  arrows: [],
};

describe("still figures", () => {
  it("reads a lever with its beam, pivot and loads", () => {
    const spec = parse(LEVER);

    expect(spec!.type).toBe("lever");
    expect(spec!.bodies).toHaveLength(0);
    expect(spec!.beam).toEqual({ x1: -2.5, y1: 0, x2: 2.5, y2: 0 });
    expect(spec!.pivot).toEqual({ x: 0, y: 0 });
    expect(spec!.vectors.map((v) => v.label)).toEqual(["5 N at 2 m", "10 N at 1.00 m"]);
  });

  it("marks the arm that was the question", () => {
    // The see-saw makes P9's pairing bug visible: the arm each force actually
    // has is drawn where it is, so a diagram reading 2 m under the wrong force
    // would be obvious rather than silent.
    const spec = parse(LEVER)!;
    const answer = spec.vectors.filter((v) => v.role === "result");

    expect(answer).toHaveLength(1);
    expect(answer[0].anchor.x).toBeGreaterThan(0);
  });

  it("reads a vector sum", () => {
    const spec = parse(VECTOR_SUM);

    expect(spec!.vectors).toHaveLength(3);
    expect(spec!.vectors.filter((v) => v.role === "result")).toHaveLength(1);
  });

  it("accepts a scene with vectors and no bodies", () => {
    // A still figure has nothing to walk a clock through, so requiring a body
    // would make the whole family unexpressible.
    expect(parse({ ...LEVER, bodies: undefined })).not.toBeNull();
  });

  it("refuses a scene with neither bodies nor vectors", () => {
    expect(parse({ ...LEVER, bodies: [], vectors: [] })).toBeNull();
  });

  it("refuses a vector with no direction", () => {
    // Zero length is not an arrow pointing nowhere, it is a missing answer.
    expect(parse({ ...LEVER, vectors: [{ anchor: [0, 0], dx: 0, dy: 0 }] })).toBeNull();
  });

  it("refuses a vector whose anchor is not a finite pair", () => {
    expect(parse({ ...LEVER, vectors: [{ anchor: [0], dx: 1, dy: 0 }] })).toBeNull();
    expect(parse({ ...LEVER, vectors: [{ anchor: [0, null], dx: 1, dy: 0 }] })).toBeNull();
  });

  it("ignores a pivot with no beam to sit under", () => {
    // On its own it is a dot in space; the beam is what makes it read as a
    // fulcrum.
    const spec = parse({ ...LEVER, beam: undefined });

    expect(spec!.beam).toBeUndefined();
    expect(spec!.pivot).toBeUndefined();
  });
});
