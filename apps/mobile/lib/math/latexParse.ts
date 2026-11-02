import { readGroup } from "@/lib/math/latexGroups";
import { preprocessLatex } from "@/lib/math/latexPreprocess";
import { pushNamedFunction } from "@/lib/math/latexCommands";
import { latexNameKind, operatorWord, reportUnknownLatexCommand, symbolGlyph } from "@/lib/math/latexNames";
import {
  MAX_MATH_NEST_DEPTH,
  NATIVE_LITERAL_APOSTROPHE_MARKER,
  NATIVE_LITERAL_LEFT_BRACE_MARKER,
  NATIVE_LITERAL_RIGHT_BRACE_MARKER,
  NATIVE_UPRIGHT_END_MARKER,
  NATIVE_UPRIGHT_START_MARKER,
  restoreNativeLiterals,
} from "@/lib/math/textMarkers";
import type { MathAccentKind, MathSegment } from "@/lib/math/textTypes";

// Copy and read-aloud still spell an accent as a combining mark. The screen
// draws a measured rule from the accent segment; these marks are not painted.
const ACCENT_MARK: Record<MathAccentKind, string> = {
  overline: "̅",
  underline: "̲",
  hat: "̂",
  tilde: "̃",
  vec: "⃗",
  vecLeft: "⃖",
  bar: "̄",
  ddot: "̈",
  dot: "̇",
};

/** Combining mark applied per-character so copy spells the whole accented
 * run. The screen draws one measured rule; these marks are not painted. */
function markEachChar(text: string, mark: string): string {
  return Array.from(text)
    .map((ch) => (ch === " " ? ch : `${ch}${mark}`))
    .join("");
}

/** Braced scripts and root indexes that are only ordinary letters stay
 * strings. Upright runs keep their segment so the renderer preserves their
 * font style inside a subscript (for example, `t_{\mathrm{flight}}`). */
function plainScriptPieces(segments: MathSegment[]): string | null {
  let plain = "";
  for (const segment of segments) {
    if (segment.type !== "text") return null;
    plain += segment.value;
  }
  return plain;
}

/** A structural command at its backslash: `name` is the table key it matched. */
type LatexCommand = { input: string; start: number; depth: number; name: string };
type ParsedSegment = { seg: MathSegment; next: number } | null;
type LatexHandler = (cmd: LatexCommand) => ParsedSegment;

function parseFrac({ input, start, depth }: LatexCommand): ParsedSegment {
  let i = start + 5;
  while (input[i] === " ") i += 1;
  const numGroup = readGroup(input, i);
  if (!numGroup) return null;
  i = numGroup.next;
  while (input[i] === " ") i += 1;
  const denGroup = readGroup(input, i);
  if (!denGroup) return null;
  return {
    seg: {
      type: "frac",
      // Keep num/den as parsed segments (not flattened strings) so the
      // renderer can render superscripts/subscripts/fractions INSIDE a
      // fraction — \frac{x^2}{4} shows x² in the numerator, not literal "x^2".
      num: parseSimpleLatex(numGroup.value, depth + 1),
      den: parseSimpleLatex(denGroup.value, depth + 1),
    },
    next: denGroup.next,
  };
}

/**
 * \sqrt{x} / \sqrt[n]{x} — mirrors parseFrac: readGroup tracks brace depth,
 * so a radicand containing its own braces (\sqrt{\frac{M}{2}}) parses
 * correctly instead of a flat `[^}]+` regex stopping at the FIRST `}`.
 */
function parseSqrt({ input, start, depth }: LatexCommand): ParsedSegment {
  let i = start + 5;
  let degree: string | undefined;
  let index: MathSegment[] | undefined;
  if (input[i] === "[") {
    const close = input.indexOf("]", i);
    if (close === -1) return null;
    const raw = input.slice(i + 1, close);
    const parsed = parseSimpleLatex(raw, depth + 1);
    const plain = plainScriptPieces(parsed);
    if (plain == null) index = parsed;
    else degree = plain;
    i = close + 1;
  }
  while (input[i] === " ") i += 1;
  const group = readGroup(input, i);
  if (group) {
    return {
      seg: { type: "sqrt", body: parseSimpleLatex(group.value, depth + 1), degree, index },
      next: group.next,
    };
  }
  // `\sqrt\text{x}` / `\sqrt\frac{1}{2}` — the radicand is one atom, not the
  // letters "sqrt" followed by that atom.
  const atom = readLeadingAtom(input, i, depth);
  if (atom) {
    return { seg: { type: "sqrt", body: atom.body, degree, index }, next: atom.next };
  }
  // \sqrt without braces (\sqrt4, \sqrt 4) — bare single-token radicand.
  const bare = input.slice(i).match(/^[0-9a-zA-Z]+/)?.[0];
  if (bare) {
    return { seg: { type: "sqrt", body: [{ type: "text", value: bare }], degree, index }, next: i + bare.length };
  }
  return null;
}

/**
 * \\cancel{3} / \\bcancel / \\xcancel — strike a cancelled factor in a divide step.
 */
function parseCancel({ input, start, depth, name }: LatexCommand): ParsedSegment {
  let i = start + 1 + name.length;
  while (input[i] === " ") i += 1;
  const group = readGroup(input, i);
  if (group) {
    return {
      seg: { type: "cancel", body: parseSimpleLatex(group.value, depth + 1) },
      next: group.next,
    };
  }
  const atom = readLeadingAtom(input, i, depth);
  if (!atom) return null;
  return { seg: { type: "cancel", body: atom.body }, next: atom.next };
}

/** `\hat{x}`, `\hat x`, `\overline{AB}`: the accent's body, braced or one atom. */
function accent(kind: MathAccentKind, span = false): LatexHandler {
  return ({ input, start, depth, name }) => {
    let i = start + 1 + name.length;
    while (input[i] === " ") i += 1;
    const group = readGroup(input, i);
    const body = group
      ? { segments: parseSimpleLatex(group.value, depth + 1), next: group.next }
      : readUnbracedAccentAtom(input, i, depth);
    if (!body) return null;
    return { seg: { type: "accent", kind, span, body: body.segments }, next: body.next };
  };
}

/**
 * The structural commands. A root, a fraction and a cancel are read by their
 * prefix (`\sqrtx` is the root of x); an accent only as its whole word.
 */
const LATEX_HANDLERS: Record<string, LatexHandler> = {
  frac: parseFrac,
  sqrt: parseSqrt,
  xcancel: parseCancel,
  bcancel: parseCancel,
  cancel: parseCancel,
  overrightarrow: accent("vec", true),
  overleftarrow: accent("vecLeft", true),
  overline: accent("overline"),
  underline: accent("underline"),
  widehat: accent("hat", true),
  widetilde: accent("tilde", true),
  ddot: accent("ddot"),
  hat: accent("hat"),
  vec: accent("vec"),
  bar: accent("bar"),
  dot: accent("dot"),
  tilde: accent("tilde"),
};
const PREFIX_COMMANDS = ["frac", "sqrt", "xcancel", "bcancel", "cancel"];

function commandName(word: string): string | undefined {
  return Object.hasOwn(LATEX_HANDLERS, word) ? word : PREFIX_COMMANDS.find((name) => word.startsWith(name));
}

/** What `^\circ` parses to: a raised ring, which in a superscript is a degree sign. */
export const DEGREE_RING = "∘";

function segmentToPlain(seg: MathSegment): string {
  if (seg.type === "text" || seg.type === "upright") return seg.value;
  if (seg.type === "sup" || seg.type === "sub") {
    if (seg.body) {
      const inner = segmentsToPlain(seg.body);
      return seg.type === "sup" ? `^${inner}` : `_${inner}`;
    }
    if (seg.type === "sup" && seg.value === DEGREE_RING) return "°";
    return seg.type === "sup" ? `^${seg.value}` : `_${seg.value}`;
  }
  if (seg.type === "cancel") return segmentsToPlain(seg.body);
  if (seg.type === "accent") {
    return markEachChar(segmentsToPlain(seg.body), ACCENT_MARK[seg.kind]);
  }
  if (seg.type === "sqrt") {
    // Radicand under a combining overline ("4̅"), not "(4)" in parens — the
    // bar itself delimits what's under the root, closer to how it's drawn
    // on paper. Nested content (a fraction, superscript, …) is flattened
    // to plain text first since there's no way to draw it under a bar too.
    const body = markEachChar(segmentsToPlain(seg.body), "̅");
    const indexText = seg.index ? segmentsToPlain(seg.index) : seg.degree;
    return indexText ? `√[${indexText}]${body}` : `√${body}`;
  }
  return `${segmentsToPlain(seg.num)}/${segmentsToPlain(seg.den)}`;
}

/** `\text{flight}` after a bare `_` or `^` is one upright script.
 * Taking only the private-use start marker made iOS draw it as an emoji
 * and left the closing marker beside the word. */
function readMarkedUpright(input: string, i: number): { value: string; next: number } | null {
  if (input[i] !== NATIVE_UPRIGHT_START_MARKER) return null;
  const end = input.indexOf(NATIVE_UPRIGHT_END_MARKER, i + 1);
  if (end < 0) return null;
  const value = input
    .slice(i + 1, end)
    .split(NATIVE_LITERAL_APOSTROPHE_MARKER).join("'")
    .split(NATIVE_LITERAL_LEFT_BRACE_MARKER).join("{")
    .split(NATIVE_LITERAL_RIGHT_BRACE_MARKER).join("}");
  return { value, next: end + 1 };
}

function literalBraceChar(ch: string | undefined): string | null {
  if (ch === NATIVE_LITERAL_LEFT_BRACE_MARKER) return "{";
  if (ch === NATIVE_LITERAL_RIGHT_BRACE_MARKER) return "}";
  if (ch === NATIVE_LITERAL_APOSTROPHE_MARKER) return "'";
  return null;
}

/** `\max`, `\mathbf{v}`, `\frac{1}{2}`, `\sqrt[3]{8}` — one atom, not one character. */
function readCommandAtom(input: string, i: number): { source: string; next: number } | null {
  if (input[i] !== "\\") return null;
  const match = /^\\([a-zA-Z]+)/.exec(input.slice(i));
  if (!match) {
    if (!input[i + 1]) return null;
    return { source: input.slice(i, i + 2), next: i + 2 };
  }
  const name = match[1] ?? "";
  let head = i + match[0].length;
  if (name === "operatorname" && input[head] === "*") head += 1;
  let j = head;
  while (input[j] === " ") j += 1;
  if (input[j] === "[") {
    const close = input.indexOf("]", j + 1);
    if (close >= 0) {
      j = close + 1;
      while (input[j] === " ") j += 1;
    }
  }
  if (input[j] !== "{") return { source: input.slice(i, head), next: head };
  const wanted = name === "frac" ? 2 : 1;
  let end = j;
  let got = 0;
  while (got < wanted && input[end] === "{") {
    const group = readGroup(input, end);
    if (!group) break;
    end = group.next;
    got += 1;
    if (got < wanted) {
      while (input[end] === " ") end += 1;
    }
  }
  if (got !== wanted) return { source: input.slice(i, head), next: head };
  return { source: input.slice(i, end), next: end };
}

/** `\{...\}` after preprocessing is a real TeX group. Models escape braces
 * that were only grouping (`x^\{2\}`, `\sqrt\{x\}`). An unclosed `\{` stays
 * a visible brace. */
function readMarkerGroup(input: string, start: number): { value: string; next: number } | null {
  if (input[start] !== NATIVE_LITERAL_LEFT_BRACE_MARKER) return null;
  let depth = 1;
  for (let k = start + 1; k < input.length; k += 1) {
    if (input[k] === NATIVE_LITERAL_LEFT_BRACE_MARKER) depth += 1;
    else if (input[k] === NATIVE_LITERAL_RIGHT_BRACE_MARKER) {
      depth -= 1;
      if (depth === 0) return { value: input.slice(start + 1, k), next: k + 1 };
    }
  }
  return null;
}

/** Upright word, escaped brace group, or backslash command. Not a plain letter. */
function readLeadingAtom(
  input: string,
  i: number,
  depth: number,
): { body: MathSegment[]; next: number } | null {
  const marked = readMarkedUpright(input, i);
  if (marked) return { body: [{ type: "upright", value: marked.value }], next: marked.next };
  if (input[i] === NATIVE_LITERAL_LEFT_BRACE_MARKER) {
    const group = readMarkerGroup(input, i);
    if (group) return { body: parseSimpleLatex(group.value, depth + 1), next: group.next };
    return { body: [{ type: "text", value: "{" }], next: i + 1 };
  }
  const brace = literalBraceChar(input[i]);
  if (brace) return { body: [{ type: "text", value: brace }], next: i + 1 };
  if (input[i] !== "\\") return null;
  const atom = readCommandAtom(input, i);
  if (!atom) return null;
  return { body: parseSimpleLatex(atom.source, depth + 1), next: atom.next };
}

/** `\hat x` and `\hat\text{v}` take one atom when the braces were omitted. */
function readUnbracedAccentAtom(
  input: string,
  i: number,
  depth: number,
): { segments: MathSegment[]; next: number } | null {
  const leading = readLeadingAtom(input, i, depth);
  if (leading) return { segments: leading.body, next: leading.next };
  const cp = input.codePointAt(i);
  if (cp == null) return null;
  const ch = String.fromCodePoint(cp);
  if (/[\s^_{}\\]/.test(ch)) return null;
  return { segments: [{ type: "text", value: ch }], next: i + ch.length };
}

function readBareScript(input: string, i: number): { value: string; next: number } {
  if (i >= input.length) return { value: "", next: i };
  let j = i;
  if (input[j] === "+" || input[j] === "-") j += 1;
  if (j < input.length && input[j] >= "0" && input[j] <= "9") {
    while (j < input.length && input[j] >= "0" && input[j] <= "9") j += 1;
    return { value: input.slice(i, j), next: j };
  }
  if (j === i && ((input[j] >= "a" && input[j] <= "z") || (input[j] >= "A" && input[j] <= "Z"))) {
    return { value: input[j] ?? "", next: i + 1 };
  }
  const raw = input[i] ?? "";
  const brace = literalBraceChar(raw);
  if (brace) return { value: brace, next: i + 1 };
  const code = raw.codePointAt(0) ?? 0;
  // A private-use sentinel is never a visible script. iOS draws it as emoji.
  if (code >= 0xe000 && code <= 0xe00f) return { value: "", next: i + 1 };
  return { value: raw, next: i + 1 };
}

/** The parse of one LaTeX string: where it has read to, and what it has built. */
type LatexState = { input: string; depth: number; i: number; out: MathSegment[] };

function pushText(state: LatexState, raw: string): void {
  const value = restoreNativeLiterals(raw)
    .split(NATIVE_UPRIGHT_START_MARKER).join("")
    .split(NATIVE_UPRIGHT_END_MARKER).join("");
  if (!value) return;
  const last = state.out[state.out.length - 1];
  if (last?.type === "text") last.value += value;
  else state.out.push({ type: "text", value });
}

/** A nested parse's text joins the current run; its structures stay segments. */
function pushParsed(state: LatexState, segments: MathSegment[]): void {
  for (const seg of segments) {
    if (seg.type === "text") pushText(state, seg.value);
    else state.out.push(seg);
  }
}

function pushScript(state: LatexState, kind: "sup" | "sub", inner: MathSegment[]): void {
  const plain = plainScriptPieces(inner);
  state.out.push(plain == null ? { type: kind, value: "", body: inner } : { type: kind, value: plain });
}

/** `\frac`, `\sqrt`, `\cancel` and the accents, from `LATEX_HANDLERS`. */
function readCommand(state: LatexState): boolean {
  const word = /^[a-zA-Z]+/.exec(state.input.slice(state.i + 1))?.[0];
  const name = word ? commandName(word) : undefined;
  if (!name) return false;
  const parsed = LATEX_HANDLERS[name]({ input: state.input, start: state.i, depth: state.depth, name });
  if (!parsed) return false;
  state.out.push(parsed.seg);
  state.i = parsed.next;
  return true;
}

/** Unescaped braces are TeX grouping syntax, not visible glyphs. SymPy
 * emits them around atoms inside scalable delimiters (for example
 * `\\left|{x}\\right|`). Parse their contents recursively so every such
 * expression renders as normal math, while escaped `\\{` / `\\}` still
 * take the literal-character path for sets. */
function readBraceGroup(state: LatexState): boolean {
  const group = readGroup(state.input, state.i);
  if (!group) return false;
  pushParsed(state, parseSimpleLatex(group.value, state.depth + 1));
  state.i = group.next;
  return true;
}

function readUprightRun(state: LatexState): boolean {
  const end = state.input.indexOf(NATIVE_UPRIGHT_END_MARKER, state.i + 1);
  if (end < 0) return false;
  state.out.push({ type: "upright", value: restoreNativeLiterals(state.input.slice(state.i + 1, end)) });
  state.i = end + 1;
  return true;
}

/** TeX ignores spaces between `^`/`_` and the atom. One character here used
 * to be a private-use brace or the backslash of `\mathbf` / `\textit`. */
function readScript(state: LatexState, kind: "sup" | "sub"): void {
  const { input, depth } = state;
  state.i += 1;
  while (input[state.i] === " ") state.i += 1;
  const marked = readMarkedUpright(input, state.i);
  if (marked) {
    state.out.push({ type: kind, value: "", body: [{ type: "upright", value: marked.value }] });
    state.i = marked.next;
    return;
  }
  const group = input[state.i] === "{" ? readGroup(input, state.i) : null;
  if (group) {
    pushScript(state, kind, parseSimpleLatex(group.value, depth + 1));
    state.i = group.next;
    return;
  }
  const leading = readLeadingAtom(input, state.i, depth);
  if (leading) {
    pushScript(state, kind, leading.body);
    state.i = leading.next;
    return;
  }
  const bare = readBareScript(input, state.i);
  if (bare.value) state.out.push({ type: kind, value: bare.value });
  state.i = bare.next > state.i ? bare.next : state.i + 1;
}

/** Any other `\name`, `\|` or escaped character. A function keeps readable notation;
 * a name with no table entry is never drawn (its argument is) and is reported. */
function readEscape(state: LatexState): boolean {
  const { input } = state;
  const rest = input.slice(state.i + 1);
  const cmd = rest.match(/^[a-zA-Z]+/)?.[0];
  if (cmd) {
    state.i += cmd.length + 1;
    const kind = latexNameKind(cmd);
    if (kind === "symbol") {
      pushText(state, symbolGlyph(cmd));
      return true;
    }
    let argStart = state.i;
    while (input[argStart] === " ") argStart += 1;
    const group = input[argStart] === "{" ? readGroup(input, argStart) : null;
    const word = kind === "function" || kind === "operator";
    if (kind === "function") pushNamedFunction(state.out, cmd, group ? null : input.slice(state.i));
    else if (kind === "operator") pushText(state, operatorWord(cmd));
    else if (kind === "unknown" && !commandName(cmd)) reportUnknownLatexCommand(cmd);
    if (!group) return true;
    if (word) pushText(state, "(");
    pushParsed(state, parseSimpleLatex(group.value, state.depth + 1));
    if (word) pushText(state, ")");
    state.i = group.next;
    return true;
  }
  // `\|` is a norm bar. U+2016 is not in KaTeX_Main; the renderer draws
  // two `|` glyphs. A single escaped bar stays one `|`.
  if (rest[0] === "|") {
    pushText(state, "‖");
    state.i += 2;
    return true;
  }
  // `\{` `\%` `\_` — emit the escaped character, not a stray backslash.
  if (!rest[0]) return false;
  pushText(state, rest[0]);
  state.i += 2;
  return true;
}

/** One piece at `state.i`; a reader that declines leaves it to the next. */
function readNext(state: LatexState): void {
  const ch = state.input[state.i];
  if (ch === "\\" && readCommand(state)) return;
  if (ch === NATIVE_LITERAL_LEFT_BRACE_MARKER || ch === NATIVE_LITERAL_RIGHT_BRACE_MARKER) {
    pushText(state, ch === NATIVE_LITERAL_LEFT_BRACE_MARKER ? "{" : "}");
    state.i += 1;
    return;
  }
  if (ch === "{" && readBraceGroup(state)) return;
  if (ch === "}") {
    state.i += 1;
    return;
  }
  if (ch === NATIVE_UPRIGHT_START_MARKER && readUprightRun(state)) return;
  if (ch === "^" || ch === "_") return readScript(state, ch === "^" ? "sup" : "sub");
  if (ch === "\\" && readEscape(state)) return;
  pushText(state, ch);
  state.i += 1;
}

export function parseSimpleLatex(latex: string, depth = 0): MathSegment[] {
  if (depth > MAX_MATH_NEST_DEPTH) {
    return [{ type: "text", value: latex.replace(/\\[A-Za-z]+|[\\{}]/g, "") }];
  }
  const state: LatexState = { input: preprocessLatex(latex), depth, i: 0, out: [] };
  while (state.i < state.input.length) readNext(state);
  // Nothing drawn (a lone `\displaystyle`, an unknown name): never the source.
  return state.out.length ? state.out : [{ type: "text", value: "" }];
}

export function segmentsToPlain(segments: MathSegment[]): string {
  return segments.map(segmentToPlain).join("");
}

/** The formula as plain words (a screen reader's label), never a leftover `\\command`. */
export function readableLatexFallback(latex: string): string {
  const plain = segmentsToPlain(parseSimpleLatex(latex));
  return plain.replace(/\\[a-zA-Z]+/g, (cmd) => cmd.slice(1));
}

