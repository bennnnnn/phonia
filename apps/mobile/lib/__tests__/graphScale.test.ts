import {
  equalScaleGraphBounds,
  functionPlotBounds,
  graphBounds,
  mapGraphPoint,
  schoolViewBounds,
} from "@/lib/math/graphBlock";
import { interactiveFunctionBounds } from "@/lib/math/graphFit";

describe("equal graph units", () => {
  it.each([0.5, 1, 1.75, 2.5])("keeps the circle round at plot aspect %s", (aspect) => {
    const bounds = equalScaleGraphBounds({ xMin: -1, xMax: 1, yMin: -1, yMax: 1 }, aspect);
    const origin = mapGraphPoint(0, 0, bounds, 200 * aspect + 56, 256);
    const right = mapGraphPoint(1, 0, bounds, 200 * aspect + 56, 256);
    const top = mapGraphPoint(0, 1, bounds, 200 * aspect + 56, 256);
    expect(right.px - origin.px).toBeCloseTo(origin.py - top.py, 10);
  });

  it.each([
    { xMin: -1, xMax: 1, yMin: -1, yMax: 1 },
    { xMin: 2, xMax: 8, yMin: -9, yMax: -5 },
    { xMin: -0.1, xMax: 0.1, yMin: -0.4, yMax: 0.4 },
  ])("expands without losing the original chosen window: %j", (before) => {
    const after = equalScaleGraphBounds(before, 1.75);
    expect(after.xMin).toBeLessThanOrEqual(before.xMin);
    expect(after.xMax).toBeGreaterThanOrEqual(before.xMax);
    expect(after.yMin).toBeLessThanOrEqual(before.yMin);
    expect(after.yMax).toBeGreaterThanOrEqual(before.yMax);
    expect((after.xMin + after.xMax) / 2).toBeCloseTo((before.xMin + before.xMax) / 2);
    expect((after.yMin + after.yMax) / 2).toBeCloseTo((before.yMin + before.yMax) / 2);
  });

  it("preserves a genuine ellipse's 3:2 semi-axis ratio", () => {
    const bounds = equalScaleGraphBounds({ xMin: -3, xMax: 3, yMin: -2, yMax: 2 }, 1.75);
    const left = mapGraphPoint(-3, 0, bounds, 406, 256);
    const right = mapGraphPoint(3, 0, bounds, 406, 256);
    const top = mapGraphPoint(0, 2, bounds, 406, 256);
    const bottom = mapGraphPoint(0, -2, bounds, 406, 256);
    expect((right.px - left.px) / (bottom.py - top.py)).toBeCloseTo(1.5, 10);
  });

  it("retains the textbook parabola crop and the points in a comparison plot", () => {
    const parabola = equalScaleGraphBounds(schoolViewBounds({ xMin: -10, xMax: 10, yMin: 0, yMax: 100 }, 1.75), 1.75);
    expect(parabola.xMin).toBeLessThanOrEqual(-6);
    expect(parabola.xMax).toBeGreaterThanOrEqual(6);
    expect(parabola.yMin).toBe(-1);
    expect(parabola.yMax).toBe(6);
    const points: [number, number][] = [[-2, 4], [0, 0], [2, 4], [-2, -4]];
    const paired = equalScaleGraphBounds(schoolViewBounds(graphBounds(points), 1.75), 1.75);
    for (const [x, y] of points) {
      const { px, py } = mapGraphPoint(x, y, paired, 406, 256);
      expect(px).toBeGreaterThanOrEqual(28);
      expect(px).toBeLessThanOrEqual(378);
      expect(py).toBeGreaterThanOrEqual(28);
      expect(py).toBeLessThanOrEqual(228);
    }
  });

  it("keeps a shifted parabola vertex in the equal-scale window", () => {
    const bounds = equalScaleGraphBounds(
      schoolViewBounds({ xMin: -10, xMax: 10, yMin: -13.56, yMax: 338 }, 1.75),
      1.75,
    );
    expect(bounds.yMin).toBeLessThanOrEqual(-13.56);
    expect(bounds.yMax).toBeGreaterThan(0);
    const vertex = mapGraphPoint(0.625, -13.56, bounds, 406, 256);
    expect(vertex.py).toBeGreaterThanOrEqual(28);
    expect(vertex.py).toBeLessThanOrEqual(228);
  });

  it("does not flatten 4x²-5x-12 into a ±10 needle", () => {
    const points: [number, number][] = Array.from({ length: 97 }, (_, i) => {
      const x = -10 + (20 * i) / 96;
      return [x, 4 * x * x - 5 * x - 12];
    });
    const bounds = functionPlotBounds(points, undefined, 1.75);
    expect(bounds.xMin).toBeGreaterThanOrEqual(-4);
    expect(bounds.xMax).toBeLessThanOrEqual(6);
    expect(bounds.yMax).toBeGreaterThanOrEqual(25);
    for (const [x, y] of [
      [0.625, -13.56],
      [-1.22, 0],
      [2.47, 0],
    ] as const) {
      const { px, py } = mapGraphPoint(x, y, bounds, 406, 256);
      expect(px).toBeGreaterThanOrEqual(28);
      expect(px).toBeLessThanOrEqual(378);
      expect(py).toBeGreaterThanOrEqual(28);
      expect(py).toBeLessThanOrEqual(228);
    }
  });

  it("starts on an explicitly requested x-domain without making the graph rigid", () => {
    const points: [number, number][] = Array.from({ length: 101 }, (_, i) => {
      const x = -Math.PI + (2 * Math.PI * i) / 100;
      return [x, Math.tan(x)] as [number, number];
    }).filter(([, y]) => Number.isFinite(y));
    const bounds = interactiveFunctionBounds({
      type: "function",
      expr: "tan(x)",
      points,
      x_min: -Math.PI,
      x_max: Math.PI,
      domain_explicit: true,
    }, 1.75);
    expect(bounds.xMin).toBeCloseTo(-Math.PI, 12);
    expect(bounds.xMax).toBeCloseTo(Math.PI, 12);
    expect(bounds.yMax).toBeGreaterThan(bounds.yMin);
  });

  it("keeps the adaptive school window when no domain was requested", () => {
    const bounds = interactiveFunctionBounds({
      type: "function",
      expr: "x",
      points: [[0, 0], [1, 1]],
      x_min: 0,
      x_max: 1,
      domain_explicit: false,
    }, 1.75);
    expect(bounds.xMin).toBe(-6);
    expect(bounds.xMax).toBe(6);
  });

  it.each([0, -1, Number.NaN, Number.POSITIVE_INFINITY])("keeps valid bounds when aspect is invalid: %s", (aspect) => {
    const bounds = { xMin: -1, xMax: 1, yMin: -1, yMax: 1 };
    expect(equalScaleGraphBounds(bounds, aspect)).toBe(bounds);
  });

  it.each([
    { xMin: 0, xMax: 0, yMin: -1, yMax: 1 },
    { xMin: 0, xMax: 1, yMin: 0, yMax: 0 },
    { xMin: 0, xMax: 1, yMin: 0, yMax: Number.POSITIVE_INFINITY },
    { xMin: -1e308, xMax: 1e308, yMin: -1, yMax: 1 },
  ])("does not introduce new bounds for a degenerate or unrepresentable span: %j", (bounds) => {
    expect(equalScaleGraphBounds(bounds, 1.75)).toBe(bounds);
  });
});
