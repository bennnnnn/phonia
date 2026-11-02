/**
 * Unicode superscript / subscript characters for the Expo-Go math fallback.
 *
 * `MathText` renders math as native Text when no inline-HTML WebView is
 * available (neither RNC nor `@expo/dom-webview`). Its
 * `sup`/`sub` styles are just smaller text at the baseline — they don't raise
 * the exponent, so `2^x` reads as `2_x` (subscript) instead of `2ˣ`. Mapping
 * exponents to real Unicode superscripts makes them render raised in plain
 * text with no WebView. When a character has no Unicode super/subscript (e.g.
 * a parenthesis or an unusual letter), the caller falls back to the styled
 * smaller-Text rendering.
 */

const SUPERSCRIPT: Record<string, string> = {
  "0": "⁰",
  "1": "¹",
  "2": "²",
  "3": "³",
  "4": "⁴",
  "5": "⁵",
  "6": "⁶",
  "7": "⁷",
  "8": "⁸",
  "9": "⁹",
  "+": "⁺",
  "-": "⁻",
  "=": "⁼",
  "(": "⁽",
  ")": "⁾",
  a: "ᵃ",
  b: "ᵇ",
  c: "ᶜ",
  d: "ᵈ",
  e: "ᵉ",
  f: "ᶠ",
  g: "ᵍ",
  h: "ʰ",
  i: "ⁱ",
  j: "ʲ",
  k: "ᵏ",
  l: "ˡ",
  m: "ᵐ",
  n: "ⁿ",
  o: "ᵒ",
  p: "ᵖ",
  r: "ʳ",
  s: "ˢ",
  t: "ᵗ",
  u: "ᵘ",
  v: "ᵛ",
  w: "ʷ",
  x: "ˣ",
  y: "ʸ",
  z: "ᶻ",
  A: "ᴬ",
  B: "ᴮ",
  D: "ᴰ",
  E: "ᴱ",
  G: "ᴳ",
  H: "ᴴ",
  I: "ᴵ",
  J: "ᴶ",
  K: "ᴷ",
  L: "ᴸ",
  M: "ᴹ",
  N: "ᴺ",
  O: "ᴼ",
  P: "ᴾ",
  R: "ᴿ",
  T: "ᵀ",
  U: "ᵁ",
  V: "ⱽ",
  W: "ᵂ",
};

const SUBSCRIPT: Record<string, string> = {
  "0": "₀",
  "1": "₁",
  "2": "₂",
  "3": "₃",
  "4": "₄",
  "5": "₅",
  "6": "₆",
  "7": "₇",
  "8": "₈",
  "9": "₉",
  "+": "₊",
  "-": "₋",
  "=": "₌",
  "(": "₍",
  ")": "₎",
  a: "ₐ",
  e: "ₑ",
  h: "ₕ",
  i: "ᵢ",
  j: "ⱼ",
  k: "ₖ",
  l: "ₗ",
  m: "ₘ",
  n: "ₙ",
  o: "ₒ",
  p: "ₚ",
  r: "ᵣ",
  s: "ₛ",
  t: "ₜ",
  u: "ᵤ",
  v: "ᵥ",
  x: "ₓ",
};

function toVerticalForm(value: string, map: Record<string, string>): string | null {
  if (!value) return null;
  let out = "";
  for (const ch of value) {
    const mapped = map[ch];
    if (!mapped) return null; // any unmapped char → caller falls back to styled Text
    out += mapped;
  }
  return out;
}

/** Return the Unicode superscript for `value` (e.g. "x" → "ˣ", "2" → "²"),
 * or null if any character lacks a Unicode superscript.
 * `2/3` → `²⁄³` (fraction slash) so `3^{2/3}` does not paint as baseline "32/3". */
export function toSuperscript(value: string): string | null {
  if (value.includes("/")) {
    const parts = value.split("/");
    if (parts.length !== 2 || !parts[0] || !parts[1]) return null;
    const num = toVerticalForm(parts[0], SUPERSCRIPT);
    const den = toVerticalForm(parts[1], SUPERSCRIPT);
    if (!num || !den) return null;
    return `${num}\u2044${den}`;
  }
  return toVerticalForm(value, SUPERSCRIPT);
}

/** Reverse maps: Unicode super/subscript glyph → ASCII base char. */
const FROM_SUPERSCRIPT: Record<string, string> = Object.fromEntries(
  Object.entries(SUPERSCRIPT).map(([ascii, uni]) => [uni, ascii]),
);
const FROM_SUBSCRIPT: Record<string, string> = Object.fromEntries(
  Object.entries(SUBSCRIPT).map(([ascii, uni]) => [uni, ascii]),
);

function isSuperscriptChar(ch: string): boolean {
  return ch in FROM_SUPERSCRIPT;
}

function isSubscriptChar(ch: string): boolean {
  return ch in FROM_SUBSCRIPT;
}

function scriptRunToCaret(run: string, kind: "sup" | "sub"): string {
  const map = kind === "sup" ? FROM_SUPERSCRIPT : FROM_SUBSCRIPT;
  const ascii = [...run].map((ch) => map[ch] ?? "").join("");
  if (!ascii) return run;
  const marker = kind === "sup" ? "^" : "_";
  // Single char → ^2 / _n; multi-char → ^{10} / _{ij} so parseSimpleLatex
  // groups the whole exponent the same way as typed LaTeX.
  return ascii.length === 1 ? `${marker}${ascii}` : `${marker}{${ascii}}`;
}

/**
 * Rewrite Unicode superscript/subscript runs into caret/underscore LaTeX
 * (`x²` → `x^2`, `a₁₀` → `a_{10}`) so `parseSimpleLatex` can build real
 * sup/sub segments. OCR and models often emit these glyphs instead of `^`.
 */
export function normalizeUnicodeScripts(input: string): string {
  if (!input) return input;
  let out = "";
  let i = 0;
  while (i < input.length) {
    const ch = input[i]!;
    if (isSuperscriptChar(ch) || isSubscriptChar(ch)) {
      const kind: "sup" | "sub" = isSuperscriptChar(ch) ? "sup" : "sub";
      const isRun = kind === "sup" ? isSuperscriptChar : isSubscriptChar;
      let j = i + 1;
      while (j < input.length && isRun(input[j]!)) j += 1;
      out += scriptRunToCaret(input.slice(i, j), kind);
      i = j;
      continue;
    }
    out += ch;
    i += 1;
  }
  return out;
}
