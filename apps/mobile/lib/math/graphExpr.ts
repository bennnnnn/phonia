/**
 * Plot-only expression eval (not a solver). Whitelisted AST — no eval/Function.
 * Used so pinch-zoom and live edits can resample y=f(x) on device.
 * docs/fixtures/graph_expr_cases.json holds it to the server's SymPy reading.
 */

type GraphExprNode =
  | { t: "num"; v: number }
  | { t: "var" }
  | { t: "call"; name: string; arg: GraphExprNode }
  | { t: "unary"; arg: GraphExprNode }
  | { t: "bin"; op: "+" | "-" | "*" | "/" | "^"; l: GraphExprNode; r: GraphExprNode };

const FUNCS: Record<string, (n: number) => number> = {
  sin: Math.sin,
  cos: Math.cos,
  tan: Math.tan,
  asin: Math.asin,
  acos: Math.acos,
  atan: Math.atan,
  sinh: Math.sinh,
  cosh: Math.cosh,
  tanh: Math.tanh,
  sqrt: Math.sqrt,
  abs: Math.abs,
  exp: Math.exp,
  ln: Math.log,
  // School notation, as on the server: a bare log is base 10.
  log: Math.log10,
  lg: Math.log10,
  log10: Math.log10,
  floor: Math.floor,
  ceil: Math.ceil,
  round: Math.round,
};

const CONSTS: Record<string, number> = { pi: Math.PI, e: Math.E };

type Tok =
  | { k: "num"; v: number }
  | { k: "id"; v: string }
  | { k: "op"; v: string };

function preprocess(src: string): string {
  let s = "";
  for (let i = 0; i < src.length; i += 1) {
    const ch = src[i];
    if (ch === "²") {
      s += "^2";
      continue;
    }
    if (ch === "³") {
      s += "^3";
      continue;
    }
    if (ch === "×" || ch === "·") {
      s += "*";
      continue;
    }
    if (ch === "÷") {
      s += "/";
      continue;
    }
    if (ch === "−" || ch === "–") {
      s += "-";
      continue;
    }
    if (ch === "≤" || ch === "⩽") {
      s += "<=";
      continue;
    }
    if (ch === "≥" || ch === "⩾") {
      s += ">=";
      continue;
    }
    s += ch;
  }
  return s;
}

function skipSpaces(s: string, i: number): number {
  while (i < s.length && (s[i] === " " || s[i] === "\t")) i += 1;
  return i;
}

function isLetter(ch: string): boolean {
  return (ch >= "A" && ch <= "Z") || (ch >= "a" && ch <= "z");
}

function isIdentChar(ch: string): boolean {
  return isLetter(ch) || (ch >= "0" && ch <= "9") || ch === "_";
}

function hasIdentToken(s: string, name: string): boolean {
  const n = name.length;
  for (let i = 0; i < s.length; i += 1) {
    if (i + n > s.length) return false;
    if (s[i] !== name[0] && s[i].toLowerCase() !== name[0]) continue;
    if (i > 0 && isIdentChar(s[i - 1])) continue;
    let ok = true;
    for (let k = 0; k < n; k += 1) {
      if (s[i + k].toLowerCase() !== name[k]) {
        ok = false;
        break;
      }
    }
    if (!ok) continue;
    if (i + n < s.length && isIdentChar(s[i + n])) continue;
    return true;
  }
  return false;
}

function stripLeadingAssign(s: string): string {
  let i = skipSpaces(s, 0);
  const head = s[i];
  if (head === "y" || head === "Y") {
    i = skipSpaces(s, i + 1);
    if (s[i] === "=") return s.slice(i + 1).trim();
    return s;
  }
  if (head === "f" || head === "F") {
    i = skipSpaces(s, i + 1);
    if (s[i] !== "(") return s;
    i = skipSpaces(s, i + 1);
    if (s[i] !== "x" && s[i] !== "X") return s;
    i = skipSpaces(s, i + 1);
    if (s[i] !== ")") return s;
    i = skipSpaces(s, i + 1);
    if (s[i] === "=") return s.slice(i + 1).trim();
  }
  return s;
}

export type GraphCmp = "=" | "<" | "<=" | ">" | ">=";

type CmpTok = { op: GraphCmp; end: number };

function readCmp(s: string, i: number): CmpTok | null {
  const two = s.slice(i, i + 2);
  if (two === "<=" || two === "=<") return { op: "<=", end: i + 2 };
  if (two === ">=" || two === "=>") return { op: ">=", end: i + 2 };
  if (s[i] === "<") return { op: "<", end: i + 1 };
  if (s[i] === ">") return { op: ">", end: i + 1 };
  if (s[i] === "=") return { op: "=", end: i + 1 };
  return null;
}

/** `y = x^2` / `y < 2x` → comparator + rhs. Bare `x^2` is not a relation. */
function splitYRelation(raw: string): { cmp: GraphCmp; rhs: string } | null {
  const s = preprocess(raw).trim();
  let i = skipSpaces(s, 0);
  if (s[i] !== "y" && s[i] !== "Y") return null;
  i = skipSpaces(s, i + 1);
  const cmp = readCmp(s, i);
  if (!cmp) return null;
  return { cmp: cmp.op, rhs: s.slice(cmp.end).trim() };
}

export function parseGraphRelation(
  src: string,
  variable = "x",
): { node: GraphExprNode; cmp: GraphCmp } | null {
  const rel = splitYRelation(src);
  const node = parseGraphExpr(rel ? rel.rhs : src, variable);
  if (!node) return null;
  return { node, cmp: rel?.cmp ?? "=" };
}

/** Seed the series field so the user can change `=` into `<` / `>`. */
export function formatSeriesExpr(raw: string): string {
  const s = displayGraphExpr(raw);
  if (!s) return "";
  const rel = splitYRelation(s);
  if (rel) return `y ${rel.cmp} ${displayGraphExpr(rel.rhs)}`;
  if (parseGraphExpr(s)) {
    return `y = ${displayGraphExpr(normalizePlotExpr(s))}`;
  }
  return s;
}

export function inequalityFillPoints(
  curve: [number, number][],
  yMin: number,
  yMax: number,
  cmp: GraphCmp,
): [number, number][] {
  if (cmp === "=" || curve.length < 2) return [];
  const below = cmp === "<" || cmp === "<=";
  const x0 = curve[0][0];
  const x1 = curve[curve.length - 1][0];
  const yEdge = below ? yMin : yMax;
  return [...curve, [x1, yEdge], [x0, yEdge]];
}

/** Strip `y=` / `f(x)=` and a trailing `=0` so a plotted polynomial is y=f(x). */
export function normalizePlotExpr(raw: string, variable = "x"): string {
  let s = stripLeadingAssign(preprocess(raw).trim());
  const eq = s.indexOf("=");
  if (eq <= 0) return s;
  const other = variable === "y" ? "x" : "y";
  if (hasIdentToken(s, other)) return s;
  const lhs = s.slice(0, eq).trim();
  const rhs = s.slice(eq + 1).trim();
  if (!lhs) return s;
  if (rhs === "0" || rhs === "") return lhs;
  return `(${lhs})-(${rhs})`;
}

function tokenize(src: string): Tok[] | null {
  const out: Tok[] = [];
  let i = 0;
  const s = src;
  while (i < s.length) {
    const ch = s[i];
    if (ch === " " || ch === "\t" || ch === "\n") {
      i += 1;
      continue;
    }
    if (ch === "*" && s[i + 1] === "*") {
      out.push({ k: "op", v: "^" });
      i += 2;
      continue;
    }
    if ("+-*/^()".includes(ch)) {
      out.push({ k: "op", v: ch });
      i += 1;
      continue;
    }
    if ((ch >= "0" && ch <= "9") || (ch === "." && s[i + 1] >= "0" && s[i + 1] <= "9")) {
      let j = i;
      while (j < s.length && s[j] >= "0" && s[j] <= "9") j += 1;
      if (s[j] === ".") {
        j += 1;
        while (j < s.length && s[j] >= "0" && s[j] <= "9") j += 1;
      }
      const v = Number(s.slice(i, j));
      if (!Number.isFinite(v)) return null;
      out.push({ k: "num", v });
      i = j;
      continue;
    }
    if ((ch >= "A" && ch <= "Z") || (ch >= "a" && ch <= "z")) {
      let j = i + 1;
      while (j < s.length && isIdentChar(s[j])) j += 1;
      out.push({ k: "id", v: s.slice(i, j).toLowerCase() });
      i = j;
      continue;
    }
    return null;
  }
  return out;
}

function canEnd(t: Tok): boolean {
  return t.k === "num" || t.k === "id" || (t.k === "op" && t.v === ")");
}

function canStart(t: Tok): boolean {
  return t.k === "num" || t.k === "id" || (t.k === "op" && t.v === "(");
}

function insertImplicitMul(toks: Tok[]): Tok[] {
  const out: Tok[] = [];
  for (let i = 0; i < toks.length; i += 1) {
    if (i > 0 && canEnd(out[out.length - 1]) && canStart(toks[i])) {
      const prev = out[out.length - 1];
      const isCall =
        prev.k === "id" && toks[i].k === "op" && toks[i].v === "(" && FUNCS[prev.v] != null;
      if (!isCall) out.push({ k: "op", v: "*" });
    }
    out.push(toks[i]);
  }
  return out;
}

class Parser {
  i = 0;
  constructor(
    readonly toks: Tok[],
    readonly variable: string,
  ) {}

  peek(): Tok | undefined {
    return this.toks[this.i];
  }

  take(): Tok | undefined {
    const t = this.toks[this.i];
    this.i += 1;
    return t;
  }

  eatOp(v: string): boolean {
    const t = this.peek();
    if (t?.k === "op" && t.v === v) {
      this.i += 1;
      return true;
    }
    return false;
  }

  parseExpr(): GraphExprNode | null {
    const n = this.parseAdd();
    if (n == null || this.i !== this.toks.length) return null;
    return n;
  }

  parseAdd(): GraphExprNode | null {
    let left = this.parseMul();
    if (left == null) return null;
    while (this.peek()?.k === "op" && (this.peek()?.v === "+" || this.peek()?.v === "-")) {
      const op = this.take()!.v as "+" | "-";
      const right = this.parseMul();
      if (right == null) return null;
      left = { t: "bin", op, l: left, r: right };
    }
    return left;
  }

  parseMul(): GraphExprNode | null {
    let left = this.parseUnary();
    if (left == null) return null;
    while (this.peek()?.k === "op" && (this.peek()?.v === "*" || this.peek()?.v === "/")) {
      const op = this.take()!.v as "*" | "/";
      const right = this.parseUnary();
      if (right == null) return null;
      left = { t: "bin", op, l: left, r: right };
    }
    return left;
  }

  parseUnary(): GraphExprNode | null {
    if (this.eatOp("+")) return this.parseUnary();
    if (this.eatOp("-")) {
      const arg = this.parseUnary();
      return arg ? { t: "unary", arg } : null;
    }
    return this.parsePow();
  }

  parsePow(): GraphExprNode | null {
    const left = this.parsePrimary();
    if (left == null) return null;
    if (!this.eatOp("^")) return left;
    const right = this.parseUnary();
    if (right == null) return null;
    return { t: "bin", op: "^", l: left, r: right };
  }

  parsePrimary(): GraphExprNode | null {
    const t = this.take();
    if (t == null) return null;
    if (t.k === "num") return { t: "num", v: t.v };
    if (t.k === "id") {
      if (this.eatOp("(")) {
        if (FUNCS[t.v] == null) return null;
        const arg = this.parseAdd();
        if (arg == null || !this.eatOp(")")) return null;
        return { t: "call", name: t.v, arg };
      }
      if (t.v === this.variable) return { t: "var" };
      if (CONSTS[t.v] != null) return { t: "num", v: CONSTS[t.v] };
      return null;
    }
    if (t.k === "op" && t.v === "(") {
      const inner = this.parseAdd();
      if (inner == null || !this.eatOp(")")) return null;
      return inner;
    }
    return null;
  }
}

export function parseGraphExpr(src: string, variable = "x"): GraphExprNode | null {
  const normalized = normalizePlotExpr(src, variable);
  if (!normalized || normalized.length > 256) return null;
  const toks = tokenize(normalized);
  if (!toks || toks.length === 0) return null;
  return new Parser(insertImplicitMul(toks), variable.toLowerCase()).parseExpr();
}

export function evalGraphExpr(node: GraphExprNode, x: number): number {
  switch (node.t) {
    case "num":
      return node.v;
    case "var":
      return x;
    case "unary":
      return -evalGraphExpr(node.arg, x);
    case "call":
      return FUNCS[node.name](evalGraphExpr(node.arg, x));
    case "bin": {
      const l = evalGraphExpr(node.l, x);
      const r = evalGraphExpr(node.r, x);
      if (node.op === "+") return l + r;
      if (node.op === "-") return l - r;
      if (node.op === "*") return l * r;
      if (node.op === "/") return l / r;
      return l ** r;
    }
  }
}

function splitDiscontinuities(points: [number, number][]): [number, number][][] {
  if (points.length < 2) return points.length ? [points] : [];
  const absYs = points.map((p) => Math.abs(p[1])).sort((a, b) => a - b);
  const large = absYs[Math.min(absYs.length - 1, Math.floor(absYs.length * 0.85))];
  const segs: [number, number][][] = [[points[0]]];
  for (let i = 1; i < points.length; i += 1) {
    const y0 = points[i - 1][1];
    const y1 = points[i][1];
    const signFlip = y0 > 0 !== y1 > 0;
    if (signFlip && large > 0 && Math.abs(y0) > large && Math.abs(y1) > large) {
      segs.push([]);
    }
    segs[segs.length - 1].push(points[i]);
  }
  return segs.filter((s) => s.length > 0);
}

export function sampleGraphExpr(
  node: GraphExprNode,
  xMin: number,
  xMax: number,
  n = 160,
): { points: [number, number][]; segments?: [number, number][][] } {
  const count = Math.max(2, Math.min(500, Math.floor(n)));
  const span = xMax - xMin;
  const raw: [number, number][] = [];
  for (let i = 0; i <= count; i += 1) {
    const x = xMin + (span * i) / count;
    const y = evalGraphExpr(node, x);
    if (Number.isFinite(x) && Number.isFinite(y) && Math.abs(y) < 1e8) {
      raw.push([x, y]);
    }
  }
  const segs = splitDiscontinuities(raw);
  const points = segs.flat();
  return { points, segments: segs.length > 1 ? segs : undefined };
}

export function displayGraphExpr(src: string): string {
  return preprocess(src).replace(/\*\*/g, "^").trim();
}
