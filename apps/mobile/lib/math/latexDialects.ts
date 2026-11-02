/**
 * LaTeX that models borrow from packages neither renderer loads, rewritten to
 * standard TeX before either one sees it: `\bm`, `\R`, siunitx quantities
 * (`\SI{9.8}{\meter\per\second\squared}`), the physics package's `\abs`,
 * `\norm`, `\dv` and `\pdv`, and operator names such as `\sgn`. MathJax
 * (display maths) and the native renderer (inline maths) share this pass, so
 * the two draw the same thing.
 */
import { readGroup } from "@/lib/math/latexGroups";

/** Operator names TeX lacks but writers use; each is set upright like `\sin`. */
export const EXTRA_OPERATOR_NAMES: Readonly<Record<string, string>> = {
  sgn: "sgn", sign: "sign", lcm: "lcm", rank: "rank", tr: "tr", Tr: "Tr", trace: "trace",
  diag: "diag", Var: "Var", Cov: "Cov", Corr: "Corr", erf: "erf", erfc: "erfc", Arg: "Arg",
  Log: "Log", adj: "adj", sech: "sech", csch: "csch", arcsec: "arcsec", arccsc: "arccsc",
  arccot: "arccot", arsinh: "arsinh", arcosh: "arcosh", artanh: "artanh", arcsinh: "arcsinh",
  arccosh: "arccosh", arctanh: "arctanh", sinc: "sinc", proj: "proj", grad: "grad", curl: "curl",
  rot: "rot", Res: "Res", ord: "ord", Span: "span", supp: "supp", dist: "dist", diam: "diam",
  vol: "vol", cis: "cis", argmax: "arg max", argmin: "arg min",
};

const RENAMES: Readonly<Record<string, string>> = {
  bm: "\\boldsymbol", R: "\\mathbb{R}", N: "\\mathbb{N}", Z: "\\mathbb{Z}", Q: "\\mathbb{Q}",
  C: "\\mathbb{C}", Reals: "\\mathbb{R}", Complex: "\\mathbb{C}", vb: "\\mathbf",
  ...Object.fromEntries(
    Object.entries(EXTRA_OPERATOR_NAMES).map(([name, word]) => [name, `\\operatorname{${word}}`]),
  ),
};

const SI_UNITS: Readonly<Record<string, string>> = {
  meter: "m", metre: "m", second: "s", kilogram: "kg", gram: "g", ampere: "A", kelvin: "K",
  mole: "mol", candela: "cd", newton: "N", joule: "J", watt: "W", volt: "V", ohm: "Ω",
  coulomb: "C", farad: "F", henry: "H", tesla: "T", weber: "Wb", siemens: "S", hertz: "Hz",
  pascal: "Pa", becquerel: "Bq", gray: "Gy", sievert: "Sv", lumen: "lm", lux: "lx", katal: "kat",
  radian: "rad", steradian: "sr", liter: "L", litre: "L", minute: "min", hour: "h", day: "d",
  electronvolt: "eV", dalton: "Da", atomicmassunit: "u", astronomicalunit: "au", bar: "bar",
  angstrom: "Å", hectare: "ha", tonne: "t", decibel: "dB", bel: "B", neper: "Np", mmHg: "mmHg",
  degree: "°", arcminute: "′", arcsecond: "″", percent: "%", celsius: "°C", degreeCelsius: "°C",
};

const SI_PREFIXES: Readonly<Record<string, string>> = {
  quecto: "q", ronto: "r", yocto: "y", zepto: "z", atto: "a", femto: "f", pico: "p", nano: "n",
  micro: "µ", milli: "m", centi: "c", deci: "d", deca: "da", deka: "da", hecto: "h", kilo: "k",
  mega: "M", giga: "G", tera: "T", peta: "P", exa: "E", zetta: "Z", yotta: "Y", ronna: "R",
  quetta: "Q",
};

type Read = { value: string; next: number };

function readBraced(source: string, i: number): Read | null {
  let at = i;
  while (source[at] === " ") at += 1;
  return readGroup(source, at);
}

function readOptional(source: string, i: number): Read | null {
  let at = i;
  while (source[at] === " ") at += 1;
  if (source[at] !== "[") return null;
  const close = source.indexOf("]", at);
  return close < 0 ? null : { value: source.slice(at + 1, close), next: close + 1 };
}

/** `1.5e3` → 1.5×10³ and `3+-0.1` → 3 ± 0.1, as siunitx prints a number. */
function siNumber(raw: string): string {
  const text = raw.trim().replace(/\+-/g, "\\pm ");
  const exp = /^([+-]?[\d.,]+)\s*[eE]\s*([+-]?\d+)$/.exec(text);
  return exp ? `${exp[1]}\\times10^{${exp[2]}}` : text;
}

/** siunitx's unit macros, or a written unit (`m/s^2`), as upright TeX with raised powers. */
function siUnit(raw: string): string {
  const parts: string[] = [];
  let prefix = "";
  let power = "";
  const add = (symbol: string) => {
    parts.push(`\\mathrm{${prefix}${symbol}}${power ? `^{${power}}` : ""}`);
    prefix = "";
    power = "";
  };
  const tokens = raw.match(/\\[A-Za-z]+|\{[^{}]*\}|\^\{?[-+]?[\d.]+\}?|[A-Za-zµΩ°Å%′″]+|[/.~*·]|\S/g) ?? [];
  for (let k = 0; k < tokens.length; k += 1) {
    const token = tokens[k];
    const name = token.startsWith("\\") ? token.slice(1) : null;
    if (name && SI_PREFIXES[name]) prefix += SI_PREFIXES[name];
    else if (name && SI_UNITS[name]) add(SI_UNITS[name]);
    else if (name === "per" || token === "/") parts.push("/");
    else if (name === "square" || name === "cubic") power = name === "square" ? "2" : "3";
    else if (name === "squared" || name === "cubed") {
      parts[parts.length - 1] += `^{${name === "squared" ? "2" : "3"}}`;
    } else if (name === "tothe" || name === "raiseto") {
      const exponent = (tokens[k + 1] ?? "").replace(/[{}]/g, "");
      k += 1;
      if (name === "raiseto") power = exponent;
      else parts[parts.length - 1] += `^{${exponent}}`;
    } else if (token.startsWith("^")) {
      parts[parts.length - 1] += `^{${token.slice(1).replace(/[{}]/g, "")}}`;
    } else if (/^[A-Za-zµΩ°Å%′″]+$/.test(token)) add(token);
    else if (/^[.~*·]$/.test(token)) parts.push("\\cdot ");
  }
  return parts.join("").replace(/\}\\mathrm/g, "}\\,\\mathrm");
}

/** `\ang{30}` and `\ang{30;15;10}`: degrees, minutes, seconds. */
function siAngle(raw: string): string {
  const [deg = "", min = "", sec = ""] = raw.split(";").map((part) => part.trim());
  return `${deg ? `${deg}^{\\circ}` : ""}${min ? `${min}′` : ""}${sec ? `${sec}″` : ""}`;
}

type Dialect = (source: string, start: number) => { tex: string; next: number } | null;

/** siunitx quantity: `\SI[opts]{value}[pre]{unit}` or v3's `\qty{value}{unit}`.
 * The physics package's `\qty(…)` only sizes its brackets, so it drops out. */
const quantity: Dialect = (source, start) => {
  const options = readOptional(source, start);
  const value = readBraced(source, options?.next ?? start);
  if (!value) return options ? null : { tex: "", next: start };
  const pre = readOptional(source, value.next);
  const unit = readBraced(source, pre?.next ?? value.next);
  if (!unit) return null;
  return { tex: `${siNumber(value.value)}\\,${siUnit(unit.value)}`, next: unit.next };
};

/** A command with one braced argument after an optional `[...]`. */
function oneArgument(render: (value: string) => string): Dialect {
  return (source, start) => {
    const options = readOptional(source, start);
    const arg = readBraced(source, options?.next ?? start);
    return arg ? { tex: render(arg.value), next: arg.next } : null;
  };
}

/** physics' `\dv[n]{f}{x}` / `\pdv{f}{x}`: a derivative written as a fraction. */
function derivative(d: string): Dialect {
  return (source, start) => {
    const order = readOptional(source, start);
    const f = readBraced(source, order?.next ?? start);
    if (!f) return null;
    const x = readBraced(source, f.next);
    const n = order?.value.trim();
    const top = `${d}${n ? `^{${n}}` : ""}`;
    if (!x) return { tex: `\\frac{${top}}{${d}${f.value}${n ? `^{${n}}` : ""}}`, next: f.next };
    return { tex: `\\frac{${top}${f.value}}{${d}${x.value}${n ? `^{${n}}` : ""}}`, next: x.next };
  };
}

const DIALECTS: Readonly<Record<string, Dialect>> = {
  SI: quantity,
  qty: quantity,
  si: oneArgument(siUnit),
  unit: oneArgument(siUnit),
  num: oneArgument(siNumber),
  ang: oneArgument(siAngle),
  abs: oneArgument((value) => `\\left|${value}\\right|`),
  norm: oneArgument((value) => `\\left\\|${value}\\right\\|`),
  expval: oneArgument((value) => `\\left\\langle ${value}\\right\\rangle`),
  vu: oneArgument((value) => `\\hat{\\mathbf{${value}}}`),
  dv: derivative("d"),
  pdv: derivative("\\partial "),
};

/** Rewrite every dialect command in `source` to standard TeX. */
export function rewriteLatexDialects(source: string): string {
  if (!source.includes("\\")) return source;
  let out = "";
  let i = 0;
  while (i < source.length) {
    const name = source[i] === "\\" ? /^[A-Za-z]+/.exec(source.slice(i + 1))?.[0] : undefined;
    if (!name) {
      out += source[i] === "\\" ? source.slice(i, i + 2) : source[i];
      i += source[i] === "\\" ? 2 : 1;
      continue;
    }
    const end = i + 1 + name.length;
    const dialect = Object.hasOwn(DIALECTS, name) ? DIALECTS[name] : undefined;
    const rewritten = dialect?.(source, end);
    if (rewritten) {
      out += rewriteLatexDialects(rewritten.tex);
      i = rewritten.next;
    } else {
      out += Object.hasOwn(RENAMES, name) ? RENAMES[name] : `\\${name}`;
      i = end;
    }
  }
  return out;
}

/** The commands this pass rewrites (the coverage test reads it). */
export const DIALECT_COMMANDS: ReadonlySet<string> = new Set([
  ...Object.keys(DIALECTS),
  ...Object.keys(RENAMES),
]);
