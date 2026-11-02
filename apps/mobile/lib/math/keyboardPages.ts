import {
  MATH_KEYBOARD_SYMBOLS,
  MATH_PAD_KEYS,
  type MathKeyboardGroup,
  type MathKeyboardSymbol,
} from "@/lib/math/keyboardCatalog";

export type PadCell =
  | { kind: "insert"; spec: MathKeyboardSymbol }
  | { kind: "left" }
  | { kind: "right" }
  | { kind: "backspace" };

/** Every page is the same 6 × 6 grid, so every key is the same size. */
export const PAD_ROWS = 6;

export type SymbolPage = Exclude<MathKeyboardGroup, "converter" | "pad">;

/**
 * Key ids, row by row. The last row holds three keys and then ← → ⌫, which
 * sit in the same place on every page.
 *
 * Basics is a calculator: templates on top, letters and comparisons on the
 * left, digits and the four operations on the right, so `2x + 3 = 7` needs
 * no page switch.
 */
const PAGES: Record<SymbolPage, readonly (readonly string[])[]> = {
  basics: [
    ["frac", "sqrt", "sq", "sup", "parens", "abs"],
    ["var-x", "var-y", "digit-7", "digit-8", "digit-9", "div"],
    ["lt", "gt", "digit-4", "digit-5", "digit-6", "times"],
    ["leq", "geq", "digit-1", "digit-2", "digit-3", "minus"],
    ["pi", "comma", "digit-0", "digit-dot", "eq", "plus"],
    ["nroot", "sub", "pm"],
  ],
  symbols: [
    ["neq", "approx", "equiv", "percent", "ratio", "var-z"],
    ["brackets", "braces", "floor", "ceil", "mod", "therefore"],
    ["angle", "triangle", "perp", "parallel", "cong", "sim"],
    ["in", "notin", "subset", "subseteq", "cup", "cap"],
    ["emptyset", "naturals", "integers", "rationals", "reals", "forall"],
    ["exists", "implies", "iff"],
  ],
  trig: [
    ["sin", "cos", "tan", "cot", "sec", "csc"],
    ["arcsin", "arccos", "arctan", "arccot", "arcsec", "arccsc"],
    ["sinh", "cosh", "tanh", "coth", "sech", "csch"],
    ["arcsinh", "arccosh", "arctanh", "theta", "deg", "rad"],
    ["pi-over-6", "pi-over-4", "pi-over-3", "pi-over-2", "two-pi-over-3", "three-pi-over-4"],
    ["five-pi-over-6", "three-pi-over-2", "two-pi"],
  ],
  calc: [
    ["int", "dint", "iint", "iiint", "oint", "dx"],
    ["der", "der2", "ddv", "ddt", "prime", "dy"],
    ["partial", "partial-x", "nabla", "vec", "cdot", "infty"],
    ["sum", "prod", "lim", "to", "binom", "perm"],
    ["log", "ln", "logn", "exp", "euler", "tenpow"],
    ["e-const", "imag", "fact"],
  ],
  greek: [
    ["alpha", "beta", "gamma", "delta", "epsilon", "zeta"],
    ["eta", "theta", "iota", "kappa", "lambda", "mu"],
    ["nu", "xi", "pi", "rho", "sigma", "tau"],
    ["upsilon", "phi", "chi", "psi", "omega", "Gamma"],
    ["Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma"],
    ["Phi", "Psi", "Omega"],
  ],
};

const SPECS = new Map(
  [...MATH_KEYBOARD_SYMBOLS, ...MATH_PAD_KEYS].map((spec) => [spec.id, spec] as const),
);

function spec(id: string): MathKeyboardSymbol {
  const found = SPECS.get(id);
  if (!found) throw new Error(`missing math key ${id}`);
  return found;
}

const CONTROLS: readonly PadCell[] = [{ kind: "left" }, { kind: "right" }, { kind: "backspace" }];

/** The page's rows, with ← → ⌫ closing the last one. */
export function padRows(page: SymbolPage): PadCell[][] {
  const rows = PAGES[page];
  return rows.map((ids, r) => {
    const cells: PadCell[] = ids.map((id) => ({ kind: "insert", spec: spec(id) }));
    return r === rows.length - 1 ? [...cells, ...CONTROLS] : cells;
  });
}
