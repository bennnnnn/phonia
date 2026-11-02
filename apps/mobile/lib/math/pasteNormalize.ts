/**
 * Best-effort Unicode math → LaTeX for composer pastes.
 * Glyph set is the client counterpart of `_UNICODE_OP_SUBS` in
 * `apps/api/app/modules/math/solve/unicode_normalize.py`.
 */

import { nativeEditRange } from "@/lib/math/composerChange";
import { formatMathExpr } from "@/lib/math/formatInput";
import { isMathLike } from "@/lib/math/normalizeImplicit";
import { normalizeUnicodeScripts } from "@/lib/unicodeSupSub";

export const PASTE_GROWTH_MIN = 6;
/** Ordinary typing / autocorrect stays under this; a real paste is larger. */
const PASTE_CLIPBOARD_PROBE_MIN = 40;

const VULGAR_FRACTIONS: Record<string, string> = {
  "½": "\\frac{1}{2}",
  "⅓": "\\frac{1}{3}",
  "⅔": "\\frac{2}{3}",
  "¼": "\\frac{1}{4}",
  "¾": "\\frac{3}{4}",
  "⅕": "\\frac{1}{5}",
  "⅖": "\\frac{2}{5}",
  "⅗": "\\frac{3}{5}",
  "⅘": "\\frac{4}{5}",
  "⅙": "\\frac{1}{6}",
  "⅚": "\\frac{5}{6}",
  "⅛": "\\frac{1}{8}",
  "⅜": "\\frac{3}{8}",
  "⅝": "\\frac{5}{8}",
  "⅞": "\\frac{7}{8}",
};

const OP_GLYPHS: [string, string][] = [
  ["×", "\\times "],
  ["÷", "\\div "],
  ["±", "\\pm "],
  ["∓", "\\mp "],
  ["≤", "\\leq "],
  ["≥", "\\geq "],
  ["≠", "\\neq "],
  ["≈", "\\approx "],
  ["∞", "\\infty "],
  ["π", "\\pi "],
  ["·", "\\cdot "],
  ["⋅", "\\cdot "],
  ["∗", "\\times "],
  ["∕", "\\div "],
  ["⁄", "/"],
  ["−", "-"],
  ["–", "-"],
  ["—", "-"],
];

export const MATH_GLYPH_RE =
  /[½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞√∛∜×÷±∓≤≥≠≈∞π·⋅∗∕⁄−²³¹⁰⁴⁵⁶⁷⁸⁹⁺⁻₀-₉]/;

const RADICAL_PREFIX: Record<string, string> = {
  "√": "\\sqrt",
  "∛": "\\sqrt[3]",
  "∜": "\\sqrt[4]",
};

/** Enough English words that a paste is a word problem, not a formula. */
const PROSE_WORD_MIN = 8;

/**
 * True for homework / chat prose that happens to contain a unit or ².
 * Keep this off the math-wrap / math-preview path.
 */
export function isMostlyProsePaste(text: string): boolean {
  const words = text.match(/[A-Za-z]{3,}/g);
  return (words?.length ?? 0) >= PROSE_WORD_MIN;
}

export function shouldProbeClipboardForImagePaste(delta: string): boolean {
  if (delta.length >= PASTE_CLIPBOARD_PROBE_MIN) return true;
  return MATH_GLYPH_RE.test(delta) && delta.length >= PASTE_GROWTH_MIN;
}

export function pastedDeltaLooksLikeMath(delta: string): boolean {
  const s = delta.trim();
  if (s.length < 1) return false;
  if (/\*\*|__/.test(s)) return false;
  if (/\$[^$\n]+\$/.test(s) || /```math\b/i.test(s)) return true;
  if (MATH_GLYPH_RE.test(s)) return true;
  if (isMathLike(s) && /[=+\-^√\\]/.test(s)) return true;
  return false;
}

/**
 * Sites like MathPapa copy stacked fractions as HTML. iOS TextInput only
 * gets the accessibility dump: numerator and denominator as separate
 * tokens (`1\\n3 x` or `1 3 x`), so `1/3 x` never reaches slash-to-frac.
 */
export function restoreCopiedFractions(raw: string): string {
  let s = raw.replace(/\u00a0/g, " ");
  s = s.replace(
    /(\d+(?:\.\d+)?)\s*[\n\r]+\s*(\d+(?:\.\d+)?)(?=\s*[a-zA-Z=])/g,
    "\\frac{$1}{$2}",
  );
  if (!/\\frac/.test(s) && !/\d+\s*\/\s*\d/.test(s)) {
    s = s.replace(
      /(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s*([a-zA-Z])/g,
      "\\frac{$1}{$2} $3",
    );
  }
  return s;
}

function rewriteUnicodeSqrts(s: string, nesting = 0): string {
  if (nesting >= 12) return s;
  // Convert √9 / ∛8 / √{9} / √(x) before leftover √ becomes \sqrt{}.
  let out = "";
  let i = 0;
  const n = s.length;
  while (i < n) {
    let cmd = RADICAL_PREFIX[s[i] ?? ""];
    if (!cmd) {
      out += s[i];
      i += 1;
      continue;
    }
    i += 1;
    while (i < n && (s[i] === " " || s[i] === "\t")) i += 1;
    if (cmd === "\\sqrt" && s[i] === "[") {
      const end = s.indexOf("]", i + 1);
      if (end >= 0) {
        cmd += s.slice(i, end + 1);
        i = end + 1;
        while (i < n && /\s/.test(s[i]!)) i += 1;
      }
    }
    if (i >= n) {
      out += `${cmd}{}`;
      break;
    }
    if (s[i] === "(" || s[i] === "{") {
      const closer = s[i] === "(" ? ")" : "}";
      const start = i + 1;
      let close = start;
      let depth = 1;
      while (close < n && depth > 0) {
        if (s[close] === s[i]) depth += 1;
        else if (s[close] === closer) depth -= 1;
        if (depth > 0) close += 1;
      }
      if (depth !== 0) {
        out += `${cmd}{}`;
        continue;
      }
      out += `${cmd}{${rewriteUnicodeSqrts(s.slice(start, close), nesting + 1)}}`;
      i = close + 1;
      continue;
    }
    if (s[i] >= "0" && s[i] <= "9") {
      let j = i + 1;
      while (j < n && s[j] >= "0" && s[j] <= "9") j += 1;
      if (j < n && s[j] === ".") {
        let k = j + 1;
        if (k < n && s[k] >= "0" && s[k] <= "9") {
          while (k < n && s[k] >= "0" && s[k] <= "9") k += 1;
          j = k;
        }
      }
      out += `${cmd}{${s.slice(i, j)}}`;
      i = j;
      continue;
    }
    const ch = s[i];
    if ((ch >= "a" && ch <= "z") || (ch >= "A" && ch <= "Z")) {
      out += `${cmd}{${ch}}`;
      i += 1;
      continue;
    }
    out += `${cmd}{}`;
  }
  return out;
}

function formatPastedExpr(expr: string): string {
  return formatMathExpr(restoreCopiedFractions(expr));
}

function looksLikeEquationSystem(text: string): boolean {
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
  if (lines.length < 2) return false;
  return lines.filter((line) => line.includes("=")).length >= 2;
}

export function normalizePastedMath(delta: string): string {
  if (isMostlyProsePaste(delta)) return delta;
  if (!pastedDeltaLooksLikeMath(delta)) return delta;
  let s = delta;
  for (const [glyph, latex] of Object.entries(VULGAR_FRACTIONS)) {
    s = s.split(glyph).join(latex);
  }
  s = rewriteUnicodeSqrts(s);
  for (const [glyph, latex] of OP_GLYPHS) {
    s = s.split(glyph).join(latex);
  }
  s = normalizeUnicodeScripts(s);
  const trimmed = s.trim();
  if (!trimmed) return delta;
  if (/```math\b/i.test(trimmed)) {
    return trimmed.replace(/```math\n([\s\S]*?)```/gi, (_m, body: string) => {
      return "```math\n" + formatPastedExpr(String(body).trim()) + "\n```";
    });
  }
  // Already display math — wrapping the whole homework write-up in one `$`
  // made the sent bubble a composer MathDraftPreview (empty slots, huge).
  if (trimmed.includes("\\[") || trimmed.includes("\\]") || trimmed.includes("$$")) {
    return s;
  }
  if (trimmed.includes("$")) {
    return s.replace(/\$([^$\n]+)\$/g, (_m, inner: string) => `$${formatPastedExpr(inner)}$`);
  }
  if (looksLikeEquationSystem(trimmed)) {
    return trimmed
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line.length > 0)
      .map((line) => `$${formatMathExpr(line)}$`)
      .join("\n");
  }
  return `$${formatPastedExpr(trimmed)}$`;
}

/** Longest common prefix/suffix → inserted middle. Null if not a paste-sized insert. */
export function extractInsertedDelta(prev: string, next: string): string | null {
  if (next.length <= prev.length) return null;
  const inserted = nativeEditRange(prev, next)?.added ?? "";
  if (inserted.length < 1) return null;
  if (inserted.length < PASTE_GROWTH_MIN && !pastedDeltaLooksLikeMath(inserted)) {
    return null;
  }
  return inserted;
}
