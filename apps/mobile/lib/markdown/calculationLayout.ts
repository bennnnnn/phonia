/**
 * One logical reasoning state per math row.
 * The API's twin is apps/api/app/modules/chat/calculation_layout.py;
 * docs/fixtures/presentation_cases.json holds both to the same output.
 */

import {
  continuesSentence,
  convertsUnits,
  finishInline,
  keepHardBreak,
  readsAsProse,
} from "@/lib/markdown/calculationLayoutTail";
import { isMathFenceLang } from "@/lib/fenceRegistry";
import { codeSpanOpensWithin, escapedAt } from "@/lib/markdown/inlineCode";
import { displayMathLines, leaveProseLine, rewriteFenced } from "@/lib/markdown/markdownRegions";
import { charAt, LETTER } from "@/lib/markdown/unicodeChars";
import { readFenceMarker } from "@/lib/mdFenceScan";

const TEXT_COMMANDS = new Set([
  "text",
  "mathrm",
  "mathbf",
  "textrm",
  "operatorname",
  "textbf",
  "mbox",
]);
const NUMERIC_COMMANDS = new Set([
  "times",
  "cdot",
  "div",
  "left",
  "right",
  "pm",
  "mp",
  "cdotp",
  "quad",
  "qquad",
]);
const CHAIN_STOP_COMMANDS = new Set([
  "rightarrow",
  "leftarrow",
  "Rightarrow",
  "Leftarrow",
  "to",
  "implies",
  "iff",
  "Leftrightarrow",
  "mapsto",
  "quad",
  "qquad",
]);
const CHAIN_STOP_WORDS = new Set(["or", "and"]);
const TRAILING_PUNCT = new Set([...".,;:!?"]);

type Tok = { kind: string; start: number; end: number; top: boolean };

function commandEnd(text: string, index: number): { name: string; end: number } {
  let cursor = index + 1;
  if (cursor >= text.length) return { name: "", end: cursor };
  if (/[A-Za-z]/.test(text[cursor])) {
    const start = cursor;
    cursor += 1;
    while (cursor < text.length && /[A-Za-z]/.test(text[cursor])) cursor += 1;
    return { name: text.slice(start, cursor), end: cursor };
  }
  return { name: text[cursor], end: cursor + 1 };
}

// `1,500`: a digit, the comma, then exactly three digits. `10, 2x` is two equations:
// read as one number it joined `x + y = 10, 2x - y = 5` into a chain stating `x + y = 5`.
function thousandsSeparator(expr: string, index: number): boolean {
  const prev = index > 0 ? expr[index - 1] : "";
  return /\d/.test(prev) && /^\d{3}(?!\d)/.test(expr.slice(index + 1, index + 5));
}

function breakEnd(expr: string, index: number): number {
  let cursor = index + 1;
  while (cursor < expr.length && expr[cursor] === " ") cursor += 1;
  if (expr.startsWith("\\quad", cursor) || expr.startsWith("\\qquad", cursor)) {
    return commandEnd(expr, cursor).end;
  }
  return index + 1;
}

function tokenize(expr: string): Tok[] {
  const out: Tok[] = [];
  let brace = 0;
  let paren = 0;
  let bracket = 0;
  let index = 0;
  while (index < expr.length) {
    const top = brace === 0 && paren === 0 && bracket === 0;
    const char = expr[index];
    if (char === "\\") {
      const { name, end } = commandEnd(expr, index);
      let kind = "command";
      if (name === "approx") kind = "approx";
      else if (name === "quad" || name === "qquad") kind = "break";
      out.push({ kind, start: index, end, top });
      index = end;
      continue;
    }
    if (char === "{") brace += 1;
    else if (char === "}") brace = Math.max(0, brace - 1);
    else if (char === "(") paren += 1;
    else if (char === ")") paren = Math.max(0, paren - 1);
    else if (char === "[") bracket += 1;
    else if (char === "]") bracket = Math.max(0, bracket - 1);
    else if (char === "=" && top) out.push({ kind: "equals", start: index, end: index + 1, top: true });
    else if (char === "," && top && !thousandsSeparator(expr, index)) {
      const end = breakEnd(expr, index);
      out.push({ kind: "break", start: index, end, top: true });
      index = end;
      continue;
    }
    index += 1;
  }
  return out;
}

function hasTopEquals(expr: string): boolean {
  return tokenize(expr).some((tok) => tok.kind === "equals" && tok.top);
}

function independentPieces(expr: string): string[] | null {
  const breaks = tokenize(expr).filter((tok) => tok.kind === "break" && tok.top);
  if (breaks.length === 0) return null;
  const pieces: string[] = [];
  let start = 0;
  for (const tok of breaks) {
    const piece = expr.slice(start, tok.start).trim();
    if (piece) pieces.push(piece);
    start = tok.end;
  }
  const tail = expr.slice(start).trim();
  if (tail) pieces.push(tail);
  if (pieces.length < 2 || !pieces.every(hasTopEquals)) return null;
  return pieces;
}

function segmentBlocksChain(segment: string): boolean {
  let index = 0;
  while (index < segment.length) {
    if (segment[index] === "\\") {
      const { name, end } = commandEnd(segment, index);
      if (CHAIN_STOP_COMMANDS.has(name)) return true;
      index = end;
      continue;
    }
    // A word (in any script) is read whole; only "or" and "and" stop a chain.
    const start = index;
    while (LETTER.test(charAt(segment, index))) index += charAt(segment, index).length;
    if (CHAIN_STOP_WORDS.has(segment.slice(start, index).toLowerCase())) return true;
    if (index === start) index += charAt(segment, index).length;
  }
  return false;
}

function isSimpleNumeric(segment: string): boolean {
  let index = 0;
  while (index < segment.length) {
    if (segment[index] === "\\") {
      const { name, end } = commandEnd(segment, index);
      if (TEXT_COMMANDS.has(name)) {
        // A unit or label is a different quantity, not a factorial expansion.
        return false;
      }
      if (NUMERIC_COMMANDS.has(name) || !LETTER.test(name)) {
        index = end;
        continue;
      }
      return false;
    }
    const char = charAt(segment, index);
    if (LETTER.test(char)) return false;
    index += char.length;
  }
  return true;
}

function equalsChain(expr: string): string[] | null {
  const ops = tokenize(expr).filter((tok) => tok.top && (tok.kind === "equals" || tok.kind === "approx"));
  if (ops.length < 2) return null;
  const segments: string[] = [];
  let start = 0;
  for (const op of ops) {
    segments.push(expr.slice(start, op.start));
    start = op.end;
  }
  segments.push(expr.slice(start));
  if (segments.some((part) => !part.trim())) return null;
  if (segments.slice(1, -1).some(segmentBlocksChain)) return null;
  if (segments.every(isSimpleNumeric) || convertsUnits(segments)) return null;
  const lhs = segments[0].trim();
  return segments.slice(1).map((rhs, index) => {
    const op = ops[index].kind === "approx" ? "\\approx" : "=";
    return `${lhs} ${op} ${rhs.trim()}`;
  });
}

function splitMathExpression(expr: string): string[] | null {
  const body = expr.trim();
  if (!body || body.includes("\\begin{") || body.includes("&")) return null;
  const pieces = independentPieces(body);
  if (pieces) {
    const rows = pieces.flatMap((piece) => equalsChain(piece) ?? [piece.trim()]);
    return rows.length >= 2 ? rows : null;
  }
  return equalsChain(body);
}

function joinRows(rows: string[], delim: string, punct = ""): string {
  const lines = rows.map((row) => `${delim}${row}${delim}`);
  if (punct) lines[lines.length - 1] += punct;
  if (lines.length === 1) return lines[0];
  return lines.map((line, index) => (index < lines.length - 1 ? `${line}  ` : line)).join("\n");
}

function peelPunct(text: string): { core: string; punct: string } {
  let punct = "";
  let core = text;
  while (core && TRAILING_PUNCT.has(core[core.length - 1])) {
    punct = core[core.length - 1] + punct;
    core = core.slice(0, -1).trimEnd();
  }
  return { core, punct };
}

function soleMath(stripped: string): { delim: string; inner: string; punct: string } | null {
  const { core, punct } = peelPunct(stripped);
  if (core.startsWith("$$") && core.endsWith("$$") && core.length > 4) {
    const inner = core.slice(2, -2).trim();
    if (inner && !inner.includes("$$")) return { delim: "$$", inner, punct };
  }
  if (
    core.length > 2 &&
    core.startsWith("$") &&
    core.endsWith("$") &&
    !core.startsWith("$$") &&
    !core.slice(1, -1).includes("$")
  ) {
    const inner = core.slice(1, -1).trim();
    if (inner) return { delim: "$", inner, punct };
  }
  return null;
}

function readCodeEnd(text: string, index: number): number | null {
  let length = 0;
  while (index + length < text.length && text[index + length] === "`") length += 1;
  if (length === 0) return null;
  const close = text.indexOf("`".repeat(length), index + length);
  if (close < 0 || close === index + length || text.slice(index + length, close).includes("\n")) {
    return null;
  }
  return close + length;
}

/**
 * The `$...$` span opening at `index`. A pair never reaches across an inline
 * code span, or splitting the "chain" at its `=` signs rewrites the code
 * between the dollars. A bare number (`$2$`) is a span, so its closer cannot
 * open a new one with the next dollar on the line.
 */
function readMathSpan(
  text: string,
  index: number,
): { delim: string; inner: string; end: number } | null {
  if (text.startsWith("$$", index)) {
    const close = text.indexOf("$$", index + 2);
    if (close < 0 || close === index + 2 || text.slice(index + 2, close).includes("\n")) return null;
    if (codeSpanOpensWithin(text, index + 2, close)) return null;
    return { delim: "$$", inner: text.slice(index + 2, close).trim(), end: close + 2 };
  }
  if (text[index] !== "$") return null;
  const close = text.indexOf("$", index + 1);
  if (close < 0 || text.slice(index + 1, close).includes("\n")) return null;
  if (text[close + 1] === "$") return null;
  if (codeSpanOpensWithin(text, index + 1, close)) return null;
  const inner = text.slice(index + 1, close);
  if (!inner.trim()) return null;
  const bareNumber = /^\s*\d[\d,]*(?:\.\d+)?\s*$/.test(inner) && !/\d/.test(text[close + 1] ?? "");
  if (/^\d/.test(inner) && !/[\\=^_]/.test(inner) && !bareNumber) return null;
  return { delim: "$", inner: inner.trim(), end: close + 1 };
}

function layoutInline(body: string): string {
  const parts: string[] = [];
  let buf = "";
  let changed = false;
  let index = 0;
  while (index < body.length) {
    if (body[index] === "\\") {
      const end = commandEnd(body, index).end;
      buf += body.slice(index, end);
      index = end;
      continue;
    }
    if (body[index] === "`") {
      const end = readCodeEnd(body, index);
      if (end == null) {
        buf += body[index];
        index += 1;
      } else {
        buf += body.slice(index, end);
        index = end;
      }
      continue;
    }
    const span = readMathSpan(body, index);
    if (!span) {
      buf += body[index];
      index += 1;
      continue;
    }
    const rows = splitMathExpression(span.inner);
    if (!rows || continuesSentence(body.slice(span.end))) {
      buf += body.slice(index, span.end);
      index = span.end;
      continue;
    }
    changed = true;
    if (buf.trim()) parts.push(buf.trimEnd());
    buf = "";
    let cursor = span.end;
    while (cursor < body.length && TRAILING_PUNCT.has(body[cursor])) cursor += 1;
    parts.push(joinRows(rows, span.delim, body.slice(span.end, cursor)));
    index = cursor;
  }
  if (!changed) return body;
  return finishInline(parts, buf);
}

function withIndent(body: string, joined: string): string {
  const indent = body.slice(0, body.length - body.trimStart().length);
  if (!indent) return joined;
  return joined
    .split("\n")
    .map((line) => indent + line)
    .join("\n");
}

function plainChain(body: string): string | null {
  if (readsAsProse(body)) return null;
  const { core, punct } = peelPunct(body.trim());
  const rows = splitMathExpression(core);
  if (!rows) return null;
  return joinRows(rows, "$", punct);
}

function layoutBody(body: string): string {
  const stripped = body.trim();
  const sole = stripped ? soleMath(stripped) : null;
  if (sole) {
    const rows = splitMathExpression(sole.inner);
    if (!rows) return body;
    return withIndent(body, keepHardBreak(body, joinRows(rows, sole.delim, sole.punct)));
  }
  // A closed \[...\] on one line is one display formula, drawn as a maths block.
  if (!body.includes("$") && !body.includes("`") && !body.includes("\\[")) {
    const plain = plainChain(body);
    if (plain != null) return withIndent(body, plain);
  }
  return layoutInline(body);
}

function listPrefix(line: string): { prefix: string; body: string } {
  let index = 0;
  while (index < line.length && line[index] === " ") index += 1;
  const rest = line.slice(index);
  for (const marker of ["- ", "* ", "+ "]) {
    if (rest.startsWith(marker)) {
      return { prefix: line.slice(0, index + 2), body: rest.slice(2) };
    }
  }
  let digits = 0;
  while (digits < rest.length && /\d/.test(rest[digits])) digits += 1;
  if (digits > 0 && digits <= 3 && rest.slice(digits, digits + 2) === ". ") {
    return { prefix: line.slice(0, index + digits + 2), body: rest.slice(digits + 2) };
  }
  return { prefix: "", body: line };
}

function layoutLine(line: string): string {
  if (leaveProseLine(line)) return line;
  const stripped = line.trimStart();
  if (stripped.startsWith("|") || stripped.startsWith("#")) return line;
  const { prefix, body } = listPrefix(line);
  const laid = layoutBody(body);
  if (laid === body) return line;
  if (!prefix) return laid;
  const pad = " ".repeat(prefix.length);
  return laid
    .split("\n")
    .map((row, index) => (index === 0 ? prefix + row : pad + row))
    .join("\n");
}

function interiorLineBlocksFold(line: string): boolean {
  if (leaveProseLine(line)) return true;
  const stripped = line.trimStart();
  if (!stripped) return false;
  if (
    stripped.startsWith("|") ||
    stripped.startsWith("#") ||
    readFenceMarker(stripped) != null ||
    stripped.startsWith("- ") ||
    stripped.startsWith("* ") ||
    stripped.startsWith("+ ")
  ) {
    return true;
  }
  let digits = 0;
  while (digits < stripped.length && /\d/.test(stripped[digits])) digits += 1;
  return digits > 0 && digits <= 3 && stripped.slice(digits, digits + 2) === ". ";
}

function spanCrossesPreservedLine(text: string, start: number, close: number): boolean {
  const lineStart = text.lastIndexOf("\n", start - 1) + 1;
  const lines = text.slice(lineStart, close).split("\n");
  if (lines[0] && leaveProseLine(lines[0])) return true;
  return lines.slice(1).some(interiorLineBlocksFold);
}

function findParenCloser(text: string, start: number): number | null {
  let index = start;
  while (index < text.length) {
    if (text[index] === "`") {
      const codeEnd = readCodeEnd(text, index);
      if (codeEnd != null) {
        index = codeEnd;
        continue;
      }
    }
    if (text.startsWith("\\)", index) && !escapedAt(text, index)) return index;
    index += 1;
  }
  return null;
}

/** Turn a finished \\(...\\) into `$...$` so a chain can split.
 * An opener with no closer stays literal so a live tail does not gain `$`. */
function foldClosedParenMath(text: string): string {
  if (!text.includes("\\(")) return text;
  let out = "";
  let index = 0;
  while (index < text.length) {
    if (text[index] === "`") {
      const codeEnd = readCodeEnd(text, index);
      if (codeEnd != null) {
        out += text.slice(index, codeEnd);
        index = codeEnd;
        continue;
      }
    }
    if (text.startsWith("\\(", index) && !escapedAt(text, index)) {
      const close = findParenCloser(text, index + 2);
      if (close == null) {
        out += text.slice(index);
        break;
      }
      if (spanCrossesPreservedLine(text, index, close)) {
        out += text.slice(index, close + 2);
        index = close + 2;
        continue;
      }
      let raw = text.slice(index + 2, close);
      if (raw.includes("\n") || raw.includes("\r")) {
        raw = raw.split(/\r?\n/).map((line) => line.trim()).join(" ");
      }
      out += raw.trim() ? `$${raw}$` : text.slice(index, close + 2);
      index = close + 2;
      continue;
    }
    out += text[index];
    index += 1;
  }
  return out;
}

function layoutProse(prose: string): string {
  const lines = foldClosedParenMath(prose).split("\n");
  const kept = displayMathLines(lines);
  return lines.map((line, index) => (kept[index] ? line : layoutLine(line))).join("\n");
}

function unwrapMathLine(line: string): string {
  const sole = soleMath(line.trim());
  return sole ? sole.inner : line.trim();
}

function rewriteMathFence(opener: string, body: string): string | null {
  const marker = readFenceMarker(opener);
  const lang = marker?.info.split(/\s+/)[0]?.toLowerCase() ?? "";
  if (!isMathFenceLang(lang) && lang !== "equation") return null;
  const physical = body.split("\n").filter((line) => line.trim());
  if (physical.length === 0) return null;
  const rows: string[] = [];
  let changed = false;
  for (const line of physical) {
    const inner = unwrapMathLine(line);
    const split = splitMathExpression(inner);
    if (split) {
      changed = true;
      rows.push(...split);
    } else {
      rows.push(inner);
    }
  }
  if (!changed) return null;
  return joinRows(rows, "$");
}

export function layoutCalculations(text: string): string {
  if (!text) return text;
  return rewriteFenced(text, layoutProse, rewriteMathFence);
}
