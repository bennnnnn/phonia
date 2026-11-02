/**
 * The circuit, ray and wave diagrams' render behaviour.
 *
 * Their layout is asserted as pure functions in `lib/physics/__tests__`. What
 * is left here is what only a render can show: each kind draws what its fence
 * names, the canvas is one image with a description, a malformed fence shows
 * the fallback line, and the wave plays by itself only when Reduce Motion is
 * off. Markers are hidden from screen readers, so every marker query passes
 * `HIDDEN`.
 */
import { fireEvent, render } from "@testing-library/react-native";

import { PhysicsDiagram } from "@/components/rich/diagrams/PhysicsDiagram";

const HIDDEN = { includeHiddenElements: true };

/** The OS setting: `null` while it is still being read. */
const mockUseReduceMotion = jest.fn<boolean | null, []>(() => false);
jest.mock("@/lib/motion", () => ({
  ...jest.requireActual("@/lib/motion"),
  useReduceMotion: () => mockUseReduceMotion() ?? false,
  useReduceMotionSetting: () => mockUseReduceMotion(),
}));

const CIRCUIT = {
  type: "circuit",
  title: "Circuit",
  title_key: "circuit",
  alt: "A 12 V battery driving 4 Ω in series with 3 Ω and 6 Ω in parallel.",
  circuit: {
    source: { kind: "battery", label: "12 V" },
    load: {
      series: [
        { part: "resistor", label: "R₁ = 4 Ω", detail: "8 V" },
        {
          parallel: [
            { part: "resistor", label: "R₂ = 3 Ω" },
            { part: "bulb", label: "L" },
          ],
          label: "2 Ω",
        },
        { part: "ammeter", detail: "2 A" },
      ],
      label: "R = 6 Ω",
      role: "result",
    },
    current: "2 A",
  },
};

const LENS = {
  type: "rays",
  title: "Ray Diagram",
  title_key: "lens",
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
    ],
  },
};

const REFRACTION = {
  type: "rays",
  title: "Refraction",
  x_min: -2.2,
  x_max: 2.2,
  y_min: -2.2,
  y_max: 2.2,
  angles: [
    { vertex: [0, 0], start_deg: 90, end_deg: 120, label: "30°" },
    { vertex: [0, 0], start_deg: -90, end_deg: -70.53, label: "19.5°", role: "result" },
  ],
  optics: {
    element: "interface",
    rays: [{ points: [[-1, 1.732], [0, 0], [0.667, -1.886]] }],
    media: ["air", "glass"],
  },
};

const X = Array.from({ length: 41 }, (_, i) => i * 0.03);
const STANDING = {
  type: "wave",
  title: "Standing Wave",
  x_min: -0.05,
  x_max: 1.25,
  y_min: -0.12,
  y_max: 0.12,
  vectors: [{ anchor: [0, -0.09], dx: 0.8, dy: 0, label: "λ = 0.8 m", role: "measure" }],
  wave: {
    x: X,
    frames: Array.from({ length: 12 }, (_, f) =>
      X.map((x) => 0.05 * Math.cos((2 * Math.PI * f) / 12) * Math.sin((2 * Math.PI * x) / 0.8)),
    ),
    nodes: [0, 0.4, 0.8, 1.2],
    antinodes: [0.2, 0.6, 1.0],
    ends: ["fixed", "fixed"],
  },
};

const TRAVELLING = {
  type: "wave",
  title: "Wave",
  x_min: 0,
  x_max: 6,
  y_min: -0.9,
  y_max: 0.9,
  wave: {
    x: Array.from({ length: 31 }, (_, i) => i * 0.2),
    frames: Array.from({ length: 8 }, (_, f) =>
      Array.from({ length: 31 }, (_, i) => 0.5 * Math.sin(2 * Math.PI * ((i * 0.2) / 1.5 - f / 8))),
    ),
  },
};

const content = (value: unknown) => JSON.stringify(value);

beforeEach(() => {
  mockUseReduceMotion.mockReturnValue(false);
});

describe("PhysicsDiagram: circuit", () => {
  it("draws the source, every part, each group's bracket and the current", async () => {
    const { getByTestId, getAllByTestId, queryByTestId } = await render(
      <PhysicsDiagram content={content(CIRCUIT)} kind="circuit" />,
    );
    expect(getByTestId("circuit-canvas")).toBeTruthy();
    expect(getByTestId("diagram-source-battery", HIDDEN)).toBeTruthy();
    expect(getAllByTestId("diagram-part-resistor", HIDDEN)).toHaveLength(2);
    expect(getByTestId("diagram-part-bulb", HIDDEN)).toBeTruthy();
    expect(getByTestId("diagram-part-ammeter", HIDDEN)).toBeTruthy();
    expect(getByTestId("diagram-group-result", HIDDEN)).toBeTruthy();
    expect(getByTestId("diagram-group", HIDDEN)).toBeTruthy();
    // One parallel group of two branches: a tee on each rail.
    expect(getAllByTestId("diagram-junction", HIDDEN)).toHaveLength(2);
    expect(getByTestId("diagram-current", HIDDEN)).toBeTruthy();
    // A schematic does not move, so it has no play button.
    expect(queryByTestId("wave-control")).toBeNull();
  });

  it("titles the figure and gives the canvas the fence's alt as one image", async () => {
    const { getByText, getByLabelText } = await render(
      <PhysicsDiagram content={content(CIRCUIT)} kind="circuit" />,
    );
    // No translation is loaded in tests, so the key falls back to the English title.
    expect(getByText("Circuit")).toBeTruthy();
    const image = getByLabelText(CIRCUIT.alt);
    expect(image.props.accessibilityRole).toBe("image");
  });

  it("describes a circuit itself when the fence has no alt", async () => {
    const { alt: _alt, ...withoutAlt } = CIRCUIT;
    const { getByRole } = await render(<PhysicsDiagram content={content(withoutAlt)} kind="circuit" />);
    const label = getByRole("image").props.accessibilityLabel as string;
    expect(label).toContain("rich.diagram_a11y_circuit");
  });

  it("draws an AC source and a group-free single part", async () => {
    const single = { ...CIRCUIT, circuit: { source: { kind: "ac" }, load: { part: "switch" } } };
    const { getByTestId, queryByTestId } = await render(
      <PhysicsDiagram content={content(single)} kind="circuit" />,
    );
    expect(getByTestId("diagram-source-ac", HIDDEN)).toBeTruthy();
    expect(getByTestId("diagram-part-switch", HIDDEN)).toBeTruthy();
    expect(queryByTestId("diagram-group", HIDDEN)).toBeNull();
    expect(queryByTestId("diagram-current", HIDDEN)).toBeNull();
  });
});

describe("PhysicsDiagram: rays", () => {
  it("draws the lens, both focal points, the object, its image and every ray", async () => {
    const { getByTestId, getAllByTestId, queryByTestId } = await render(
      <PhysicsDiagram content={content(LENS)} kind="rays" />,
    );
    expect(getByTestId("rays-canvas")).toBeTruthy();
    expect(getByTestId("diagram-element-converging_lens", HIDDEN)).toBeTruthy();
    expect(getAllByTestId("diagram-focus", HIDDEN)).toHaveLength(2);
    expect(getByTestId("diagram-object", HIDDEN)).toBeTruthy();
    expect(getByTestId("diagram-image", HIDDEN)).toBeTruthy();
    expect(getAllByTestId("diagram-ray", HIDDEN)).toHaveLength(2);
    expect(queryByTestId("diagram-ray-virtual", HIDDEN)).toBeNull();
  });

  it("dashes a virtual image and its construction rays", async () => {
    const diverging = {
      ...LENS,
      optics: {
        ...LENS.optics,
        element: "diverging_lens",
        image: { x: -6.67, height: 1.33, label: "image", virtual: true },
        rays: [...LENS.optics.rays, { points: [[0, 4], [-10, 0]], virtual: true }],
      },
    };
    const { getByTestId, getAllByTestId } = await render(
      <PhysicsDiagram content={content(diverging)} kind="rays" />,
    );
    expect(getByTestId("diagram-element-diverging_lens", HIDDEN)).toBeTruthy();
    expect(getByTestId("diagram-image-virtual", HIDDEN)).toBeTruthy();
    expect(getAllByTestId("diagram-ray-virtual", HIDDEN)).toHaveLength(1);
  });

  it("gives a mirror one focal point", async () => {
    const mirror = { ...LENS, optics: { ...LENS.optics, element: "concave_mirror" } };
    const { getByTestId, getAllByTestId } = await render(<PhysicsDiagram content={content(mirror)} kind="rays" />);
    expect(getByTestId("diagram-element-concave_mirror", HIDDEN)).toBeTruthy();
    expect(getAllByTestId("diagram-focus", HIDDEN)).toHaveLength(1);
  });

  it("draws an interface with its two media and its angles, the answer emphasised", async () => {
    const { getByTestId, getAllByTestId, queryByTestId } = await render(
      <PhysicsDiagram content={content(REFRACTION)} kind="rays" />,
    );
    expect(getByTestId("diagram-element-interface", HIDDEN)).toBeTruthy();
    expect(getAllByTestId("diagram-medium", HIDDEN)).toHaveLength(2);
    expect(getByTestId("diagram-angle", HIDDEN)).toBeTruthy();
    expect(getByTestId("diagram-angle-result", HIDDEN)).toBeTruthy();
    expect(queryByTestId("diagram-focus", HIDDEN)).toBeNull();
  });
});

describe("PhysicsDiagram: wave", () => {
  it("draws its nodes, antinodes, clamps and measure, and plays by itself", async () => {
    const { getByTestId, getAllByTestId, queryByTestId } = await render(
      <PhysicsDiagram content={content(STANDING)} kind="wave" />,
    );
    expect(getByTestId("wave-canvas")).toBeTruthy();
    expect(getAllByTestId("diagram-node", HIDDEN)).toHaveLength(4);
    expect(getAllByTestId("diagram-antinode", HIDDEN)).toHaveLength(3);
    expect(getAllByTestId("diagram-end-fixed", HIDDEN)).toHaveLength(2);
    expect(getByTestId("diagram-measure", HIDDEN)).toBeTruthy();
    expect(getByTestId("wave-stop-symbol").props.name).toBe("pause");
    // Moving, it needs no envelope: the motion shows its reach.
    expect(queryByTestId("diagram-envelope", HIDDEN)).toBeNull();
  });

  it("pauses and resumes from its button, showing the envelope while still", async () => {
    const { getByLabelText, getByTestId, queryByTestId } = await render(
      <PhysicsDiagram content={content(STANDING)} kind="wave" />,
    );
    await fireEvent.press(getByLabelText("rich.diagram_wave_pause_a11y"));
    expect(getByTestId("wave-play-symbol").props.name).toBe("play");
    expect(getByTestId("diagram-envelope", HIDDEN)).toBeTruthy();
    await fireEvent.press(getByLabelText("rich.diagram_wave_play_a11y"));
    expect(getByTestId("wave-stop-symbol").props.name).toBe("pause");
    expect(queryByTestId("diagram-envelope", HIDDEN)).toBeNull();
  });

  it("holds still under Reduce Motion, with the envelope and Play still offered", async () => {
    mockUseReduceMotion.mockReturnValue(true);
    const { getByTestId, queryByTestId } = await render(
      <PhysicsDiagram content={content(STANDING)} kind="wave" />,
    );
    expect(getByTestId("diagram-static", HIDDEN)).toBeTruthy();
    expect(getByTestId("diagram-envelope", HIDDEN)).toBeTruthy();
    expect(getByTestId("wave-control")).toBeTruthy();
    expect(getByTestId("wave-play-symbol").props.name).toBe("play");
    expect(queryByTestId("wave-stop-symbol")).toBeNull();
  });

  it("waits while the Reduce Motion setting is still unknown", async () => {
    mockUseReduceMotion.mockReturnValue(null);
    const { getByTestId } = await render(<PhysicsDiagram content={content(STANDING)} kind="wave" />);
    expect(getByTestId("wave-play-symbol").props.name).toBe("play");
  });

  it("never draws an envelope for a travelling wave", async () => {
    mockUseReduceMotion.mockReturnValue(true);
    const { queryByTestId } = await render(<PhysicsDiagram content={content(TRAVELLING)} kind="wave" />);
    expect(queryByTestId("diagram-envelope", HIDDEN)).toBeNull();
    expect(queryByTestId("diagram-node", HIDDEN)).toBeNull();
    expect(queryByTestId("diagram-end-fixed", HIDDEN)).toBeNull();
  });

  it("draws a pipe's ends", async () => {
    const pipe = { ...STANDING, wave: { ...STANDING.wave, ends: ["closed", "open"] } };
    const { getByTestId } = await render(<PhysicsDiagram content={content(pipe)} kind="wave" />);
    expect(getByTestId("diagram-end-closed", HIDDEN)).toBeTruthy();
    expect(getByTestId("diagram-end-open", HIDDEN)).toBeTruthy();
  });
});

describe("PhysicsDiagram: malformed fences", () => {
  it.each([
    ["bad JSON", "{ not json", "circuit"],
    ["an unknown part", content({ ...CIRCUIT, circuit: { source: {}, load: { part: "diode" } } }), "circuit"],
    ["a lens with no focal length", content({ ...LENS, optics: { ...LENS.optics, focal: null } }), "rays"],
    ["a frame with a missing sample", content({ ...TRAVELLING, wave: { ...TRAVELLING.wave, frames: [[0], [0]] } }), "wave"],
  ] as const)("shows the fallback line, not half a diagram, for %s", async (_name, raw, kind) => {
    const { getByText, queryByTestId } = await render(<PhysicsDiagram content={raw} kind={kind} />);
    expect(getByText("rich.simulation_error")).toBeTruthy();
    expect(queryByTestId(`${kind}-canvas`)).toBeNull();
    expect(queryByTestId("wave-control")).toBeNull();
  });
});
