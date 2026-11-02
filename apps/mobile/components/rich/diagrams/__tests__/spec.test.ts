/**
 * Reading a whole diagram fence (the common scene fields plus the kind's own
 * object) and the height the chat list reserves before the renderer loads.
 */
import { FIGURE_TITLE_HEIGHT, figureWidth } from "@/components/rich/figure";
import {
  PHYSICS_DIAGRAM_FALLBACK_HEIGHT,
  physicsDiagramPlaceholderHeight,
} from "@/components/rich/diagrams/placeholder";
import { parsePhysicsDiagram, physicsDiagramCanvasHeight } from "@/components/rich/diagrams/spec";
import { diagramTextWidth, measureDiagramText } from "@/components/rich/diagrams/textWidth";
import { layoutCircuit } from "@/lib/physics/circuit";
import { worldViewportHeight } from "@/lib/physics/optics";
import { Space } from "@/lib/space";

const CIRCUIT = {
  type: "circuit",
  title: "Circuit",
  bodies: [],
  x_min: 0,
  x_max: 10,
  y_min: 0,
  y_max: 10,
  vectors: [],
  centre: null,
  beam: null,
  alt: "A 12 V battery driving 4 Ω in series with 3 Ω and 6 Ω in parallel; total 6 Ω, 2 A.",
  title_key: "circuit",
  circuit: {
    source: { kind: "battery", label: "12 V" },
    load: {
      series: [
        { part: "resistor", label: "R₁ = 4 Ω", detail: "8 V" },
        {
          parallel: [
            { part: "resistor", label: "R₂ = 3 Ω", detail: "1.33 A" },
            { part: "resistor", label: "R₃ = 6 Ω", detail: "0.667 A" },
          ],
          label: "2 Ω",
        },
      ],
      label: "R = 6 Ω",
      role: "result",
    },
    current: "2 A",
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
    { vertex: [0, 0], start_deg: 90, end_deg: 120, label: "30°", arrow: false, role: "given" },
    { vertex: [0, 0], start_deg: -90, end_deg: -70.53, label: "19.5°", arrow: false, role: "result" },
  ],
  title_key: "refraction",
  optics: {
    element: "interface",
    focal: null,
    object: null,
    image: null,
    rays: [{ points: [[-1, 1.7320508075688774], [0, 0], [0.6666666666666666, -1.8856180831641267]], virtual: false }],
    media: ["air", "glass n = 1.5"],
  },
};

const X = Array.from({ length: 81 }, (_, i) => i * 0.015);
const STANDING = {
  type: "wave",
  title: "Standing Wave",
  x_min: -0.05,
  x_max: 1.25,
  y_min: -0.12,
  y_max: 0.12,
  vectors: [{ anchor: [0, -0.09], dx: 0.8, dy: 0, label: "λ = 0.8 m", role: "measure" }],
  title_key: "standing_wave",
  wave: {
    x: X,
    frames: Array.from({ length: 24 }, (_, f) =>
      X.map((x) => 0.05 * Math.cos((2 * Math.PI * f) / 24) * Math.sin((2 * Math.PI * x) / 0.8)),
    ),
    nodes: [0, 0.4, 0.8, 1.2],
    antinodes: [0.2, 0.6, 1.0],
    ends: ["fixed", "fixed"],
  },
};

const fence = (value: unknown) => JSON.stringify(value);

describe("parsePhysicsDiagram", () => {
  it("reads each kind with its common fields", () => {
    const circuit = parsePhysicsDiagram(fence(CIRCUIT), "circuit");
    expect(circuit).toMatchObject({ kind: "circuit", title: "Circuit", titleKey: "circuit" });
    expect(circuit?.alt).toContain("12 V battery");
    const rays = parsePhysicsDiagram(fence(REFRACTION), "rays");
    expect(rays).toMatchObject({ kind: "rays", bounds: { xMin: -2.2, xMax: 2.2, yMin: -2.2, yMax: 2.2 } });
    expect(rays?.kind === "rays" && rays.angles).toHaveLength(2);
    const wave = parsePhysicsDiagram(fence(STANDING), "wave");
    expect(wave?.kind === "wave" && wave.measures[0].label).toBe("λ = 0.8 m");
  });

  it("keeps a title key this build does not know: it only picks a translation", () => {
    expect(parsePhysicsDiagram(fence({ ...CIRCUIT, title_key: "kirchhoff_loop" }), "circuit")?.titleKey).toBe(
      "kirchhoff_loop",
    );
  });

  it.each([
    ["the wrong type", fence({ ...CIRCUIT, type: "wave" }), "circuit"],
    ["a scene that also carries optics", fence({ ...CIRCUIT, optics: REFRACTION.optics }), "circuit"],
    ["a ray diagram with no optics", fence({ ...REFRACTION, optics: null }), "rays"],
    ["a title over 64 characters", fence({ ...CIRCUIT, title: "t".repeat(65) }), "circuit"],
    ["an alt over 300 characters", fence({ ...CIRCUIT, alt: "a".repeat(301) }), "circuit"],
    ["a title key that is not a key", fence({ ...CIRCUIT, title_key: "Circuit <b>" }), "circuit"],
    ["unordered bounds", fence({ ...REFRACTION, x_min: 3 }), "rays"],
    ["a malformed vector", fence({ ...STANDING, vectors: [{ anchor: [0, 0], dx: 0, dy: 0 }] }), "wave"],
    ["a malformed angle", fence({ ...REFRACTION, angles: [{ vertex: [0, 0], start_deg: 1, end_deg: 1 }] }), "rays"],
    ["a malformed circuit", fence({ ...CIRCUIT, circuit: { ...CIRCUIT.circuit, load: { part: "diode" } } }), "circuit"],
    ["a malformed wave", fence({ ...STANDING, wave: { ...STANDING.wave, ends: ["fixed"] } }), "wave"],
    ["bad JSON", "{ not json", "circuit"],
    ["an array", "[]", "circuit"],
  ] as const)("refuses %s", (_name, content, kind) => {
    expect(parsePhysicsDiagram(content, kind)).toBeNull();
  });
});

describe("physicsDiagramPlaceholderHeight", () => {
  const frame = Space.xs * 2 + FIGURE_TITLE_HEIGHT;

  it("reserves the circuit's laid-out height", () => {
    const width = figureWidth(390);
    const spec = parsePhysicsDiagram(fence(CIRCUIT), "circuit");
    if (spec?.kind !== "circuit") throw new Error("expected a circuit");
    const canvas = physicsDiagramCanvasHeight(spec, width);
    expect(canvas).toBe(layoutCircuit(spec.circuit, width, measureDiagramText).height);
    expect(physicsDiagramPlaceholderHeight(fence(CIRCUIT), 390)).toBe(frame + canvas);
  });

  it("reserves a ray diagram's canvas, with no control under it", () => {
    const height = worldViewportHeight({ xMin: -2.2, xMax: 2.2, yMin: -2.2, yMax: 2.2 }, figureWidth(390));
    expect(physicsDiagramPlaceholderHeight(fence(REFRACTION), 390)).toBe(frame + height);
  });

  it("adds the play button under a wave", () => {
    const height = worldViewportHeight({ xMin: -0.05, xMax: 1.25, yMin: -0.12, yMax: 0.12 }, figureWidth(390));
    expect(physicsDiagramPlaceholderHeight(fence(STANDING), 390)).toBe(
      frame + height + Space.xxs + Space.minTouch,
    );
  });

  it("shrinks a circuit's reservation on a narrow phone, as its layout scales", () => {
    const wide = {
      ...CIRCUIT,
      circuit: {
        source: { label: "230 V" },
        load: {
          series: Array.from({ length: 6 }, (_, i) => ({ part: "resistor", label: `R${i} = 1000 Ω`, detail: `${i} mA` })),
        },
      },
    };
    expect(physicsDiagramPlaceholderHeight(fence(wide), 320)).toBeLessThan(
      physicsDiagramPlaceholderHeight(fence(wide), 430),
    );
  });

  it("reserves the fallback line for a fence it cannot read", () => {
    expect(physicsDiagramPlaceholderHeight("{ nope", 390)).toBe(PHYSICS_DIAGRAM_FALLBACK_HEIGHT);
    expect(physicsDiagramPlaceholderHeight(fence({ ...CIRCUIT, circuit: null }), 390)).toBe(
      PHYSICS_DIAGRAM_FALLBACK_HEIGHT,
    );
  });
});

describe("diagramTextWidth", () => {
  it("adds Source Sans 3 advances, physics symbols included", () => {
    // R 569, ₁ 367, space 200, = 497, space 200, 4 497, space 200, Ω 678.
    expect(diagramTextWidth("R₁ = 4 Ω", 1000)).toBe(3208);
    expect(diagramTextWidth("λ", 12)).toBeCloseTo(5.928, 6);
    expect(diagramTextWidth("", 12)).toBe(0);
    // A character the table lacks still takes room.
    expect(diagramTextWidth("ж", 1000)).toBeGreaterThan(0);
  });
});
