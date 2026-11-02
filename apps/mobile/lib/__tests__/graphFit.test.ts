import { interactiveFunctionBounds } from "@/lib/math/graphFit";
import { type GraphSpec } from "@/lib/math/graphSpec";
import { type GraphView } from "@/lib/math/graphViewport";

/** A phone card's plot: 336 × 220 less the axis pad. */
const CARD_ASPECT = (336 - 32) / (220 - 32);

/** The server's samples: 96 points across −10…10, rounded to four places. */
function samples(f: (x: number) => number): [number, number][] {
  return Array.from({ length: 96 }, (_, i) => {
    const x = Number((-10 + (20 * i) / 95).toFixed(4));
    return [x, Number(f(x).toFixed(4))] as [number, number];
  }).filter(([, y]) => Number.isFinite(y));
}

function fn(expr: string, f: (x: number) => number, extra: Partial<GraphSpec> = {}): GraphSpec {
  return { type: "function", expr, points: samples(f), x_min: -10, x_max: 10, ...extra } as GraphSpec;
}

function shows(view: GraphView, [x, y]: [number, number]): boolean {
  return x > view.xMin && x < view.xMax && y > view.yMin && y < view.yMax;
}

describe("the window a graph card opens on", () => {
  it.each([
    ["the vertex and roots of y = x² − 4", fn("x^2 - 4", (x) => x * x - 4), [[0, -4], [-2, 0], [2, 0]]],
    ["the cap of y = −x² + 6", fn("6 - x^2", (x) => 6 - x * x), [[0, 6]]],
    ["both intercepts of y = 2x + 5", fn("2x + 5", (x) => 2 * x + 5), [[0, 5], [-2.5, 0]]],
    ["the line y = 7", fn("7", () => 7), [[0, 7]]],
    ["the vertex of y = (x − 8)²", fn("(x - 8)^2", (x) => (x - 8) ** 2), [[8, 0]]],
    ["the turning points of y = x³ − 100x", fn("x^3 - 100x", (x) => x ** 3 - 100 * x), [[5.77, -384.9], [-5.77, 384.9]]],
    ["the peaks of y = 5 sin x", fn("5sin(x)", (x) => 5 * Math.sin(x)), [[Math.PI / 2, 5], [-Math.PI / 2, -5]]],
    ["both crossings of y = x² and y = 2x + 8", fn("x^2", (x) => x * x, {
      expr2: "2x + 8",
      points2: samples((x) => 2 * x + 8),
    }), [[-2, 4], [4, 16]]],
  ] as const)("shows %s", (_name, spec, features) => {
    const view = interactiveFunctionBounds(spec, CARD_ASPECT);
    for (const point of features) expect(shows(view, point as [number, number])).toBe(true);
  });

  it("does not shrink y = (x − 8)² to a needle for its far y-intercept", () => {
    const view = interactiveFunctionBounds(fn("(x - 8)^2", (x) => (x - 8) ** 2), CARD_ASPECT);
    expect(view.yMax - view.yMin).toBeLessThan(20);
  });

  it("shows a vertical line or a point drawn off to one side", () => {
    const line = interactiveFunctionBounds(
      { type: "vertical", expr: "x = 8", x: 8, points: [[8, -10], [8, 10]], y_min: -10, y_max: 10 },
      CARD_ASPECT,
    );
    expect(line.xMax).toBeGreaterThan(8.5);
    const point = interactiveFunctionBounds(
      { type: "function", expr: "(8, 3)", points: [[8, 3]], x_min: 3, x_max: 13 },
      CARD_ASPECT,
    );
    expect(shows(point, [8, 3])).toBe(true);
  });

  it("draws the whole of a circle, still round", () => {
    const loop = Array.from({ length: 97 }, (_, i) => {
      const t = (2 * Math.PI * i) / 96;
      return [Number((5 * Math.cos(t)).toFixed(4)), Number((5 * Math.sin(t)).toFixed(4))] as [number, number];
    });
    const view = interactiveFunctionBounds(
      { type: "function", expr: "x**2 + y**2 = 25", points: loop, x_min: -6, x_max: 6, y_min: -6, y_max: 6 },
      CARD_ASPECT,
    );
    for (const point of [[5, 0], [-5, 0], [0, 5], [0, -5]] as const) {
      expect(shows(view, point as unknown as [number, number])).toBe(true);
    }
    expect((view.xMax - view.xMin) / (view.yMax - view.yMin)).toBeCloseTo(CARD_ASPECT, 6);
  });

  it.each([
    ["y = x²", fn("x^2", (x) => x * x)],
    ["y = tan x", fn("tan(x)", Math.tan)],
    ["y = eˣ, whose tail rounds to 0", fn("e^x", Math.exp)],
    // The server left this pole joined; the card's own samples split it.
    ["y = 1/(x − 2) + 3", fn("3 + 1/(x - 2)", (x) => 3 + 1 / (x - 2))],
  ] as const)("keeps the school window for %s", (_name, spec) => {
    const view = interactiveFunctionBounds(spec, CARD_ASPECT);
    expect(view.xMin).toBe(-6);
    expect(view.xMax).toBe(6);
    expect(view.yMax).toBeCloseTo(6 / CARD_ASPECT, 9);
  });
});
