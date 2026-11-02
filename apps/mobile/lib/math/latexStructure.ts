/**
 * TeX structure the native renderer cannot draw, rewritten to what it can
 * show. A colour, a box, a label, a phantom or a spacing command keeps only
 * what is seen; `\xrightarrow{Δ}` becomes an arrow with Δ raised over it.
 * Every argument is read with brace matching, so nesting never strands a
 * brace or a command name. Commands it does not list pass through unchanged.
 */
import { readGroup } from "@/lib/math/latexGroups";
import { LETTER_STYLE_COMMANDS, styledLetters } from "@/lib/math/latexFonts";
import { NATIVE_LITERAL_LEFT_BRACE_MARKER, NATIVE_LITERAL_RIGHT_BRACE_MARKER } from "@/lib/math/textMarkers";

/**
 * One letter per argument: `c` content kept, `C` an optional `[...]` kept,
 * `g` an argument dropped, `o` an optional `[...]` dropped, `*` an optional
 * star dropped, `d` a dimension dropped, `.` a following `.` dropped, `t` one
 * token dropped, `=` an optional `=` dropped, `#` macro parameters dropped.
 * A rule whose syntax is none of these reads its own arguments.
 */
type Read = { value: string; next: number };
type Rule = {
  args: string;
  out: (kept: string[]) => string;
  read?: (source: string, start: number) => { kept: string[]; next: number } | null;
};

const LB = NATIVE_LITERAL_LEFT_BRACE_MARKER;
const RB = NATIVE_LITERAL_RIGHT_BRACE_MARKER;

const keep = (kept: string[]): string => kept.map((value) => `{${value}}`).join("");
const show = (text: string) => (): string => text;
const fill = (template: string) => (kept: string[]): string =>
  template.replace(/#(\d)/g, (_m, n: string) => kept[Number(n) - 1] ?? "");

function rules(names: string, args: string, out: Rule["out"]): [string, Rule][] {
  return names.split(" ").map((name) => [name, { args, out }]);
}

/** `\xrightarrow[below]{above}`: the arrow, its label raised, a lower label under it. */
function arrow(glyph: string): Rule["out"] {
  return ([below, above]) => `{${glyph}}^{${above ?? ""}}${below ? `_{${below}}` : ""}`;
}

const NEGATED: Readonly<Record<string, string>> = {
  "=": "≠", "<": "≮", ">": "≯", "\\in": "∉", "\\ni": "∌", "\\le": "≰", "\\leq": "≰",
  "\\ge": "≱", "\\geq": "≱", "\\subset": "⊄", "\\supset": "⊅", "\\subseteq": "⊈",
  "\\supseteq": "⊉", "\\equiv": "≢", "\\sim": "≁", "\\simeq": "≄", "\\cong": "≇",
  "\\approx": "≉", "\\mid": "∤", "\\parallel": "∦", "\\exists": "∄",
};

/** `\mathbb{R}` is ℝ; a body that is not plain letters keeps its letters. */
function styled(name: string): Rule {
  return {
    args: "c",
    out: ([body = ""]) =>
      /^[A-Za-z0-9 ]+$/.test(body) ? styledLetters(body, LETTER_STYLE_COMMANDS[name]) : `{${body}}`,
  };
}

/** Plain TeX's `\matrix{a & b \cr c & d}` family: rows by `\cr` (already "; "), cells by `&`. */
function plainMatrix(open: string, close: string, cell: string, row = "; "): Rule["out"] {
  return ([body = ""]) => {
    const rows = body.split(/\s*;\s*|\\\\/).map((line) => line.split("&").map((part) => part.trim()));
    return `${open}${rows.filter((cells) => cells.some(Boolean)).map((cells) => cells.join(cell)).join(row)}${close}`;
  };
}

/** `\root 3 \of x` is `\sqrt[3]{x}`. */
function readRoot(source: string, start: number): { kept: string[]; next: number } | null {
  const of = source.indexOf("\\of", start);
  const radicand = of < 0 ? null : readArgument(source, of + 3);
  return radicand ? { kept: [source.slice(start, of).trim(), radicand.value], next: radicand.next } : null;
}

/** `\verb|x+1|`: everything up to the delimiter's second appearance, as written. */
function readVerbatim(source: string, start: number): { kept: string[]; next: number } | null {
  const at = source[start] === "*" ? start + 1 : start;
  const close = source.indexOf(source[at] ?? "", at + 1);
  return close < 0 ? null : { kept: [source.slice(at + 1, close)], next: close + 1 };
}

/** `\toggle{a}{b}\endtoggle` shows its first state; the others, and the end, drop out. */
function readToggle(source: string, start: number): { kept: string[]; next: number } | null {
  const first = readArgument(source, start);
  if (!first) return null;
  const end = source.indexOf("\\endtoggle", first.next);
  let next = end >= 0 ? end + "\\endtoggle".length : first.next;
  for (let more = end >= 0 ? null : readGroup(source, skipSpaces(source, next)); more; ) {
    next = more.next;
    more = readGroup(source, skipSpaces(source, next));
  }
  return { kept: [rewriteLatexStructure(first.value)], next };
}

/** `\unicode{x2192}` / `\unicode{8594}`: the character itself. */
function unicodeChar([code = ""]: string[]): string {
  const hex = /^(?:x|U\+|0x)([0-9a-f]+)$/i.exec(code.trim());
  const value = hex ? Number.parseInt(hex[1], 16) : Number.parseInt(code, 10);
  return Number.isInteger(value) && value > 0 && value <= 0x10ffff ? String.fromCodePoint(value) : "";
}

const RULES: Readonly<Record<string, Rule>> = Object.fromEntries([
  ...Object.keys(LETTER_STYLE_COMMANDS).map((name): [string, Rule] => [name, styled(name)]),
  // Seen as their content.
  ...rules(
    "mathop mathord mathopen mathclose mathbin mathrel mathpunct mathinner vcenter mathup mathnormal " +
      "mathbfup mathbfit mathbfscr mathsf mathsfup mathbfsf mathbfsfup mathsfit mathbfsfit " +
      "mathbfcal symrm symup symnormal symbf symbfup symit symbfit symscr symbfscr symsf symsfup symbfsf " +
      "symbfsfup symsfit symbfsfit symtt symcal symbfcal fbox boxed Aboxed mathmbox pmb ensuremath " +
      "overbrace underbrace overparen underparen llap rlap clap mathllap mathrlap mathclap textllap " +
      "textrlap textclap centerOver AxiomC UnaryInfC BinaryInfC TrinaryInfC QuaternaryInfC QuinaryInfC " +
      "AXC UIC BIC TIC Axiom UnaryInf BinaryInf TrinaryInf QuaternaryInf QuinaryInf RightLabel LeftLabel RL LL",
    "c",
    keep,
  ),
  ...rules("framebox mathmakebox overbracket underbracket", "ooc", keep),
  ...rules("smash cramped crampedllap crampedrlap crampedclap shoveleft shoveright bbox", "oc", keep),
  ...rules("href class cssId style", "gc", keep),
  ...rules("textcolor colorbox", "ogc", keep),
  ...rules("mathtip texttip", "cg", keep),
  ...rules("overset underset stackrel stackbin", "gc", keep),
  ...rules("raise lower moveleft moveright", "dc", keep),
  ["fcolorbox", { args: "oggc", out: keep }],
  ["enclose", { args: "goc", out: keep }],
  ["mmlToken", { args: "goc", out: keep }],
  ["mathchoice", { args: "cggg", out: keep }],
  ["overunderset", { args: "ggc", out: keep }],
  ["sideset", { args: "cc", out: keep }],
  ["prescript", { args: "ccc", out: fill("{}^{#1}_{#2}{#3}") }],
  // Fractions and stacks the native layout draws its own way.
  ...rules("splitfrac splitdfrac", "cc", fill("\\frac{#1}{#2}")),
  ["genfrac", { args: "ggggcc", out: fill("\\frac{#1}{#2}") }],
  ["cfrac", { args: "occ", out: fill("\\frac{#1}{#2}") }],
  ...rules("binom dbinom tbinom", "cc", fill("C(#1,#2)")),
  ...rules("substack crampedsubstack", "c", ([rows = ""]) =>
    rows.split("\\\\").map((row) => row.trim()).filter(Boolean).join("; "),
  ),
  ["cancelto", { args: "cc", out: fill("\\cancel{#2}^{#1}") }],
  ["centernot", { args: "c", out: fill("{#1}\u0338") }],
  ["not", { args: "c", out: ([token = ""]) => NEGATED[token] ?? `{${token}}\u0338` }],
  ["pmod", { args: "c", out: fill("(mod #1)") }],
  ["pod", { args: "c", out: fill("(#1)") }],
  ["tag", { args: "*c", out: fill(" (#1)") }],
  // Accents the native layout has no rule for: a combining mark after the body.
  ...[
    ["acute", "\u0301"], ["grave", "\u0300"], ["breve", "\u0306"], ["check", "\u030c"],
    ["mathring", "\u030a"], ["dddot", "\u20db"], ["ddddot", "\u20dc"], ["overleftrightarrow", "\u20e1"],
    ["underleftrightarrow", "\u034d"], ["underrightarrow", "\u20ef"], ["underleftarrow", "\u20ee"],
  ].map(([name, mark]): [string, Rule] => [name, { args: "c", out: fill(`{#1}${mark}`) }]),
  // Bra-ket notation.
  ...rules("bra Bra", "c", fill("⟨#1|")),
  ...rules("ket Ket", "c", fill("|#1⟩")),
  ...rules("braket Braket", "c", fill("⟨#1⟩")),
  ...rules("ketbra Ketbra", "cc", fill("|#1⟩⟨#2|")),
  ...rules("set Set", "c", fill(`${LB}#1${RB}`)),
  // Arrows with labels.
  ...[
    ["xrightarrow", "→"], ["xleftarrow", "←"], ["xleftrightarrow", "↔"], ["xLeftarrow", "⇐"],
    ["xRightarrow", "⇒"], ["xLeftrightarrow", "⇔"], ["xhookleftarrow", "↩"], ["xhookrightarrow", "↪"],
    ["xmapsto", "↦"], ["xrightharpoondown", "⇁"], ["xleftharpoondown", "↽"], ["xrightleftharpoons", "⇌"],
    ["xRightleftharpoons", "⇌"], ["xLeftrightharpoons", "⇋"], ["xrightharpoonup", "⇀"],
    ["xleftharpoonup", "↼"], ["xleftrightharpoons", "⇋"], ["xtwoheadrightarrow", "↠"],
    ["xtwoheadleftarrow", "↞"], ["xlongequal", "="], ["xtofrom", "⇄"],
  ].map(([name, glyph]): [string, Rule] => [name, { args: "Cc", out: arrow(glyph) }]),
  // Spacing: a gap, never the dimension that sized it.
  ["hspace", { args: "*d", out: show(" ") }],
  ...rules("hskip kern mskip mspace mkern", "d", show(" ")),
  ...rules("phantom hphantom", "c", show(" ")),
  ...rules("enspace thinspace hfill hfil hfilll space nobreakspace", "", show(" ")),
  ...rules("negthinspace negmedspace negthickspace", "", show("")),
  ["rule", { args: "odd", out: show("") }],
  ["Rule", { args: "ddd", out: show("") }],
  ["Space", { args: "ddd", out: show(" ") }],
  ...rules("newline cr", "", show("; ")),
  // Sizing and style switches, delimiter sizes and spacing hints: nothing seen.
  ...rules(
    "displaylimits limits nolimits nonumber notag hline hdashline strut mathstrut xmathstrut nonscript " +
      "MTFlushSpaceAbove MTFlushSpaceBelow adjustlimits noLine singleLine solidLine dashedLine alwaysNoLine " +
      "alwaysSingleLine alwaysSolidLine alwaysDashedLine rootAtTop alwaysRootAtTop rootAtBottom " +
      "alwaysRootAtBottom fCenter rm mit oldstyle cal it bf bbFont scr frak sf tt tiny Tiny scriptsize " +
      "small normalsize large Large LARGE huge Huge displaystyle textstyle scriptstyle scriptscriptstyle " +
      "empheql empheqr empheqbigl empheqbigr",
    "",
    show(""),
  ),
  ...rules(
    "left right middle big Big bigg Bigg bigl Bigl biggl Biggl bigr Bigr biggr Biggr bigm Bigm biggm Biggm",
    ".",
    show(""),
  ),
  // Definitions, labels, colours and settings: nothing seen.
  ...rules(
    "label ref eqref refeq uproot leftroot usetagform mathtoolsset minCDarrowwidth minCDarrowheight vphantom skew",
    "g",
    show(""),
  ),
  ...rules("color cellcolor rowcolor columncolor", "og", show("")),
  ["definecolor", { args: "ggg", out: show("") }],
  ["DeclareMathOperator", { args: "*gg", out: show("") }],
  ...rules("newcommand renewcommand", "*goog", show("")),
  ...rules("newenvironment renewenvironment", "googg", show("")),
  ...rules("Newextarrow DeclarePairedDelimiter DeclarePairedDelimiters", "ggg", show("")),
  ...rules("DeclarePairedDelimiterX DeclarePairedDelimitersX", "goggg", show("")),
  ...rules("DeclarePairedDelimiterXPP DeclarePairedDelimitersXPP", "goggggg", show("")),
  ...rules("newtagform renewtagform", "gogg", show("")),
  ["MoveEqLeft", { args: "o", out: show("") }],
  ["def", { args: "t#g", out: show("") }],
  ["let", { args: "t=t", out: show("") }],
  ["buildrel", { args: "", out: show("") }],
  // Plain TeX's matrices take their body as one argument.
  ["matrix", { args: "c", out: plainMatrix("", "", ", ") }],
  ["pmatrix", { args: "c", out: plainMatrix("(", ")", ", ") }],
  ["cases", { args: "c", out: plainMatrix("", "", " if ") }],
  ...rules("array eqalign displaylines eqalignno leqalignno", "c", plainMatrix("", "", " ", ";  ")),
  ["root", { args: "", read: readRoot, out: fill("\\sqrt[#1]{#2}") }],
  ["verb", { args: "", read: readVerbatim, out: fill("#1") }],
  ["toggle", { args: "", read: readToggle, out: fill("#1") }],
  ["unicode", { args: "oc", out: unicodeChar }],
  // An environment left unpaired once the paired ones are expanded.
  ...rules("begin end", "g", show("")),
  ["ArrowBetweenLines", { args: "*o", out: show("") }],
  // Symbols that MathJax builds from pieces.
  ...rules("vdotswithin", "g", show("⋮")),
  ["shortvdotswithin", { args: "*g", out: show("⋮") }],
  ...[
    ["TeX", "TeX"], ["LaTeX", "LaTeX"], ["dots", "…"], ["impliedby", "⟸"], ["mod", " mod "],
    ["idotsint", "∫⋯∫"], ["bigtimes", "⨉"], ["centercolon", ":"], ["ordinarycolon", ":"],
    ["MTThinColon", ":"], ["coloneqq", "≔"], ["Coloneqq", "⩴"], ["coloneq", ":−"], ["Coloneq", "∷−"],
    ["eqqcolon", "≕"], ["Eqqcolon", "=∷"], ["eqcolon", "∹"], ["Eqcolon", "−∷"], ["colonapprox", ":≈"],
    ["Colonapprox", "∷≈"], ["colonsim", ":∼"], ["Colonsim", "∷∼"], ["dblcolon", "∷"],
    ["nuparrow", "↑\u0338"], ["ndownarrow", "↓\u0338"], ["longrightleftharpoons", "⇌"],
    ["longRightleftharpoons", "⇌"], ["longLeftrightharpoons", "⇋"], ["longleftrightarrows", "⇄"],
    ["tripledash", "≡"], ["empheqlbrace", LB], ["empheqrbrace", RB], ["empheqbiglbrace", LB],
    ["empheqbigrbrace", RB], ["empheqlbrack", "["], ["empheqrbrack", "]"], ["empheqbiglbrack", "["],
    ["empheqbigrbrack", "]"], ["empheqlangle", "⟨"], ["empheqrangle", "⟩"], ["empheqbiglangle", "⟨"],
    ["empheqbigrangle", "⟩"], ["empheqlparen", "("], ["empheqrparen", ")"], ["empheqbiglparen", "("],
    ["empheqbigrparen", ")"], ["empheqlvert", "|"], ["empheqrvert", "|"], ["empheqbiglvert", "|"],
    ["empheqbigrvert", "|"], ["empheqlVert", "‖"], ["empheqrVert", "‖"], ["empheqbiglVert", "‖"],
    ["empheqbigrVert", "‖"], ["empheqlfloor", "⌊"], ["empheqrfloor", "⌋"], ["empheqbiglfloor", "⌊"],
    ["empheqbigrfloor", "⌋"], ["empheqlceil", "⌈"], ["empheqrceil", "⌉"], ["empheqbiglceil", "⌈"],
    ["empheqbigrceil", "⌉"],
  ].map(([name, text]): [string, Rule] => [name, { args: "", out: show(text) }]),
  // Infix fractions: `{a \over b}`.
  ...rules("over above", "", show("/")),
  ...rules("overwithdelims abovewithdelims", "gg", show("/")),
  ...rules("atop brace brack", "", show(" ")),
  ["atopwithdelims", { args: "gg", out: show(" ") }],
  ["choose", { args: "", out: show(" choose ") }],
]);

function skipSpaces(source: string, i: number): number {
  let at = i;
  while (source[at] === " ") at += 1;
  return at;
}

/** One TeX token: a control word, an escaped character, or one character. */
function readToken(source: string, i: number): Read | null {
  if (i >= source.length || source[i] === "}") return null;
  if (source[i] === "\\") {
    const word = /^\\[A-Za-z]+/.exec(source.slice(i))?.[0] ?? source.slice(i, i + 2);
    return { value: word, next: i + word.length };
  }
  const ch = String.fromCodePoint(source.codePointAt(i) ?? 0);
  return { value: ch, next: i + ch.length };
}

/** A braced argument, or the single token TeX takes when the braces are left off. */
function readArgument(source: string, i: number): Read | null {
  const at = skipSpaces(source, i);
  return source[at] === "{" ? readGroup(source, at) : readToken(source, at);
}

function readOptional(source: string, i: number): Read | null {
  const at = skipSpaces(source, i);
  if (source[at] !== "[") return null;
  let depth = 0;
  for (let k = at + 1; k < source.length; k += 1) {
    if (source[k] === "\\") k += 1;
    else if (source[k] === "{") depth += 1;
    else if (source[k] === "}") depth -= 1;
    else if (source[k] === "]" && depth === 0) return { value: source.slice(at + 1, k), next: k + 1 };
  }
  return null;
}

const DIMENSION =
  /^[+-]?\s*(?:\d+\.?\d*|\.\d+)\s*(?:em|ex|pt|pc|in|cm|mm|bp|dd|cc|sp|mu|px)(?:\s+(?:plus|minus)\s+[+-]?\s*(?:\d+\.?\d*|\.\d+)\s*(?:em|ex|pt|pc|in|cm|mm|bp|dd|cc|sp|mu|px|fil+))*/;

function readDimension(source: string, i: number): Read | null {
  const at = skipSpaces(source, i);
  if (source[at] === "{") return readGroup(source, at);
  const match = DIMENSION.exec(source.slice(at));
  return match ? { value: match[0], next: at + match[0].length } : readToken(source, at);
}

/** Read a rule's arguments; null when a required one is missing. */
function readArgs(source: string, start: number, spec: string): { kept: string[]; next: number } | null {
  const kept: string[] = [];
  let i = start;
  for (const kind of spec) {
    if (kind === "*" || kind === "." || kind === "=") {
      const at = skipSpaces(source, i);
      if (source[at] === kind) i = at + 1;
      continue;
    }
    if (kind === "#") {
      i = skipSpaces(source, i);
      while (/^#\d/.test(source.slice(i, i + 2))) i += 2;
      continue;
    }
    if (kind === "o" || kind === "C") {
      const optional = readOptional(source, i);
      if (kind === "C") kept.push(optional ? rewriteLatexStructure(optional.value) : "");
      if (optional) i = optional.next;
      continue;
    }
    const read =
      kind === "d" ? readDimension(source, i) : kind === "t" ? readToken(source, skipSpaces(source, i)) : readArgument(source, i);
    if (!read) return null;
    if (kind === "c") kept.push(rewriteLatexStructure(read.value));
    i = read.next;
  }
  return { kept, next: i };
}

/** Rewrite every listed command; anything else is copied as written. */
export function rewriteLatexStructure(source: string): string {
  let out = "";
  let i = 0;
  while (i < source.length) {
    if (source[i] !== "\\") {
      out += source[i];
      i += 1;
      continue;
    }
    const name = /^[A-Za-z]+/.exec(source.slice(i + 1))?.[0];
    if (!name) {
      out += source.slice(i, i + 2);
      i += 2;
      continue;
    }
    const end = i + 1 + name.length;
    const rule = Object.hasOwn(RULES, name) ? RULES[name] : undefined;
    const read = rule ? (rule.read ?? ((text, at) => readArgs(text, at, rule.args)))(source, end) : null;
    if (!rule || !read) {
      out += `\\${name}`;
      i = end;
      continue;
    }
    out += rule.out(read.kept);
    i = read.next;
  }
  return out;
}
