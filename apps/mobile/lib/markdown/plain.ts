/** Copy vs speech conversion of assistant markdown (do not import printDocument). */

import { splitAnswerNotation } from "@/lib/answerNotation";
import { closesFence, readFenceMarker } from "@/lib/mdFenceScan";
import {
  type FencePlainReader,
  fenceIdForLang,
  isChartFenceLang,
  isControlFenceLang,
  isMathFenceLang,
  isVisualDiagramFenceLang,
  fenceSpecForLang,
} from "@/lib/fenceRegistry";
import { clarifyText, parseClarifyCard } from "@/lib/clarify/clarifyCard";
import { arrayCardText, quizCardText } from "@/lib/lesson/cardBody";
import { plainFenceText } from "@/lib/lesson/lessonFences";
import { teachingSpeech } from "@/lib/math/teachingBlock";
import {
  DEGREE_RING,
  parseSimpleLatex,
  segmentsToPlain,
  type MathAccentKind,
  type MathSegment,
} from "@/lib/math/text";
import { looksLikePipeRow } from "@/lib/markdown/streamTableHold";

/** Walk prose and fenced blocks, converting each; the fence's markers are not kept. */
export function mapFenceRegions(
  text: string,
  onProse: (prose: string) => string,
  onFence: (lang: string, body: string) => string,
): string {
  const lines = text.split("\n");
  const out: string[] = [];
  let prose: string[] = [];
  let fence: { char: "`" | "~"; len: number; lang: string; body: string[] } | null = null;

  const flushProse = () => {
    if (prose.length === 0) return;
    const converted = onProse(prose.join("\n"));
    if (converted.length > 0) out.push(converted);
    prose = [];
  };

  const flushFence = () => {
    if (!fence) return;
    const converted = onFence(fence.lang, fence.body.join("\n"));
    if (converted.length > 0) out.push(converted);
    fence = null;
  };

  for (const line of lines) {
    const marker = readFenceMarker(line);
    if (fence) {
      if (marker && closesFence(marker, fence)) {
        flushFence();
        continue;
      }
      fence.body.push(line);
      continue;
    }
    if (marker && !marker.info.includes("|")) {
      flushProse();
      fence = {
        char: marker.char,
        len: marker.len,
        lang: (marker.info.split(/\s/)[0] ?? "").toLowerCase(),
        body: [],
      };
      continue;
    }
    prose.push(line);
  }
  flushFence();
  flushProse();
  return out.join("\n");
}

function pipeTablesToPlain(text: string): string {
  const lines = text.split("\n");
  const out: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i] ?? "";
    if (looksLikePipeRow(line)) {
      const rows: string[] = [];
      while (i < lines.length && looksLikePipeRow(lines[i] ?? "")) {
        const cells = (lines[i] ?? "")
          .split("|")
          .map((c) => c.trim())
          .filter(Boolean);
        if (!cells.every((c) => /^:?-+:?$/.test(c))) {
          rows.push(cells.join(" — "));
        }
        i += 1;
      }
      out.push(rows.join("\n"));
      continue;
    }
    out.push(line);
    i += 1;
  }
  return out.join("\n");
}

function unwrapDelimited(text: string, delim: string): string {
  let out = "";
  let i = 0;
  const n = delim.length;
  while (i < text.length) {
    if (text.startsWith(delim, i)) {
      const close = text.indexOf(delim, i + n);
      if (close < 0) {
        out += text.slice(i);
        break;
      }
      if (!text.slice(i, close).includes("\n") || n > 1) {
        out += text.slice(i + n, close);
        i = close + n;
        continue;
      }
    }
    out += text[i];
    i += 1;
  }
  return out;
}

/** Paired `_italic_` / `*italic*` only at word edges — never `user_id` or `a * b`. */
function unwrapWordEdgeMarker(text: string, marker: string): string {
  let out = "";
  let i = 0;
  while (i < text.length) {
    if (text[i] !== marker) {
      out += text[i];
      i += 1;
      continue;
    }
    const prev = i === 0 ? "" : text[i - 1] ?? "";
    const next = text[i + 1] ?? "";
    const openOk = !/[A-Za-z0-9]/.test(prev) && next !== "" && next !== marker && next !== " ";
    if (!openOk) {
      out += text[i];
      i += 1;
      continue;
    }
    const close = text.indexOf(marker, i + 1);
    if (close < 0 || text.slice(i, close).includes("\n")) {
      out += text[i];
      i += 1;
      continue;
    }
    const after = text[close + 1] ?? "";
    const inner = text.slice(i + 1, close);
    const closeOk = inner.length > 0 && inner[inner.length - 1] !== " " && !/[A-Za-z0-9]/.test(after);
    if (!closeOk) {
      out += text[i];
      i += 1;
      continue;
    }
    out += inner;
    i = close + 1;
  }
  return out;
}

function stripMarkdownChrome(text: string): string {
  let out = text.replace(/!\[[^\]]*\]\([^)]+\)/g, " ");
  out = out.replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1");
  out = out.replace(/^#{1,6}\s+/gm, "");
  out = out.replace(/^>\s?/gm, "");
  out = out.replace(/^(\s*)[-+]\s+/gm, "$1• ");
  // Whole-message Copy must preserve sequence/rank and nested indentation.
  // Removing `1.`, `2.`, `3.` turned copied procedures into unordered lines.
  out = out.replace(/^(\s*)(\d+)\.\s+/gm, "$1$2. ");
  out = unwrapDelimited(out, "**");
  out = unwrapDelimited(out, "__");
  out = unwrapDelimited(out, "~~");
  out = unwrapDelimited(out, "`");
  out = unwrapWordEdgeMarker(out, "_");
  out = unwrapWordEdgeMarker(out, "*");
  out = out.replace(/^(\s*)\*\s+/gm, "$1• ");
  return out;
}

const MAX_SPEAK_MATH_DEPTH = 12;

const ACCENT_WORD: Record<MathAccentKind, string> = {
  overline: "bar",
  underline: "underlined",
  hat: "hat",
  tilde: "tilde",
  vec: "vector",
  vecLeft: "vector",
  bar: "bar",
  dot: "dot",
  ddot: "double dot",
};

/** Spoken operators. The parser has already turned `\times` into `×`. */
function speakPlainMath(value: string): string {
  let out = value
    .replaceAll("±", " plus or minus ")
    .replaceAll("×", " times ")
    .replaceAll("⋅", " dot ")
    .replaceAll("·", " dot ");
  if (out.includes("\\")) {
    out = out
      .replace(/\\frac\{([^{}]+)\}\{([^{}]+)\}/g, "$1 over $2")
      .replace(/\\sqrt\{([^{}]+)\}/g, "the square root of $1")
      .replace(/\\times(?![a-zA-Z])/g, " times ")
      .replace(/\\cdot(?![a-zA-Z])/g, " dot ")
      .replace(/\\pm(?![a-zA-Z])/g, " plus or minus ")
      .replace(/\\[a-zA-Z]+/g, " ")
      .replace(/[{}]/g, "");
  }
  return out;
}

function speakScript(value: string, depth: number, kind: "sup" | "sub"): string {
  const spoken = (
    depth >= MAX_SPEAK_MATH_DEPTH ? value : speakMathSegments(parseSimpleLatex(value), depth + 1)
  ).trim();
  if (!spoken) return "";
  if (kind === "sub") return ` subscript ${spoken}`;
  // `30^\circ` is thirty degrees, never a power.
  if (spoken === DEGREE_RING) return " degrees";
  if (spoken === "2") return " squared";
  if (spoken === "3") return " cubed";
  return ` to the power of ${spoken}`;
}

/** Read-aloud walks the same segments as copy. A `[^}]+` fraction regex
 * never matches `x^{2}`, and stripping the leftover braces speaks `fracx^24`. */
function speakMathSegments(segments: MathSegment[], depth = 0): string {
  if (depth > MAX_SPEAK_MATH_DEPTH) {
    return segments.map((segment) => ("value" in segment ? segment.value : "")).join(" ");
  }
  return segments.map((segment) => {
    switch (segment.type) {
      case "text":
      case "upright":
        return speakPlainMath(segment.value);
      case "sup":
      case "sub": {
        const spoken = segment.body
          ? speakMathSegments(segment.body, depth + 1).trim()
          : segment.value;
        return speakScript(spoken, depth, segment.type);
      }
      case "frac": {
        const num = speakMathSegments(segment.num, depth + 1).trim();
        const den = speakMathSegments(segment.den, depth + 1).trim();
        return `${num} over ${den}`;
      }
      case "sqrt": {
        const body = speakMathSegments(segment.body, depth + 1).trim();
        const degree = segment.index
          ? speakMathSegments(segment.index, depth + 1).trim()
          : segment.degree
            ? speakMathSegments(parseSimpleLatex(segment.degree), depth + 1).trim()
            : "";
        if (!degree) return `the square root of ${body}`;
        if (degree === "3") return `the cube root of ${body}`;
        return `the ${degree} root of ${body}`;
      }
      case "cancel":
        return speakMathSegments(segment.body, depth + 1);
      case "accent": {
        const body = speakMathSegments(segment.body, depth + 1).trim();
        return `${body} ${ACCENT_WORD[segment.kind]}`;
      }
      default: {
        const _exhaustive: never = segment;
        return _exhaustive;
      }
    }
  }).join("");
}

function speakMath(latex: string): string {
  return speakMathSegments(parseSimpleLatex(latex)).replace(/\s+/g, " ").trim();
}

/** Copy needs explicit grouping; visual fraction bars and radical overbars vanish. */
function copyMathSegments(segments: MathSegment[], depth = 0): string {
  const fractionSide = (side: MathSegment[]): string => {
    const text = copyMathSegments(side, depth + 1).trim();
    return side.length === 1 && (side[0]?.type === "text" || side[0]?.type === "upright")
      && /^(?:[+-]?\d+(?:\.\d+)?|\p{L})$/u.test(text)
      ? text : `(${text})`;
  };
  return segments.map((segment, index) => {
    switch (segment.type) {
      case "text": return segment.value;
      case "upright": return segment.value;
      case "sup":
      case "sub": {
        if (segment.type === "sup" && !segment.body && segment.value === DEGREE_RING) return "°";
        const value = segment.body
          ? copyMathSegments(segment.body, depth + 1)
          : depth >= 12
            ? segment.value
            : copyMathSegments(parseSimpleLatex(segment.value), depth + 1);
        return `${segment.type === "sup" ? "^" : "_"}${value.length === 1 ? value : `{${value}}`}`;
      }
      case "frac": {
        const fraction = `${fractionSide(segment.num)}/${fractionSide(segment.den)}`;
        const next = segments[index + 1];
        return next?.type === "sup" || next?.type === "sub" ? `(${fraction})` : fraction;
      }
      case "sqrt": {
        const index = segment.index
          ? `[${copyMathSegments(segment.index, depth + 1)}]`
          : segment.degree
            ? `[${copyMathSegments(parseSimpleLatex(segment.degree), depth + 1)}]`
            : "";
        return `√${index}(${copyMathSegments(segment.body, depth + 1)})`;
      }
      case "cancel":
        return copyMathSegments(segment.body, depth + 1);
      case "accent":
        return segmentsToPlain([segment]);
    }
  }).join("");
}

/** Native script segment values flatten structure; keep the original formula
 * when those values cannot be serialized without losing grouping. */
function hasStructuredScript(latex: string): boolean {
  for (let i = 0; i < latex.length; i += 1) {
    if (latex[i] !== "^" && latex[i] !== "_") continue;
    let open = i + 1;
    while (/\s/.test(latex[open] ?? "") && open < latex.length) open += 1;
    if (latex[open] !== "{") continue;
    let depth = 1;
    let close = open + 1;
    for (; close < latex.length; close += 1) {
      if (latex[close] === "\\") { close += 1; continue; }
      if (latex[close] === "{") depth += 1;
      else if (latex[close] === "}") depth -= 1;
      if (depth === 0) break;
    }
    if (depth !== 0 || /\\(?:[dct]?frac|sqrt)\b|[_^]/.test(latex.slice(open + 1, close))) return true;
    i = close;
  }
  return false;
}

function copyMath(latex: string): string {
  if (hasStructuredScript(latex)) return latex.trim();
  return copyMathSegments(parseSimpleLatex(latex)).replace(/\$/g, "").trim();
}

function isMathDollarInner(inner: string): boolean {
  const t = inner.trim();
  if (!t) return false;
  if (/\\[a-zA-Z]/.test(t) || /[\^=_]/.test(t)) return true;
  if (/[=<>]/.test(t)) return true;
  if (/^[A-Za-z]$/.test(t)) return true;
  return /\d/.test(t) && /[+\-*/]/.test(t);
}

function rewriteInlineMath(text: string, convert: (latex: string) => string): string {
  let out = "";
  let i = 0;
  while (i < text.length) {
    if (text.startsWith("$$", i)) {
      const close = text.indexOf("$$", i + 2);
      if (close < 0) {
        out += text[i];
        i += 1;
        continue;
      }
      out += convert(text.slice(i + 2, close));
      i = close + 2;
      continue;
    }
    if (text[i] !== "$") {
      out += text[i];
      i += 1;
      continue;
    }
    const close = text.indexOf("$", i + 1);
    if (close < 0 || text.slice(i + 1, close).includes("\n")) {
      out += text[i];
      i += 1;
      continue;
    }
    const inner = text.slice(i + 1, close);
    if (isMathDollarInner(inner)) {
      out += convert(inner);
      i = close + 1;
      continue;
    }
    out += text[i];
    i += 1;
  }
  return out;
}

function convertProse(prose: string, mode: "copy" | "speech"): string {
  let text = pipeTablesToPlain(prose);
  text = stripMarkdownChrome(text);
  if (mode === "speech") text = rewriteInlineMath(text, speakMath);
  else text = rewriteInlineMath(text, copyMath);
  return text;
}

type PlainMode = "copy" | "speech";

/** Each registry `plainReader`: the body's own text, or null to fall to its `plainText` rule. */
const PLAIN_READERS: Record<FencePlainReader, (body: string, mode: PlainMode) => string | null> = {
  // A teaching picture speaks its worked lines; without them it is a diagram like any other.
  worked: (body, mode) => {
    const spoken = teachingSpeech(body);
    return spoken ? withTexRuns(spoken, mode === "speech" ? speakMath : copyMath) : null;
  },
  // Each reads what its card shows: a plain-text body as that text, never a quiz's answer.
  quiz: quizCardText,
  clarify: (body) => {
    const card = parseClarifyCard(body);
    return card ? clarifyText(card) : (plainFenceText(body) ?? "");
  },
  array: arrayCardText,
};

function convertFence(lang: string, body: string, mode: PlainMode): string {
  const trimmed = body.replace(/\n$/, "").trim();
  if (isControlFenceLang(lang)) return "";
  const reader = fenceSpecForLang(lang)?.plainReader;
  const read = reader ? PLAIN_READERS[reader](trimmed, mode) : null;
  if (read !== null) return read;
  if (isChartFenceLang(lang)) return mode === "speech" ? "a chart" : "";
  const id = fenceIdForLang(lang);
  if (isVisualDiagramFenceLang(lang)) return mode === "speech" ? "a diagram" : "";
  if (id === "answer") {
    // A chemistry answer is text (H₂O, Fe³⁺, →); the header line only tells the renderer so.
    const { notation, body: answer } = splitAnswerNotation(trimmed);
    if (notation === "chemistry") return answer;
    return mode === "speech" ? speakMath(answer) : copyMath(answer);
  }
  if (isMathFenceLang(lang)) {
    return mode === "speech" ? speakMath(trimmed) : copyMath(trimmed);
  }
  if (lang.startsWith("callout-")) return convertProse(trimmed, mode);
  return trimmed;
}

function convertMarkdown(markdown: string, mode: "copy" | "speech"): string {
  const walked = mapFenceRegions(
    markdown,
    (prose) => convertProse(prose, mode),
    (lang, body) => convertFence(lang, body, mode),
  );
  return walked.replace(/\n{3,}/g, "\n\n").trim();
}

/** One fenced block as whole-message Copy writes it. */
export function fenceToCopyText(lang: string, body: string): string {
  return convertFence(lang, body, "copy");
}

/** Whole-message Copy: keep code and identifiers; flatten `$...$` math to readable text. */
export function markdownToCopyText(markdown: string): string {
  return convertMarkdown(markdown, "copy");
}

/** Read-aloud: speak prose and results; label visuals; skip control JSON. */
export function markdownToSpeechText(markdown: string): string {
  return convertMarkdown(markdown, "speech");
}

/** A command with its braced arguments, one level of nesting deep (`\frac{\sqrt{3}}{2}`). */
const TEX_RUN = /\\[A-Za-z]+(?:\s*\{(?:[^{}]|\{[^{}]*\})*\})*/g;

function withTexRuns(text: string, render: (latex: string) => string): string {
  return text.replace(TEX_RUN, (run) => render(run)).replace(/[ \t]+/g, " ").trim();
}

/** A sentence that carries bare TeX ("cosine \frac{\sqrt{3}}{2}"), as words to read aloud. */
export function spokenText(text: string): string {
  return withTexRuns(text, speakMath);
}
