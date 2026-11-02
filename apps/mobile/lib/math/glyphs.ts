/**
 * Which KaTeX face actually contains a glyph, and the em advance it draws at.
 *
 * Checked against katex/dist/fonts (Main, Math-Italic, AMS). Unicode
 * blackboard bold, U+2260 ≠, U+2209 ∉, and U+00B7 · are not in those files.
 * Painting them in a face that lacks the character makes React Native fall
 * back to the UI font. Callers paint a glyph the face does contain.
 */

/** KaTeX `\@not` in KaTeX_Main. Advance matches `=`; ink is the negating slash. */
export const MATH_NOT_GLYPH = "\uE020";
export const NOT_ADVANCE_EM = 0.778;

/** Relations KaTeX builds by overlaying MATH_NOT_GLYPH, plus the base advance. */
export const NEGATED_RELATION: Record<string, { base: string; widthEm: number }> = {
  "≠": { base: "=", widthEm: NOT_ADVANCE_EM },
  "∉": { base: "∈", widthEm: 0.667 },
};

/** In KaTeX_AMS and absent from KaTeX_Main. Everything else in Main stays there. */
export const AMS_ONLY_CHARS = new Set(["∴", "∵"]);

/**
 * Unicode double-struck letters are not in the KaTeX fonts. AMS-Regular draws
 * them at the Latin capitals, which is how KaTeX sets `\mathbb`.
 */
export const BLACKBOARD_LATIN: Record<string, string> = {
  "ℝ": "R",
  "ℤ": "Z",
  "ℕ": "N",
  "ℚ": "Q",
  "ℂ": "C",
  "ℙ": "P",
  "ℍ": "H",
  "𝔽": "F",
  "𝕂": "K",
};

const BLACKBOARD_ADVANCE_EM = 0.72;
const CDOT_ADVANCE_EM = 0.28;
const PRIME_ADVANCE_EM = 0.275;
/** Two Main `|` bars pulled together. U+2016 lives only in the Size1 face. */
export const NORM_ADVANCE_EM = 0.64;

export function primeRun(ch: string): string | null {
  if (ch === "″") return "′′";
  if (ch === "‴") return "′′′";
  return null;
}

/**
 * Arrow advances in KaTeX_Main (katex fontMetricsData). A sideways arrow is a
 * full em and a long one over 1.6; measured as an unknown glyph (0.7 em), a
 * formula with `\rightarrow` came out narrower than its ink.
 */
const ARROW_ADVANCE_EM: Record<string, number> = {
  "↑": 0.5, "↓": 0.5, "↕": 0.5, "⇑": 0.611, "⇓": 0.611, "⇕": 0.611,
  "↩": 1.126, "↪": 1.126,
  "⟵": 1.609, "⟸": 1.609, "⟶": 1.638, "⟹": 1.638, "⟼": 1.638, "⟷": 1.859, "⟺": 1.858,
};

/** The em advance of an arrow glyph, or null when `ch` is not an arrow. */
function arrowAdvanceEm(ch: string): number | null {
  const listed = ARROW_ADVANCE_EM[ch];
  if (listed != null) return listed;
  const code = ch.codePointAt(0) ?? 0;
  return code >= 0x2190 && code <= 0x21ff ? 1 : null;
}

const WIDE = new Set(["m", "w", "M", "W"]);
const NARROW = new Set(["i", "l", "I", "j", "f", "t", "r"]);

function isCombiningMark(ch: string): boolean {
  const c = ch.charCodeAt(0);
  return c >= 0x0300 && c <= 0x036f;
}

/** Em advance for one glyph. Unknown characters still take positive space. */
export function glyphAdvanceEm(ch: string): number {
  if (isCombiningMark(ch)) return 0;
  if (ch === " " || ch === "\u00a0" || ch === "\u2009") return 0.33;
  if (ch >= "0" && ch <= "9") return 0.5;
  if (ch === "m" || ch === "M") return 0.9;
  if (ch === "w" || ch === "W") return 0.85;
  if (WIDE.has(ch)) return 0.8;
  if (NARROW.has(ch)) return 0.32;
  if (/[A-Za-z]/.test(ch)) {
    return ch.toLowerCase() !== ch ? 0.72 : 0.52;
  }
  if (ch === "·" || ch === "⋅") return CDOT_ADVANCE_EM;
  if (ch === "″") return PRIME_ADVANCE_EM * 2;
  if (ch === "‴") return PRIME_ADVANCE_EM * 3;
  if (ch === "‖") return NORM_ADVANCE_EM;
  if (NEGATED_RELATION[ch]) return NEGATED_RELATION[ch].widthEm;
  if (BLACKBOARD_LATIN[ch]) return BLACKBOARD_ADVANCE_EM;
  if (".,:;'`′″‴".includes(ch)) return 0.28;
  if ("()[]{}|/".includes(ch)) return 0.4;
  if ("+-−=<>±∓×÷".includes(ch)) return 0.78;
  const arrow = arrowAdvanceEm(ch);
  if (arrow != null) return arrow;
  const code = ch.codePointAt(0) ?? 0;
  if (code >= 0x370 && code <= 0x3ff) return 0.62;
  if (code > 0x7f) return 0.7;
  return 0.5;
}
