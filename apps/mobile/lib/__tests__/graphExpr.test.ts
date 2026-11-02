import {
  evalGraphExpr,
  formatSeriesExpr,
  inequalityFillPoints,
  normalizePlotExpr,
  parseGraphExpr,
  parseGraphRelation,
  sampleGraphExpr,
} from "@/lib/math/graphExpr";

import fixture from "../../../../docs/fixtures/graph_expr_cases.json";

type GraphCase = {
  expr: string;
  fence?: string;
  x?: number[];
  y?: (number | null)[];
  refused?: boolean;
  phone_gap?: string;
};
type Contract = { variable: string; cases: GraphCase[] };

describe("graphExpr", () => {
  it("evaluates 4x^2-5x-12 at the vertex and origin", () => {
    const node = parseGraphExpr("4x^2-5x-12");
    expect(node).not.toBeNull();
    expect(evalGraphExpr(node!, 0)).toBe(-12);
    expect(evalGraphExpr(node!, 0.625)).toBeCloseTo(-13.5625, 6);
  });

  it("strips y= and a trailing =0 so a quadratic equation plots as a U", () => {
    expect(normalizePlotExpr("y = 4x^2-5x-12")).toBe("4x^2-5x-12");
    expect(normalizePlotExpr("4x^2-5x-12=0")).toBe("4x^2-5x-12");
    const node = parseGraphExpr("4x^2-5x-12=0");
    expect(evalGraphExpr(node!, 0)).toBe(-12);
  });

  it("leaves an ellipse as a relation (not y=f(x))", () => {
    expect(parseGraphExpr("x^2 + y^2 = 1")).toBeNull();
  });

  it("handles implicit multiplication, powers, and unary minus", () => {
    const node = parseGraphExpr("-x^2 + 2(x+1)");
    expect(evalGraphExpr(node!, 3)).toBe(-9 + 8);
    expect(evalGraphExpr(parseGraphExpr("2^3^2")!, 0)).toBe(512);
  });

  it("reads a bare log as base 10, as the server does", () => {
    expect(evalGraphExpr(parseGraphExpr("log(x)")!, 100)).toBeCloseTo(2);
    expect(evalGraphExpr(parseGraphExpr("lg(x)")!, 1000)).toBeCloseTo(3);
    expect(evalGraphExpr(parseGraphExpr("ln(x)")!, Math.E)).toBeCloseTo(1);
  });

  it("samples sin and splits 1/x at the pole", () => {
    expect(evalGraphExpr(parseGraphExpr("sin(0)")!, 0)).toBeCloseTo(0);
    const sampled = sampleGraphExpr(parseGraphExpr("1/x")!, -2, 2, 40);
    expect(sampled.segments?.length).toBeGreaterThanOrEqual(2);
  });

  it("rejects unknown identifiers and empty input", () => {
    expect(parseGraphExpr("hello")).toBeNull();
    expect(parseGraphExpr("")).toBeNull();
  });

  it("evaluates x^2/3 as (x^2)/3", () => {
    expect(evalGraphExpr(parseGraphExpr("x^2/3")!, 3)).toBe(3);
  });

  it("parses y < 2x and y > x^2 as relations", () => {
    const below = parseGraphRelation("y < 2x");
    expect(below?.cmp).toBe("<");
    expect(evalGraphExpr(below!.node, 1)).toBe(2);
    const above = parseGraphRelation("y > x^2");
    expect(above?.cmp).toBe(">");
    expect(evalGraphExpr(above!.node, 2)).toBe(4);
    expect(parseGraphRelation("y <= 2x")?.cmp).toBe("<=");
    expect(parseGraphRelation("y ≥ 2x")?.cmp).toBe(">=");
    expect(parseGraphRelation("x^2")?.cmp).toBe("=");
  });

  it("seeds the editor with a full relation so = can become <", () => {
    expect(formatSeriesExpr("x**2")).toBe("y = x^2");
    expect(formatSeriesExpr("y < 2x")).toBe("y < 2x");
    expect(formatSeriesExpr("4x^2-5x-12=0")).toBe("y = 4x^2-5x-12");
    expect(formatSeriesExpr("x^2 + y^2 = 1")).toBe("x^2 + y^2 = 1");
  });

  it("closes an inequality fill against the matching y edge", () => {
    const curve: [number, number][] = [
      [0, 0],
      [2, 4],
    ];
    expect(inequalityFillPoints(curve, -3, 5, "<")).toEqual([
      [0, 0],
      [2, 4],
      [2, -3],
      [0, -3],
    ]);
    expect(inequalityFillPoints(curve, -3, 5, ">")).toEqual([
      [0, 0],
      [2, 4],
      [2, 5],
      [0, 5],
    ]);
    expect(inequalityFillPoints(curve, -3, 5, "=")).toEqual([]);
  });
});

/**
 * docs/fixtures/graph_expr_cases.json is shared with the API test
 * (app/tests/modules/math/test_math_graph_expr_contract.py), which recomputes
 * every y with SymPy through the server's own reading of the expression, and
 * regenerates `fence`: the text the server writes into the graph fence. The
 * phone re-reads that text to resample on zoom, and a typed expression in the
 * series editor, so both must land on the same curve.
 */
describe("graph expression contract", () => {
  const contract: Contract = fixture;
  // Within 1e-9, relative once |y| is above 1.
  const TOLERANCE = 1e-9;
  const read = contract.cases.filter((c) => !c.refused && c.phone_gap == null);
  const refused = contract.cases.filter((c) => c.refused);
  const gaps = contract.cases.filter((c) => c.phone_gap != null);
  const fenced = contract.cases.filter((c) => c.fence != null);

  /** NaN and the infinities draw no point, which the fixture writes as null. */
  const phoneY = (expr: string, x: number): number | null | "unread" => {
    const node = parseGraphExpr(expr, contract.variable);
    if (node == null) return "unread";
    const y = evalGraphExpr(node, x);
    return Number.isFinite(y) ? y : null;
  };

  const agrees = (got: number | null | "unread", want: number | null): boolean => {
    if (want == null) return got === null;
    if (typeof got !== "number") return false;
    return Math.abs(got - want) <= TOLERANCE * Math.max(1, Math.abs(want));
  };

  const misses = (text: string, c: GraphCase) =>
    (c.x ?? []).flatMap((x, i) => {
      const want = c.y?.[i] ?? null;
      const got = phoneY(text, x);
      return agrees(got, want) ? [] : [{ x, phone: got, sympy: want }];
    });

  it.each(read.map((c) => [c.expr, c] as const))("%s samples as SymPy does", (_expr, c) => {
    expect(misses(c.expr, c)).toEqual([]);
  });

  it.each(fenced.map((c) => [c.expr, c.fence, c] as const))(
    "%s arrives in the graph fence as %s, which samples as SymPy does",
    (_expr, fence, c) => {
      expect(misses(fence ?? "", c)).toEqual([]);
    },
  );

  it("has a fence for every expression the server reads", () => {
    expect(contract.cases.filter((c) => !c.refused && c.fence == null)).toEqual([]);
  });

  it.each(refused.map((c) => [c.expr] as const))("%s is refused, as on the server", (expr) => {
    expect(parseGraphExpr(expr, contract.variable)).toBeNull();
  });

  for (const c of gaps) {
    it.skip(`${c.expr} parity skipped, known phone gap: ${c.phone_gap}`, () => {});
  }

  it.each(gaps.map((c) => [c.expr] as const))(
    "%s is a known phone gap in typed text: refused rather than drawn differently",
    (expr) => {
      // The fence carries the server's bracketed reading instead (checked above).
      // When the phone learns this raw form, delete its phone_gap line so parity is checked.
      expect(parseGraphExpr(expr, contract.variable)).toBeNull();
    },
  );
});
