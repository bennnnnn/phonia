import { formatAxisNumber, graphAxisTicks } from "@/lib/math/graphBlock";
import { parseGraphSpec, type InequalityGraphSpec } from "@/lib/math/graphSpec";
import { clipInequalityRegion } from "@/lib/math/inequalityGraph";

const base: InequalityGraphSpec = {
  type: "inequality", expr: "y < 2*x", a: -2, b: 1, c: 0, comparator: "<",
  x_min: -10, x_max: 10, y_min: -10, y_max: 10, points: [],
};

describe("inequality graph parsing", () => {
  it("accepts the verified half-plane without sampled function points", () => {
    expect(parseGraphSpec(JSON.stringify(base))).toEqual({ ...base, title: base.expr });
  });

  it("defaults omitted bounds but preserves an explicit viewport", () => {
    const { x_min: _xMin, x_max: _xMax, y_min: _yMin, y_max: _yMax, ...relation } = base;
    expect(parseGraphSpec(JSON.stringify(relation))).toMatchObject({ x_min: -10, x_max: 10, y_min: -10, y_max: 10 });
    expect(parseGraphSpec(JSON.stringify({ ...base, x_min: 2, x_max: 4, y_min: 5, y_max: 8 })))
      .toMatchObject({ x_min: 2, x_max: 4, y_min: 5, y_max: 8 });
  });

  it.each([
    { a: 0, b: 0 }, { a: "-2" }, { b: null }, { c: null },
    { comparator: "=" }, { comparator: "<>" }, { expr: "" }, { expr: "x".repeat(257) },
    { x_min: 10, x_max: -10 }, { y_min: 3, y_max: 3 }, { x_min: null },
    { x_max: "10" }, { y_max: Infinity }, { x_min: -1e308, x_max: 1e308 },
  ])("rejects malformed or unrepresentable graph data %j", (patch) => {
    expect(parseGraphSpec(JSON.stringify({ ...base, ...patch }))).toBeNull();
  });

  it("does not coerce missing coefficients into a different relation", () => {
    const { c: _c, ...missing } = base;
    expect(parseGraphSpec(JSON.stringify(missing))).toBeNull();
  });
});

describe("half-plane clipping", () => {
  it("shades below y=2x for y<2x and clips the boundary to the viewport", () => {
    const shape = clipInequalityRegion(base)!;
    expect(shape.boundary).toEqual([[-5, -10], [5, 10]]);
    expect(shape.region).toEqual([[-5, -10], [10, -10], [10, 10], [5, 10]]);
  });

  it.each(["<", "<=", ">", ">="] as const)("shades the correct side for %s", (comparator) => {
    const shape = clipInequalityRegion({ ...base, comparator })!;
    for (const [x, y] of shape.region) {
      const signed = -2 * x + y;
      expect(comparator.startsWith("<") ? signed <= 1e-9 : signed >= -1e-9).toBe(true);
    }
    const center = shape.region.reduce(([x, y], point) => [x + point[0], y + point[1]], [0, 0]);
    expect(comparator.startsWith("<") ? center[1] < 2 * center[0] : center[1] > 2 * center[0]).toBe(true);
  });

  it("handles a vertical boundary without dividing by b", () => {
    const shape = clipInequalityRegion({ ...base, a: 1, b: 0, c: 2 })!;
    expect(shape.boundary).toEqual([[2, -10], [2, 10]]);
    expect(shape.region).toContainEqual([-10, -10]);
    expect(shape.region.every(([x]) => x <= 2)).toBe(true);
  });

  it("handles a horizontal boundary and negative coefficients", () => {
    const shape = clipInequalityRegion({ ...base, a: 0, b: -2, c: -6, comparator: ">=" })!;
    expect(shape.boundary[0][1]).toBeCloseTo(3);
    expect(shape.boundary[1][1]).toBeCloseTo(3);
    expect(shape.region.every(([, y]) => y <= 3 + 1e-9)).toBe(true);
    expect(shape.region).toContainEqual([-10, -10]);
  });

  it("keeps a boundary through two corners without duplicate endpoints", () => {
    const shape = clipInequalityRegion({ ...base, a: -1 })!;
    expect(shape.boundary).toEqual([[-10, -10], [10, 10]]);
    expect(shape.region).toHaveLength(3);
  });

  it("allows a completely shaded or unshaded viewport when the boundary is outside it", () => {
    const full = clipInequalityRegion({ ...base, a: 0, b: 1, c: 20 })!;
    const empty = clipInequalityRegion({ ...base, a: 0, b: 1, c: 20, comparator: ">" })!;
    expect(full.region).toHaveLength(4);
    expect(full.boundary).toEqual([]);
    expect(empty).toEqual({ region: [], boundary: [] });
  });

  it("draws an edge boundary without inventing a positive-area solution", () => {
    const shape = clipInequalityRegion({ ...base, a: 0, b: 1, c: -10 })!;
    expect(shape.region).toEqual([]);
    expect(shape.boundary).toEqual([[-10, -10], [10, -10]]);
  });

  it("preserves a boundary that touches just one viewport corner", () => {
    const shape = clipInequalityRegion({ ...base, a: 1, b: 1, c: 20, comparator: ">=" })!;
    expect(shape).toEqual({ region: [], boundary: [[10, 10]] });
  });

  it("uses exactly the supplied bounds, including an origin-free viewport", () => {
    const shape = clipInequalityRegion({ ...base, x_min: 2, x_max: 4, y_min: 5, y_max: 8 })!;
    expect(shape.region.length).toBeGreaterThanOrEqual(3);
    for (const [x, y] of [...shape.region, ...shape.boundary]) {
      expect(x).toBeGreaterThanOrEqual(2);
      expect(x).toBeLessThanOrEqual(4);
      expect(y).toBeGreaterThanOrEqual(5);
      expect(y).toBeLessThanOrEqual(8);
    }
  });

  it("rescales very large coefficients instead of overflowing their products", () => {
    expect(clipInequalityRegion({ ...base, a: -1e308, b: 1e308 }))
      .toEqual(clipInequalityRegion({ ...base, a: -1, b: 1 }));
  });

  it("does not let an irrelevant y range erase a very small vertical boundary", () => {
    const shape = clipInequalityRegion({ ...base, a: 1, b: 0, x_min: -1e-300, x_max: 1e-300, y_min: -1e300, y_max: 1e300 })!;
    expect(shape.boundary).toEqual([[0, -1e300], [0, 1e300]]);
    expect(shape.region).toHaveLength(4);
  });

  it("fails safely if floating-point precision erases the relation", () => {
    expect(clipInequalityRegion({ ...base, a: 1e308, b: Number.MIN_VALUE, x_min: -Number.MIN_VALUE, x_max: Number.MIN_VALUE, y_min: -1e308, y_max: 1e308 })).toBeNull();
  });

  it("keeps axis tick generation bounded for extreme finite intervals", () => {
    const ticks = graphAxisTicks(1e308, 1.0000000000000002e308);
    expect(ticks.length).toBeLessThanOrEqual(64);
    expect(ticks.every(Number.isFinite)).toBe(true);
  });

  it.each([[-0.1, 0.1], [2.1, 2.4]])("preserves distinct fractional ticks from %s to %s", (min, max) => {
    const ticks = graphAxisTicks(min, max, 7, true);
    const labels = ticks.map((tick) => formatAxisNumber(tick, true));
    expect(ticks.length).toBeGreaterThan(2);
    expect(ticks[0]).toBe(min);
    expect(ticks[ticks.length - 1]).toBe(max);
    expect(new Set(labels).size).toBe(ticks.length);
    expect(labels.map(Number)).toEqual(ticks);
  });
});
