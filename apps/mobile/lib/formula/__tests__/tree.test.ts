/**
 * docs/fixtures/formula_tree_cases.json is written by the API (expression.py's `to_tree`)
 * and read here: the phone's evaluator must give the server's number for every case.
 */
import fixture from "../../../../../docs/fixtures/formula_tree_cases.json";
import { compileFormula, evaluateFormula } from "@/lib/formula/tree";

type Case = { id: string; tree: unknown; values: Record<string, number>; expected: number | null };

const CASES = (fixture as unknown as { cases: Case[] }).cases;

function closeTo(actual: number, expected: number): boolean {
  const scale = Math.max(1, Math.abs(expected));
  return Math.abs(actual - expected) <= 1e-9 * scale;
}

describe("formula tree parity with the server", () => {
  it("has cases to check", () => {
    expect(CASES.length).toBeGreaterThan(5);
  });

  it.each(CASES.map((c) => [c.id, c] as const))("%s", (_id, c) => {
    const formula = compileFormula(c.tree, Object.keys(c.values));
    expect(formula).not.toBeNull();
    const value = evaluateFormula(formula!, c.values);
    if (c.expected === null) {
      expect(value).toBeNull();
    } else {
      expect(value).not.toBeNull();
      expect(closeTo(value!, c.expected)).toBe(true);
    }
  });
});

describe("compileFormula refuses anything outside the closed language", () => {
  const x = { v: "x" };

  it.each([
    ["an unknown operation", { op: "%", a: [x, { n: 2 }] }],
    ["an unknown function", { fn: "eval", a: [x] }],
    ["a name that is not a control", { v: "y" }],
    ["a string number", { n: "2" }],
    ["an infinite number", { n: Number.POSITIVE_INFINITY }],
    ["the wrong number of operands", { op: "+", a: [x] }],
    ["a function with two operands", { fn: "log", a: [x, x] }],
    ["an unknown comparison", { op: "if", a: [{ cmp: "!=", a: [x, x] }, x, x] }],
    ["a condition with no test", { op: "if", a: [x, x, x] }],
    ["text instead of a tree", "x + 1"],
    ["an array", [x]],
    ["null", null],
  ])("%s", (_label, tree) => {
    expect(compileFormula(tree, ["x"])).toBeNull();
  });

  it("refuses a tree deeper than 32 levels", () => {
    let tree: unknown = { v: "x" };
    for (let i = 0; i < 32; i += 1) tree = { op: "neg", a: [tree] };
    expect(compileFormula(tree, ["x"])).toBeNull();
    let shallow: unknown = { v: "x" };
    for (let i = 0; i < 30; i += 1) shallow = { op: "neg", a: [shallow] };
    expect(compileFormula(shallow, ["x"])).not.toBeNull();
  });

  it("refuses a tree of more than 512 nodes", () => {
    const leaves = Array.from({ length: 300 }, () => ({ v: "x" }));
    const balanced = (nodes: unknown[]): unknown =>
      nodes.length === 1
        ? nodes[0]
        : {
            op: "+",
            a: [
              balanced(nodes.slice(0, nodes.length / 2)),
              balanced(nodes.slice(nodes.length / 2)),
            ],
          };
    expect(compileFormula(balanced(leaves), ["x"])).toBeNull();
    expect(compileFormula(balanced(leaves.slice(0, 200)), ["x"])).not.toBeNull();
  });
});

describe("evaluateFormula", () => {
  const ratio = compileFormula({ op: "/", a: [{ v: "a" }, { v: "b" }] }, ["a", "b"])!;

  it("gives no number for a missing value", () => {
    expect(evaluateFormula(ratio, { a: 1 })).toBeNull();
  });

  it("gives no number for a result too large to hold", () => {
    const big = compileFormula({ op: "^", a: [{ n: 10 }, { v: "x" }] }, ["x"])!;
    expect(evaluateFormula(big, { x: 400 })).toBeNull();
    expect(evaluateFormula(big, { x: 3 })).toBe(1000);
  });

  it("knows pi", () => {
    const pi = compileFormula({ v: "pi" }, [])!;
    expect(evaluateFormula(pi, {})).toBe(Math.PI);
  });
});
