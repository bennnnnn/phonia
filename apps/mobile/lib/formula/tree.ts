/**
 * The server's checked formula, as a JSON tree, evaluated on the phone (docs/money.md).
 *
 * The server owns every formula: it picks it, checks it and sends it as a tree, never as text.
 * The phone only walks that tree with the closed list of operations below, so a slider can
 * redraw a card's numbers as it moves. Nothing is parsed from a string and nothing is solved.
 * A tree is checked once (`compileFormula`): an unknown operation or name, or one too deep or
 * too large, is refused before any value is computed. The server's twin is
 * `apps/api/app/services/law_binding/expression.py`; `docs/fixtures/formula_tree_cases.json`
 * holds both to one result.
 */

import { isJsonRecord } from "@/lib/jsonFence";

const MAX_DEPTH = 32;
const MAX_NODES = 512;

const FUNCTIONS = {
  sqrt: Math.sqrt,
  sin: Math.sin,
  cos: Math.cos,
  tan: Math.tan,
  asin: Math.asin,
  acos: Math.acos,
  atan: Math.atan,
  exp: Math.exp,
  log: Math.log,
  abs: Math.abs,
} as const;

type FunctionName = keyof typeof FUNCTIONS;
type BinaryOp = "+" | "-" | "*" | "/" | "^";
type Comparison = ">" | ">=" | "<" | "<=" | "==";

const BINARY: ReadonlySet<string> = new Set<BinaryOp>(["+", "-", "*", "/", "^"]);
const COMPARISONS: ReadonlySet<string> = new Set<Comparison>([">", ">=", "<", "<=", "=="]);

type Node =
  | { kind: "number"; value: number }
  | { kind: "name"; name: string }
  | { kind: "binary"; op: BinaryOp; left: Node; right: Node }
  | { kind: "negate"; operand: Node }
  | { kind: "call"; fn: FunctionName; operand: Node }
  | { kind: "if"; cmp: Comparison; left: Node; right: Node; then: Node; otherwise: Node };

/** A tree that passed the check, ready to evaluate any number of times. */
export type Formula = { readonly root: Node };

type Budget = { nodes: number };

function args(raw: Record<string, unknown>, count: number): unknown[] | null {
  const list = raw.a;
  return Array.isArray(list) && list.length === count ? list : null;
}

function compileNode(
  raw: unknown,
  names: ReadonlySet<string>,
  depth: number,
  budget: Budget,
): Node | null {
  budget.nodes += 1;
  if (depth > MAX_DEPTH || budget.nodes > MAX_NODES || !isJsonRecord(raw)) return null;
  if ("n" in raw) {
    return typeof raw.n === "number" && Number.isFinite(raw.n)
      ? { kind: "number", value: raw.n }
      : null;
  }
  if ("v" in raw) {
    const name = raw.v;
    return typeof name === "string" && (name === "pi" || names.has(name))
      ? { kind: "name", name }
      : null;
  }
  if ("fn" in raw) {
    const fn = raw.fn;
    const list = args(raw, 1);
    if (typeof fn !== "string" || !(fn in FUNCTIONS) || !list) return null;
    const operand = compileNode(list[0], names, depth + 1, budget);
    return operand ? { kind: "call", fn: fn as FunctionName, operand } : null;
  }
  const op = raw.op;
  if (op === "neg") {
    const list = args(raw, 1);
    const operand = list ? compileNode(list[0], names, depth + 1, budget) : null;
    return operand ? { kind: "negate", operand } : null;
  }
  if (op === "if") {
    const list = args(raw, 3);
    if (!list) return null;
    const test = list[0];
    const sides = isJsonRecord(test) ? args(test, 2) : null;
    if (!isJsonRecord(test) || typeof test.cmp !== "string" || !COMPARISONS.has(test.cmp) || !sides) {
      return null;
    }
    const left = compileNode(sides[0], names, depth + 2, budget);
    const right = compileNode(sides[1], names, depth + 2, budget);
    const then = compileNode(list[1], names, depth + 1, budget);
    const otherwise = compileNode(list[2], names, depth + 1, budget);
    if (!left || !right || !then || !otherwise) return null;
    return { kind: "if", cmp: test.cmp as Comparison, left, right, then, otherwise };
  }
  if (typeof op === "string" && BINARY.has(op)) {
    const list = args(raw, 2);
    if (!list) return null;
    const left = compileNode(list[0], names, depth + 1, budget);
    const right = compileNode(list[1], names, depth + 1, budget);
    return left && right ? { kind: "binary", op: op as BinaryOp, left, right } : null;
  }
  return null;
}

/**
 * The checked formula, or null when the tree uses anything outside the closed language:
 * an unknown operation or function, a name that is not one of `names` (or `pi`), a
 * non-finite number, or more than 32 levels or 512 nodes.
 */
export function compileFormula(raw: unknown, names: readonly string[]): Formula | null {
  const root = compileNode(raw, new Set(names), 1, { nodes: 0 });
  return root ? { root } : null;
}

function compare(cmp: Comparison, left: number, right: number): boolean {
  switch (cmp) {
    case ">":
      return left > right;
    case ">=":
      return left >= right;
    case "<":
      return left < right;
    case "<=":
      return left <= right;
    case "==":
      return left === right;
  }
}

function binary(op: BinaryOp, left: number, right: number): number {
  switch (op) {
    case "+":
      return left + right;
    case "-":
      return left - right;
    case "*":
      return left * right;
    case "/":
      return right === 0 ? Number.NaN : left / right;
    case "^":
      return left ** right;
  }
}

/** NaN stands for "no number" inside the walk; `evaluateFormula` turns it into null. */
function walk(node: Node, values: Readonly<Record<string, number>>): number {
  switch (node.kind) {
    case "number":
      return node.value;
    case "name":
      return node.name === "pi" ? Math.PI : (values[node.name] ?? Number.NaN);
    case "negate":
      return -walk(node.operand, values);
    case "call": {
      const operand = walk(node.operand, values);
      return Number.isFinite(operand) ? FUNCTIONS[node.fn](operand) : Number.NaN;
    }
    case "if": {
      const left = walk(node.left, values);
      const right = walk(node.right, values);
      if (!Number.isFinite(left) || !Number.isFinite(right)) return Number.NaN;
      return walk(compare(node.cmp, left, right) ? node.then : node.otherwise, values);
    }
    case "binary": {
      const left = walk(node.left, values);
      const right = walk(node.right, values);
      if (!Number.isFinite(left) || !Number.isFinite(right)) return Number.NaN;
      return binary(node.op, left, right);
    }
  }
}

/**
 * The formula's value for these values, or null when it gives no number: a division by
 * zero, a negative number to a fractional power, a function outside its domain, a missing
 * value, or a result too large to hold.
 */
export function evaluateFormula(
  formula: Formula,
  values: Readonly<Record<string, number>>,
): number | null {
  const value = walk(formula.root, values);
  return Number.isFinite(value) ? value : null;
}
