/**
 * The circuit diagram's reading and layout, as pure functions: what the
 * schematic is allowed to draw, and where each symbol, wire and label goes.
 */
import { circuitLabelBoxes } from "@/lib/physics/__tests__/support/circuitLabels";
import {
  circuitDepth,
  circuitPartCount,
  describeCircuit,
  layoutCircuit,
  MAX_CIRCUIT_PARTS,
  parseCircuitSpec,
  PART_HALF_SPAN,
  type CircuitLayout,
  type CircuitSpec,
} from "@/lib/physics/circuit";

/** Roughly Source Sans at 12 pt; the real table lives with the renderer. */
const measure = (text: string) => [...text].length * 6;

const R = (label: string, detail?: string, extra: Record<string, unknown> = {}) => ({
  part: "resistor",
  label,
  ...(detail ? { detail } : {}),
  ...extra,
});

/** The server's example: 4 Ω in series with 3 Ω and 6 Ω in parallel. */
const EXAMPLE = {
  source: { kind: "battery", label: "12 V" },
  load: {
    series: [
      R("R₁ = 4 Ω", "8 V"),
      { parallel: [R("R₂ = 3 Ω", "1.33 A"), R("R₃ = 6 Ω", "0.667 A")], label: "2 Ω" },
    ],
    label: "R = 6 Ω",
    role: "result",
  },
  current: "2 A",
};

function parse(raw: unknown): CircuitSpec {
  const spec = parseCircuitSpec(raw);
  if (!spec) throw new Error("expected the circuit to parse");
  return spec;
}

function boxesOverlap(a: number[], b: number[]): boolean {
  return a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];
}

function expectNoLabelOverlap(layout: CircuitLayout) {
  const boxes = circuitLabelBoxes(layout);
  for (let i = 0; i < boxes.length; i += 1) {
    for (let j = i + 1; j < boxes.length; j += 1) {
      expect(boxesOverlap(boxes[i], boxes[j])).toBe(false);
    }
  }
}

describe("parseCircuitSpec", () => {
  it("reads the server's example", () => {
    const spec = parse(EXAMPLE);
    expect(spec.source).toEqual({ kind: "battery", label: "12 V" });
    expect(spec.current).toBe("2 A");
    expect(spec.load.kind).toBe("series");
    expect(spec.load.role).toBe("result");
    expect(circuitPartCount(spec.load)).toBe(3);
    expect(circuitDepth(spec.load)).toBe(2);
  });

  it("treats null optional fields as absent and defaults the source to a battery", () => {
    const spec = parse({
      source: { label: null },
      load: { part: "bulb", label: null, detail: null, series: null, parallel: null },
      current: null,
    });
    expect(spec.source.kind).toBe("battery");
    expect(spec.load).toEqual({ kind: "part", part: "bulb", label: undefined, detail: undefined, role: "given" });
    expect(spec.current).toBeUndefined();
  });

  it("accepts every part the schematic can draw", () => {
    for (const part of Object.keys(PART_HALF_SPAN)) {
      expect(parseCircuitSpec({ source: { kind: "ac" }, load: { part } })).not.toBeNull();
    }
  });

  it("accepts ten parts nested three groups deep", () => {
    const ten = {
      source: {},
      load: {
        series: [
          { parallel: [{ series: [R("a"), R("b")] }, { series: [R("c"), R("d")] }] },
          { parallel: [{ series: [R("e"), R("f")] }, { series: [R("g"), R("h")] }] },
          R("i"),
          R("j"),
        ],
      },
    };
    const spec = parse(ten);
    expect(circuitPartCount(spec.load)).toBe(MAX_CIRCUIT_PARTS);
    expect(circuitDepth(spec.load)).toBe(3);
  });

  it.each([
    ["an unknown part", { source: {}, load: { part: "diode" } }],
    ["an unknown source", { source: { kind: "solar" }, load: { part: "bulb" } }],
    ["no source", { load: { part: "bulb" } }],
    ["no load", { source: {} }],
    ["a node that is both a part and a group", { source: {}, load: { part: "bulb", series: [R("a"), R("b")] } }],
    ["a node that is neither", { source: {}, load: { label: "x" } }],
    ["a series of one", { source: {}, load: { series: [R("a")] } }],
    ["a series of seven", { source: {}, load: { series: Array.from({ length: 7 }, (_, i) => R(`${i}`)) } }],
    ["a parallel group of five", { source: {}, load: { parallel: Array.from({ length: 5 }, (_, i) => R(`${i}`)) } }],
    ["a label over 24 characters", { source: {}, load: R("x".repeat(25)) }],
    ["a detail that is not text", { source: {}, load: { part: "bulb", detail: 6 } }],
    ["an unknown role", { source: {}, load: { part: "bulb", role: "answer" } }],
    ["a current label over 24 characters", { source: {}, load: { part: "bulb" }, current: "1".repeat(25) }],
    [
      "eleven parts",
      {
        source: {},
        load: {
          series: [
            { parallel: [R("a"), R("b"), R("c"), R("d")] },
            { parallel: [R("e"), R("f"), R("g"), R("h")] },
            R("i"),
            { series: [R("j"), R("k")] },
          ],
        },
      },
    ],
    [
      "groups nested four deep",
      {
        source: {},
        load: { series: [R("a"), { parallel: [R("b"), { series: [R("c"), { parallel: [R("d"), R("e")] }] }] }] },
      },
    ],
    ["not an object", "resistor"],
  ])("refuses %s", (_name, raw) => {
    expect(parseCircuitSpec(raw)).toBeNull();
  });

  it("counts a 24-character label by code points, as the server does", () => {
    // Subscripts and Ω are one code point each.
    const label = "R₁₂₃ = 4 Ω ".padEnd(24, "x");
    expect([...label].length).toBe(24);
    expect(parseCircuitSpec({ source: {}, load: R(label) })).not.toBeNull();
  });
});

describe("layoutCircuit", () => {
  it("runs a series group left to right on one wire", () => {
    const spec = parse({ source: { label: "6 V" }, load: { series: [R("R₁", "2 V"), R("R₂", "4 V"), R("R₃")] } });
    const layout = layoutCircuit(spec, 400, measure);
    const xs = layout.parts.map((part) => part.cx);
    expect(xs).toEqual([...xs].sort((a, b) => a - b));
    expect(new Set(layout.parts.map((part) => part.cy)).size).toBe(1);
    // A series has no tees.
    expect(layout.junctions).toEqual([]);
    // Labels above their symbol, details below.
    for (const part of layout.parts) {
      expect(part.label!.y).toBeLessThan(part.cy);
      if (part.detail) expect(part.detail.y).toBeGreaterThan(part.cy);
    }
  });

  it("stacks parallel branches between two rails, each on its own wire", () => {
    const spec = parse({
      source: {},
      load: { parallel: [R("R₁", "1 A"), R("R₂", "2 A"), R("R₃", "3 A")] },
    });
    const layout = layoutCircuit(spec, 400, measure);
    const ys = layout.parts.map((part) => part.cy);
    expect(ys[0]).toBeLessThan(ys[1]);
    expect(ys[1]).toBeLessThan(ys[2]);
    // The branches share a column between the rails.
    expect(new Set(layout.parts.map((part) => part.cx)).size).toBe(1);
    // Two vertical rails span from the first branch to the last.
    const rails = layout.wires.filter((w) => w.x1 === w.x2 && w.y1 === ys[0] && w.y2 === ys[2]);
    expect(rails).toHaveLength(2);
    // Tees at every branch but the last, on both rails.
    expect(layout.junctions).toHaveLength(4);
    // The first branch is on the top wire of the loop, so the loop stays straight.
    const top = Math.min(...layout.wires.map((w) => Math.min(w.y1, w.y2)));
    expect(ys[0]).toBe(top);
  });

  it("lays a series inside a parallel branch inside a series", () => {
    const spec = parse({
      source: {},
      load: {
        series: [
          R("R₁"),
          { parallel: [{ series: [R("R₂"), { part: "inductor", label: "L" }], label: "3 Ω" }, R("R₃")], label: "2 Ω" },
        ],
      },
    });
    const layout = layoutCircuit(spec, 400, measure);
    const [r1, r2, inductor, r3] = layout.parts;
    expect(r2.cy).toBe(r1.cy);
    expect(inductor.cy).toBe(r2.cy);
    expect(inductor.cx).toBeGreaterThan(r2.cx);
    expect(r3.cy).toBeGreaterThan(r2.cy);
    expect(r3.cx).toBeGreaterThan(r1.cx);
    // Two brackets, the inner one (3 Ω) under the outer one (2 Ω).
    const [inner, outer] = layout.groups;
    expect(inner.text.text).toBe("3 Ω");
    expect(outer.text.text).toBe("2 Ω");
    expect(outer.y).toBeLessThan(inner.y);
    expect(outer.x1).toBeLessThanOrEqual(inner.x1);
    expect(outer.x2).toBeGreaterThanOrEqual(inner.x2);
    expectNoLabelOverlap(layout);
  });

  it("puts a group's bracket above every label of its members", () => {
    const layout = layoutCircuit(parse(EXAMPLE), 400, measure);
    const root = layout.groups.find((group) => group.text.text === "R = 6 Ω")!;
    expect(root.role).toBe("result");
    for (const part of layout.parts) expect(root.y).toBeLessThan(part.label!.y - 9);
    expectNoLabelOverlap(layout);
  });

  it("joins a group's label and detail on its bracket", () => {
    const spec = parse({ source: {}, load: { parallel: [R("a"), R("b")], label: "2 Ω", detail: "6 V" } });
    expect(layoutCircuit(spec, 400, measure).groups[0].text.text).toBe("2 Ω · 6 V");
  });

  it("draws the source on the left edge with the current arrow above it, pointing up", () => {
    const layout = layoutCircuit(parse(EXAMPLE), 400, measure);
    const { source, current } = layout;
    expect(source.kind).toBe("battery");
    for (const part of layout.parts) expect(part.cx).toBeGreaterThan(source.cx);
    expect(current).not.toBeNull();
    expect(current!.x).toBe(source.cx);
    expect(current!.tipY).toBeLessThan(current!.tailY);
    expect(current!.tailY).toBeLessThan(source.cy);
    // Both gutter labels end left of the source.
    expect(source.label!.x + source.label!.width).toBeLessThan(source.cx);
    expect(current!.label.x + current!.label.width).toBeLessThan(source.cx);
  });

  it("closes the loop: every wire end meets another wire, a symbol or the source", () => {
    const layout = layoutCircuit(parse(EXAMPLE), 400, measure);
    const ends = layout.wires.flatMap((w) => [
      [w.x1, w.y1],
      [w.x2, w.y2],
    ]);
    const key = (x: number, y: number) => `${x.toFixed(3)},${y.toFixed(3)}`;
    const counts = new Map<string, number>();
    for (const [x, y] of ends) counts.set(key(x, y), (counts.get(key(x, y)) ?? 0) + 1);
    const symbolEnds = new Set(
      layout.parts.flatMap((p) => [key(p.cx - PART_HALF_SPAN[p.part], p.cy), key(p.cx + PART_HALF_SPAN[p.part], p.cy)]),
    );
    const sourceEnds = new Set([key(layout.source.cx, layout.source.cy - 10), key(layout.source.cx, layout.source.cy + 10)]);
    for (const [point, count] of counts) {
      if (count === 1) expect(symbolEnds.has(point) || sourceEnds.has(point)).toBe(true);
    }
  });

  it("keeps a narrow circuit at full size, centred", () => {
    const spec = parse({ source: {}, load: R("R") });
    const layout = layoutCircuit(spec, 400, measure);
    expect(layout.scale).toBe(1);
    expect(layout.offsetX).toBeCloseTo((400 - layout.naturalWidth) / 2);
    expect(layout.height).toBe(Math.ceil(layout.naturalHeight));
  });

  it("scales a wide circuit down to fit the canvas, never past it", () => {
    const wide = parse({
      source: { label: "230 V" },
      load: { series: Array.from({ length: 6 }, (_, i) => R(`R${i} = 1000 Ω`, `${i}.5 mA`)) },
      current: "12.5 mA",
    });
    for (const width of [272, 312, 360]) {
      const layout = layoutCircuit(wide, width, measure);
      expect(layout.scale).toBeLessThan(1);
      expect(layout.naturalWidth * layout.scale).toBeLessThanOrEqual(width + 1e-9);
      expect(layout.offsetX).toBeGreaterThanOrEqual(0);
      expect(layout.height).toBe(Math.ceil(layout.naturalHeight * layout.scale));
      expectNoLabelOverlap(layout);
    }
  });

  it("keeps everything inside the drawing it scales", () => {
    const layout = layoutCircuit(parse(EXAMPLE), 312, measure);
    const xs = [
      ...layout.wires.flatMap((w) => [w.x1, w.x2]),
      ...circuitLabelBoxes(layout).flatMap(([l, , r]) => [l, r]),
    ];
    const ys = [
      ...layout.wires.flatMap((w) => [w.y1, w.y2]),
      ...circuitLabelBoxes(layout).flatMap(([, t, , b]) => [t, b]),
    ];
    expect(Math.min(...xs)).toBeGreaterThanOrEqual(0);
    expect(Math.max(...xs)).toBeLessThanOrEqual(layout.naturalWidth);
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(0);
    expect(Math.max(...ys)).toBeLessThanOrEqual(layout.naturalHeight);
  });

  it("gives the same layout for the same input: the placeholder can trust it", () => {
    expect(layoutCircuit(parse(EXAMPLE), 312, measure)).toEqual(layoutCircuit(parse(EXAMPLE), 312, measure));
  });
});

describe("describeCircuit", () => {
  const t = (key: string, options?: Record<string, unknown>) =>
    options ? `${key}(${Object.entries(options).map(([k, v]) => `${k}=${v}`).join(";")})` : key;

  it("names the source, each part and how the groups connect", () => {
    const text = describeCircuit(parse(EXAMPLE), t);
    expect(text).toContain("rich.diagram_a11y_circuit(source=rich.diagram_source_battery 12 V");
    expect(text).toContain("rich.diagram_part_resistor R₁ = 4 Ω (8 V)");
    expect(text).toContain("rich.diagram_a11y_parallel(list=");
    expect(text).toContain("rich.diagram_a11y_current(value=2 A)");
    expect(text.endsWith(".")).toBe(true);
  });
});
