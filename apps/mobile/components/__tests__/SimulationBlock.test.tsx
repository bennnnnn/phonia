/**
 * P14: the simulation scene's render behaviour.
 *
 * Its arithmetic is asserted as pure functions in
 * `lib/__tests__/simulationScene.test.ts` and `simulationLayout.test.ts`. What
 * is left here is the part only a render can prove: when the scene moves by
 * itself and when it waits, that Reduce Motion still gets a real diagram and a
 * way to play it, and that an arrow is never drawn without the thing it points
 * at.
 *
 * The geometry markers a test reads are hidden from screen readers, so every
 * marker query passes `HIDDEN`.
 */
import { fireEvent, render } from "@testing-library/react-native";
import { Dimensions, StyleSheet } from "react-native";

import { simulationPlaceholderHeight } from "@/components/rich/simulationPlaceholder";
import { SimulationBlock } from "@/components/rich/SimulationBlock";
import { Space } from "@/lib/space";

const HIDDEN = { includeHiddenElements: true };

/** The OS setting: `null` while it is still being read. */
const mockUseReduceMotion = jest.fn<boolean | null, []>(() => false);
jest.mock("@/lib/motion", () => ({
  ...jest.requireActual("@/lib/motion"),
  useReduceMotion: () => mockUseReduceMotion() ?? false,
  useReduceMotionSetting: () => mockUseReduceMotion(),
}));

const PROJECTILE = JSON.stringify({
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
  x_max: 42,
  y_min: 0,
  y_max: 14,
  arrows: ["velocity", "gravity"],
  ground: true,
});

const ORBIT = JSON.stringify({
  type: "orbit",
  title: "Circular Motion",
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
  x_min: -7,
  x_max: 7,
  y_min: -7,
  y_max: 7,
  arrows: ["velocity", "centripetal"],
  centre: [0, 0],
  ground: false,
});

const SPRING = JSON.stringify({
  type: "spring",
  title: "Spring",
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
  x_min: -2.4,
  x_max: 1.5,
  y_min: 0,
  y_max: 1,
  ground: true,
  anchor: [-2, 0.2],
});

beforeEach(() => {
  mockUseReduceMotion.mockReturnValue(false);
});

describe("SimulationBlock", () => {
  it("renders a projectile scene with a body, its arrows and the ground", async () => {
    const { getByTestId, getAllByTestId } = await render(<SimulationBlock content={PROJECTILE} />);

    expect(getAllByTestId("simulation-body", HIDDEN).length).toBe(1);
    expect(getByTestId("simulation-arrow-velocity", HIDDEN)).toBeTruthy();
    expect(getByTestId("simulation-arrow-gravity", HIDDEN)).toBeTruthy();
    expect(getByTestId("simulation-ground", HIDDEN)).toBeTruthy();
  });

  it("renders a spring from the wall the solver stated", async () => {
    const { getByTestId, getByText, queryByTestId } = await render(
      <SimulationBlock content={SPRING} />,
    );

    expect(getByText("Spring")).toBeTruthy();
    expect(getByTestId("simulation-spring", HIDDEN)).toBeTruthy();
    expect(getByTestId("simulation-body", HIDDEN)).toBeTruthy();
    expect(getByTestId("simulation-ground", HIDDEN)).toBeTruthy();
    expect(queryByTestId("simulation-arrow-gravity", HIDDEN)).toBeNull();
  });

  it("renders an orbit with its centre and a centripetal arrow", async () => {
    // The kind that drew nothing at all before this ticket.
    const { getByTestId, queryByTestId } = await render(<SimulationBlock content={ORBIT} />);

    expect(getByTestId("simulation-centre", HIDDEN)).toBeTruthy();
    expect(getByTestId("simulation-arrow-centripetal", HIDDEN)).toBeTruthy();
    expect(queryByTestId("simulation-ground", HIDDEN)).toBeNull();
  });

  it("starts moving scenes automatically and lets the user pause or resume them", async () => {
    const { getByLabelText, getByTestId } = await render(
      <SimulationBlock content={PROJECTILE} />,
    );

    expect(getByTestId("simulation-control")).toBeTruthy();
    expect(getByTestId("simulation-stop-symbol").props.name).toBe("pause");
    await fireEvent.press(getByLabelText("rich.simulation_pause_a11y"));
    expect(getByTestId("simulation-play-symbol").props.name).toBe("play");
    await fireEvent.press(getByLabelText("rich.simulation_play_a11y"));
    expect(getByTestId("simulation-stop-symbol").props.name).toBe("pause");
  });

  it("falls back to a static diagram under Reduce Motion, with Play still offered", async () => {
    // Not a blank space: the body and its force arrows at the first sample are
    // a free-body diagram, which is most of what the picture is for. Motion
    // the user starts is fine, so the button stays.
    mockUseReduceMotion.mockReturnValue(true);
    const { getByTestId, queryByTestId } = await render(<SimulationBlock content={PROJECTILE} />);

    expect(getByTestId("simulation-static", HIDDEN)).toBeTruthy();
    expect(getByTestId("simulation-body", HIDDEN)).toBeTruthy();
    expect(getByTestId("simulation-arrow-gravity", HIDDEN)).toBeTruthy();
    expect(getByTestId("simulation-ground", HIDDEN)).toBeTruthy();
    expect(getByTestId("simulation-control")).toBeTruthy();
    expect(getByTestId("simulation-play-symbol").props.name).toBe("play");
    expect(queryByTestId("simulation-stop-symbol")).toBeNull();
  });

  it("never draws a centripetal arrow without a centre", async () => {
    // "Toward the centre" with nothing at the centre would point at the origin
    // of the scene box instead — a confident arrow at the wrong target.
    const noCentre = JSON.stringify({ ...JSON.parse(ORBIT), centre: undefined });
    const { queryByTestId } = await render(<SimulationBlock content={noCentre} />);

    expect(queryByTestId("simulation-arrow-centripetal", HIDDEN)).toBeNull();
    expect(queryByTestId("simulation-centre", HIDDEN)).toBeNull();
    // The rest of the scene still renders.
    expect(queryByTestId("simulation-arrow-velocity", HIDDEN)).toBeTruthy();
  });

  it("shows its fallback rather than half a scene when the spec is unreadable", async () => {
    const { queryByTestId } = await render(<SimulationBlock content="{ not json" />);

    expect(queryByTestId("simulation-body", HIDDEN)).toBeNull();
    expect(queryByTestId("simulation-control")).toBeNull();
  });

  it("renders every body in a multi-body scene", async () => {
    // The shape collisions will use: two bodies, one clock.
    const pair = JSON.parse(PROJECTILE);
    const twoBodies = JSON.stringify({
      ...pair,
      bodies: [
        pair.bodies[0],
        { ...pair.bodies[0], role: "secondary" },
      ],
    });
    const { getAllByTestId } = await render(<SimulationBlock content={twoBodies} />);

    expect(getAllByTestId("simulation-body", HIDDEN).length).toBe(2);
  });
});

const COLLISION = JSON.stringify({
  type: "collision",
  title: "Collision",
  bodies: [
    { radius: 0.38, role: "primary", path: [[-2, 0], [-1, 0], [-0.38, 0], [0, 0]] },
    { radius: 0.3, role: "secondary", path: [[0.3, 0], [0.3, 0], [0.3, 0], [1.2, 0]] },
  ],
  x_min: -3,
  x_max: 3,
  y_min: -1,
  y_max: 1,
  arrows: ["velocity"],
});

const INCLINE = JSON.stringify({
  type: "incline",
  title: "Inclined Plane",
  bodies: [{ radius: 0.36, role: "primary", path: [[0, 3], [0, 3]] }],
  x_min: -1,
  x_max: 6.2,
  y_min: -1,
  y_max: 4,
  arrows: ["gravity", "normal", "friction"],
  incline_deg: 30,
});

describe("SimulationBlock: collisions and inclines", () => {
  it("renders both bodies of a collision", async () => {
    // The scene a number cannot replace: "1.00 m/s and 4.00 m/s" says nothing
    // about which ball ends up ahead or whether either turns around.
    const { getAllByTestId, queryByTestId } = await render(<SimulationBlock content={COLLISION} />);

    expect(getAllByTestId("simulation-body", HIDDEN).length).toBe(2);
    expect(getAllByTestId("simulation-arrow-velocity", HIDDEN).length).toBe(2);
    expect(queryByTestId("simulation-ground", HIDDEN)).toBeNull();
    expect(queryByTestId("simulation-slope", HIDDEN)).toBeNull();
  });

  it("draws the slope an incline block sits on", async () => {
    const { getByTestId, queryByTestId } = await render(<SimulationBlock content={INCLINE} />);

    expect(getByTestId("simulation-slope", HIDDEN)).toBeTruthy();
    expect(getByTestId("simulation-arrow-normal", HIDDEN)).toBeTruthy();
    expect(getByTestId("simulation-arrow-friction", HIDDEN)).toBeTruthy();
    expect(getByTestId("simulation-arrow-gravity", HIDDEN)).toBeTruthy();
    // Not a projectile: no flat ground line under a slope.
    expect(queryByTestId("simulation-ground", HIDDEN)).toBeNull();
  });

  it("gives a held block its free-body diagram under Reduce Motion", async () => {
    // For two of the three friction ops the block never moves, so the still
    // picture is not a fallback — it is the answer's illustration.
    mockUseReduceMotion.mockReturnValue(true);
    const { getByTestId, queryByTestId } = await render(<SimulationBlock content={INCLINE} />);

    expect(getByTestId("simulation-static", HIDDEN)).toBeTruthy();
    expect(getByTestId("simulation-arrow-normal", HIDDEN)).toBeTruthy();
    expect(getByTestId("simulation-arrow-friction", HIDDEN)).toBeTruthy();
    expect(getByTestId("simulation-slope", HIDDEN)).toBeTruthy();
    expect(queryByTestId("simulation-control")).toBeNull();
  });

  it("never draws a normal or friction arrow without a slope", async () => {
    const noSlope = JSON.stringify({ ...JSON.parse(INCLINE), incline_deg: undefined });
    const { queryByTestId } = await render(<SimulationBlock content={noSlope} />);

    expect(queryByTestId("simulation-arrow-normal", HIDDEN)).toBeNull();
    expect(queryByTestId("simulation-arrow-friction", HIDDEN)).toBeNull();
    expect(queryByTestId("simulation-slope", HIDDEN)).toBeNull();
    // Weight still points down whatever the surface does.
    expect(queryByTestId("simulation-arrow-gravity", HIDDEN)).toBeTruthy();
  });
});

const LEVER = JSON.stringify({
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
});

const FREE_BODY = JSON.stringify({
  type: "free_body",
  title: "Free-Body Diagram",
  bodies: [{ radius: 0.32, role: "primary", label: "5 kg", path: [[0, 0], [0, 0]] }],
  vectors: [
    { anchor: [0, 0], dx: 0, dy: 1, label: "T = 59.05 N", role: "result" },
    { anchor: [0, 0], dx: 0, dy: -1, label: "W = 49.05 N", role: "force" },
  ],
  x_min: -2,
  x_max: 2,
  y_min: -2,
  y_max: 2,
  arrows: [],
});

describe("SimulationBlock: still figures", () => {
  it("draws a see-saw as beam, pivot and two labelled loads", async () => {
    const { getByTestId, getAllByTestId } = await render(<SimulationBlock content={LEVER} />);

    expect(getByTestId("simulation-beam", HIDDEN)).toBeTruthy();
    expect(getByTestId("simulation-pivot", HIDDEN)).toBeTruthy();
    expect(getAllByTestId("simulation-vector-label", HIDDEN).length).toBe(2);
    // The arm that was the question is the one drawn in the answer's colour.
    expect(getAllByTestId("simulation-vector-result", HIDDEN).length).toBe(1);
    expect(getAllByTestId("simulation-vector-force", HIDDEN).length).toBe(1);
  });

  it("offers no Play on a scene with nothing to play", async () => {
    // A button that does nothing when pressed is worse than no button.
    const { queryByTestId } = await render(<SimulationBlock content={LEVER} />);

    expect(queryByTestId("simulation-control")).toBeNull();
  });

  it("shows each stated force with the magnitude the solver computed", async () => {
    // The labels carry the numbers, so the picture cannot disagree with the
    // answer pill above it.
    //
    // Read off the accessibility label rather than with getByText: canvas
    // text is not a text node a test — or a screen reader — can reach, which
    // is why the scene's description carries every stated label.
    const { getByLabelText } = await render(<SimulationBlock content={FREE_BODY} />);

    expect(getByLabelText(/T = 59\.05 N/)).toBeTruthy();
    expect(getByLabelText(/W = 49\.05 N/)).toBeTruthy();
  });

  it("draws the block a free-body diagram is about", async () => {
    const { getByLabelText, getByTestId, queryByTestId } = await render(
      <SimulationBlock content={FREE_BODY} />,
    );

    expect(getByTestId("simulation-body", HIDDEN)).toBeTruthy();
    expect(getByTestId("simulation-body-label", HIDDEN)).toBeTruthy();
    expect(getByLabelText(/5 kg/)).toBeTruthy();
    // Still figure: no beam, and nothing to play.
    expect(queryByTestId("simulation-beam", HIDDEN)).toBeNull();
    expect(queryByTestId("simulation-control")).toBeNull();
  });

  it("describes resuming as playing the physics animation", async () => {
    const { getByLabelText } = await render(<SimulationBlock content={PROJECTILE} />);

    await fireEvent.press(getByLabelText("rich.simulation_pause_a11y"));
    expect(getByLabelText("rich.simulation_play_a11y")).toBeTruthy();
  });

  it("sizes wide scenes short and square scenes full, with the title always above", async () => {
    // One title style in one place: never laid over the canvas, and the same
    // role and colour as a graph's title.
    const projectile = await render(<SimulationBlock content={PROJECTILE} />);
    const projectileStyle = projectile.getByTestId("simulation-canvas").props.style;
    expect(projectileStyle.height).toBeLessThan(240);
    const projectileTitle = StyleSheet.flatten(projectile.getByText("Projectile").props.style);
    expect(projectileTitle.position).toBeUndefined();

    const orbit = await render(<SimulationBlock content={ORBIT} />);
    const orbitStyle = orbit.getByTestId("simulation-canvas").props.style;
    expect(orbitStyle.height).toBe(240);
    const orbitTitle = StyleSheet.flatten(orbit.getByText("Circular Motion").props.style);
    expect(orbitTitle).toEqual(projectileTitle);
  });

  it("keeps its figure under Reduce Motion", async () => {
    // Nothing was moving, so there is nothing to take away.
    mockUseReduceMotion.mockReturnValue(true);
    const { getByTestId, getAllByTestId } = await render(<SimulationBlock content={LEVER} />);

    expect(getByTestId("simulation-beam", HIDDEN)).toBeTruthy();
    expect(getAllByTestId("simulation-vector-label", HIDDEN).length).toBe(2);
  });
});

describe("SimulationBlock: Reduce Motion and playback", () => {
  it("waits for the Reduce Motion setting before moving", async () => {
    // Starting on a guess and stopping a few frames later is the flash of
    // motion a Reduce Motion user asked not to see.
    mockUseReduceMotion.mockReturnValue(null);
    const view = await render(<SimulationBlock content={PROJECTILE} />);
    expect(view.getByTestId("simulation-play-symbol").props.name).toBe("play");

    mockUseReduceMotion.mockReturnValue(false);
    await view.rerender(<SimulationBlock content={PROJECTILE} />);
    expect(view.getByTestId("simulation-stop-symbol").props.name).toBe("pause");
  });

  it("never autoplays under Reduce Motion but plays when the user asks", async () => {
    mockUseReduceMotion.mockReturnValue(true);
    const { getByLabelText, getByTestId } = await render(<SimulationBlock content={PROJECTILE} />);

    expect(getByTestId("simulation-play-symbol").props.name).toBe("play");
    await fireEvent.press(getByLabelText("rich.simulation_play_a11y"));
    expect(getByTestId("simulation-stop-symbol").props.name).toBe("pause");
  });

  it("rewinds and stops when a recycled cell is given another scene", async () => {
    // FlashList can hand this instance new content; the old scene's playing
    // state must not carry over to it.
    mockUseReduceMotion.mockReturnValue(true);
    const view = await render(<SimulationBlock content={PROJECTILE} />);
    await fireEvent.press(view.getByLabelText("rich.simulation_play_a11y"));
    expect(view.getByTestId("simulation-stop-symbol")).toBeTruthy();

    await view.rerender(<SimulationBlock content={ORBIT} />);
    expect(view.getByTestId("simulation-play-symbol").props.name).toBe("play");
  });

  it("uses the kit's 44 pt control rather than a hand-made circle", async () => {
    const { getByTestId } = await render(<SimulationBlock content={PROJECTILE} />);
    const style = StyleSheet.flatten(getByTestId("simulation-control").props.style);
    expect(style.minWidth).toBe(Space.minTouch);
    expect(style.minHeight).toBe(Space.minTouch);
  });
});

describe("SimulationBlock: accessibility", () => {
  it("is one image with a description built from the scene", async () => {
    const { getByRole } = await render(<SimulationBlock content={FREE_BODY} />);
    const image = getByRole("image");

    expect(image.props.accessibilityLabel).toMatch(/^Free-Body Diagram\. 5 kg\./);
    expect(image.props.accessibilityLabel).toContain("T = 59.05 N, W = 49.05 N");
  });

  it("names the arrows a moving scene derives", async () => {
    const { getByRole } = await render(<SimulationBlock content={PROJECTILE} />);
    expect(getByRole("image").props.accessibilityLabel).toMatch(/^Projectile\./);
  });

  it("keeps its test markers away from screen readers", async () => {
    // A screen reader could otherwise land on invisible one-pixel dots.
    const { queryByTestId, getByTestId } = await render(<SimulationBlock content={PROJECTILE} />);

    expect(queryByTestId("simulation-body")).toBeNull();
    expect(getByTestId("simulation-body", HIDDEN)).toBeTruthy();
  });
});

describe("LazySimulationBlock placeholder", () => {
  it("is as tall as the scene it stands in for", async () => {
    // A wide scene is short, and only a moving one carries the play button.
    const screenWidth = Dimensions.get("window").width;
    const projectile = await render(<SimulationBlock content={PROJECTILE} />);
    const canvas = projectile.getByTestId("simulation-canvas").props.style.height;
    const title = 22;
    expect(simulationPlaceholderHeight(PROJECTILE, screenWidth)).toBe(
      Space.xs * 2 + title + canvas + Space.xxs + Space.minTouch,
    );

    const lever = await render(<SimulationBlock content={LEVER} />);
    const leverCanvas = lever.getByTestId("simulation-canvas").props.style.height;
    expect(simulationPlaceholderHeight(LEVER, screenWidth)).toBe(Space.xs * 2 + title + leverCanvas);
  });
});

// --- v2 scenes -------------------------------------------------------------

const SWING = Array.from({ length: 61 }, (_, i) => {
  const theta = ((15 * Math.PI) / 180) * Math.cos((2 * Math.PI * i) / 60);
  return [Math.sin(theta), -Math.cos(theta)];
});

const PENDULUM = JSON.stringify({
  type: "pendulum",
  title: "Pendulum",
  bodies: [{ label: "0.5 kg", radius: 0.06, path: SWING, role: "primary" }],
  x_min: -0.6,
  x_max: 0.6,
  y_min: -1.2,
  y_max: 0.15,
  arrows: ["velocity", "gravity"],
  tethers: [{ anchor: [0, 0], body: 0 }],
  angles: [{ vertex: [0, 0], start_deg: -90, end_deg: -75, label: "15°", arrow: false, role: "given" }],
  arrow_labels: { velocity: "v", gravity: "mg" },
  alt: "A 1 m pendulum swinging 15° either side; period 2.01 s.",
  title_key: "pendulum",
});

const FALL = Array.from({ length: 50 }, (_, i) => Math.min(0.5 * 2.45 * (i * 0.025) ** 2, 1.5));
const ATWOOD = JSON.stringify({
  type: "free_body",
  title: "Atwood Machine",
  bodies: [
    { label: "5 kg", radius: 0.25, path: FALL.map((s) => [-0.5, 2.2 - s]), shape: "box" },
    { label: "3 kg", radius: 0.21, path: FALL.map((s) => [0.5, 0.7 + s]), role: "secondary", shape: "box" },
  ],
  x_min: -1.6,
  x_max: 1.6,
  y_min: 0,
  y_max: 3.9,
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
});

const TABLE = JSON.stringify({
  type: "projectile_motion",
  title: "Projectile",
  bodies: [
    {
      radius: 0.05,
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
});

const SATELLITE = JSON.stringify({
  ...JSON.parse(ORBIT),
  central_body: { radius: 4.6, label: "Earth" },
  arrow_labels: { centripetal: "g" },
});

const TORQUE = JSON.stringify({
  ...JSON.parse(LEVER),
  angles: [
    { vertex: [0, 0], start_deg: 60, end_deg: -30, label: "τ = 15 N·m", arrow: true, role: "result" },
  ],
});

const BUOYANCY = JSON.stringify({
  type: "free_body",
  title: "Free-Body Diagram",
  bodies: [{ radius: 0.35, path: [[0, -0.8], [0, -0.8]], shape: "box" }],
  x_min: -2.2,
  x_max: 2.2,
  y_min: -2.2,
  y_max: 0.8,
  vectors: [{ anchor: [0, -0.8], dx: 0, dy: 19.6, label: "F_b = 19.6 N", role: "result" }],
  solids: [{ rect: [-2, -2, 2, 0], kind: "fluid", label: "water" }],
  title_key: "buoyancy",
});

describe("SimulationBlock: v2 scenes", () => {
  it("hangs a pendulum's bob on its string from a fixed support, with its angle", async () => {
    const { getByTestId, getAllByTestId } = await render(<SimulationBlock content={PENDULUM} />);

    expect(getAllByTestId("simulation-body", HIDDEN)).toHaveLength(1);
    expect(getByTestId("simulation-tether", HIDDEN)).toBeTruthy();
    expect(getByTestId("simulation-support", HIDDEN)).toBeTruthy();
    expect(getByTestId("simulation-angle-given", HIDDEN)).toBeTruthy();
    expect(getByTestId("simulation-angle-label", HIDDEN)).toBeTruthy();
    expect(getByTestId("simulation-arrow-label-velocity", HIDDEN)).toBeTruthy();
    expect(getByTestId("simulation-arrow-label-gravity", HIDDEN)).toBeTruthy();
    // It swings, so it plays.
    expect(getByTestId("simulation-control")).toBeTruthy();
  });

  it("says the server's sentence for the picture, and shows the title it can", async () => {
    // No translation is loaded here, so the key falls back to the English title.
    const { getByRole, getByText } = await render(<SimulationBlock content={PENDULUM} />);

    expect(getByRole("image").props.accessibilityLabel).toBe(
      "A 1 m pendulum swinging 15° either side; period 2.01 s.",
    );
    expect(getByText("Pendulum")).toBeTruthy();
  });

  it("keeps the generated description when there is no sentence", async () => {
    const noAlt = JSON.stringify({ ...JSON.parse(PENDULUM), alt: undefined });
    const { getByRole } = await render(<SimulationBlock content={noAlt} />);

    expect(getByRole("image").props.accessibilityLabel).toMatch(/^Pendulum\. 0\.5 kg\./);
  });

  it("runs an Atwood machine's ropes over its pulley, with tensions riding on the masses", async () => {
    const { getByTestId, getAllByTestId, queryByTestId } = await render(
      <SimulationBlock content={ATWOOD} />,
    );

    expect(getByTestId("simulation-pulley", HIDDEN)).toBeTruthy();
    expect(getAllByTestId("simulation-tether", HIDDEN)).toHaveLength(2);
    // Both ropes leave the wheel's rim: it is their support.
    expect(queryByTestId("simulation-support", HIDDEN)).toBeNull();
    expect(getAllByTestId("simulation-body-box", HIDDEN)).toHaveLength(2);
    expect(getAllByTestId("simulation-vector-attached", HIDDEN)).toHaveLength(4);
    expect(getAllByTestId("simulation-vector-result", HIDDEN)).toHaveLength(2);
  });

  it("strobes a ball off a table, and keeps the strobe under Reduce Motion", async () => {
    mockUseReduceMotion.mockReturnValue(true);
    const { getByTestId, getAllByTestId } = await render(<SimulationBlock content={TABLE} />);

    expect(getByTestId("simulation-static", HIDDEN)).toBeTruthy();
    // The still frame still shows the motion: six faint copies along the path.
    expect(getAllByTestId("simulation-strobe", HIDDEN)).toHaveLength(6);
    expect(getByTestId("simulation-solid-solid", HIDDEN)).toBeTruthy();
    expect(getByTestId("simulation-ground", HIDDEN)).toBeTruthy();
  });

  it("draws the planet an orbit goes round", async () => {
    const { getByTestId } = await render(<SimulationBlock content={SATELLITE} />);

    expect(getByTestId("simulation-planet", HIDDEN)).toBeTruthy();
    expect(getByTestId("simulation-arrow-label-centripetal", HIDDEN)).toBeTruthy();
  });

  it("draws a moment as a curved arrow in the answer's colour", async () => {
    const { getByTestId } = await render(<SimulationBlock content={TORQUE} />);

    expect(getByTestId("simulation-angle-result", HIDDEN)).toBeTruthy();
    expect(getByTestId("simulation-angle-arrow", HIDDEN)).toBeTruthy();
  });

  it("puts a block under water", async () => {
    const { getByTestId, queryByTestId } = await render(<SimulationBlock content={BUOYANCY} />);

    expect(getByTestId("simulation-solid-fluid", HIDDEN)).toBeTruthy();
    expect(getByTestId("simulation-body-box", HIDDEN)).toBeTruthy();
    expect(queryByTestId("simulation-control")).toBeNull();
  });

  it("shows its fallback for a malformed new field rather than half a scene", async () => {
    const bad = JSON.stringify({ ...JSON.parse(PENDULUM), strobe: 40 });
    const { queryByTestId } = await render(<SimulationBlock content={bad} />);

    expect(queryByTestId("simulation-body", HIDDEN)).toBeNull();
    expect(queryByTestId("simulation-canvas")).toBeNull();
  });

  it("stands in with a placeholder as tall as each new scene", async () => {
    const screenWidth = Dimensions.get("window").width;
    const title = 22;
    for (const content of [PENDULUM, ATWOOD, TABLE, SATELLITE]) {
      const view = await render(<SimulationBlock content={content} />);
      const canvas = view.getByTestId("simulation-canvas").props.style.height;
      expect(simulationPlaceholderHeight(content, screenWidth)).toBe(
        Space.xs * 2 + title + canvas + Space.xxs + Space.minTouch,
      );
    }
    for (const content of [TORQUE, BUOYANCY]) {
      const view = await render(<SimulationBlock content={content} />);
      const canvas = view.getByTestId("simulation-canvas").props.style.height;
      expect(simulationPlaceholderHeight(content, screenWidth)).toBe(Space.xs * 2 + title + canvas);
    }
  });
});
