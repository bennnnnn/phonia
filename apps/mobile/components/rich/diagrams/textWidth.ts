/**
 * Label widths for the physics diagrams, without loading a font.
 *
 * The diagrams draw their labels in Source Sans 3 Regular (the app's UI face,
 * which unlike SpaceMono carries Ω, λ and θ). Skia measures and draws text as
 * the plain sum of glyph advances, with no kerning, so a table of advances
 * gives the width Skia will draw. The layout and the list placeholder both
 * read it, which is what lets the placeholder reserve the diagram's real
 * height before the renderer's chunk, or the font, has loaded.
 */

/** The size every diagram label is drawn at. */
export const DIAGRAM_FONT_SIZE = 12;

/** Advance widths in thousandths of an em for U+0020 to U+007E, in order. */
// prettier-ignore
const ASCII_ADVANCES = [
  200, 289, 426, 497, 497, 824, 609, 249, 303, 303, 418, 497, 249, 311, 249, 350,
  497, 497, 497, 497, 497, 497, 497, 497, 497, 497, 249, 249, 497, 497, 497, 425,
  847, 543, 588, 571, 615, 527, 494, 617, 652, 263, 479, 579, 486, 727, 647, 664,
  566, 664, 569, 534, 536, 645, 515, 786, 513, 476, 539, 303, 350, 303, 497, 500,
  542, 504, 553, 456, 555, 496, 292, 504, 544, 246, 247, 495, 255, 829, 547, 542,
  555, 555, 347, 419, 338, 544, 467, 719, 446, 467, 425, 303, 241, 303, 497,
];

/** Physics notation beyond ASCII: Greek letters, sub- and superscripts, signs. */
const OTHER_ADVANCES: Record<string, number> = {
  "Ω": 678, "λ": 494, "θ": 522, "μ": 562, "Δ": 588, "α": 560, "β": 565, "γ": 484,
  "ω": 701, "π": 586, "ρ": 549, "σ": 546, "φ": 680, "ε": 448, "η": 541, "τ": 458,
  "ν": 474, "Σ": 538, "Φ": 719, "Ψ": 699, "°": 331, "−": 497, "±": 497, "·": 249,
  "→": 619, "←": 619, "×": 497, "√": 557, "∞": 782, "≈": 497, "≤": 497, "≥": 497,
  "′": 249, "″": 426, "…": 948, "–": 480, "—": 800,
};
/** Every sub- and superscript digit has the same advance. */
const SCRIPT_DIGIT = 367;
const SCRIPT_DIGITS = "₀₁₂₃₄₅₆₇₈₉⁰¹²³⁴⁵⁶⁷⁸⁹";
/** Anything else: a little wider than the average letter, so the guess errs roomy. */
const UNKNOWN_ADVANCE = 560;

function advance(char: string): number {
  const code = char.codePointAt(0) ?? 0;
  if (code >= 0x20 && code <= 0x7e) return ASCII_ADVANCES[code - 0x20];
  if (SCRIPT_DIGITS.includes(char)) return SCRIPT_DIGIT;
  return OTHER_ADVANCES[char] ?? UNKNOWN_ADVANCE;
}

export function diagramTextWidth(text: string, fontSize = DIAGRAM_FONT_SIZE): number {
  let total = 0;
  for (const char of text) total += advance(char);
  return (total * fontSize) / 1000;
}

/** The measure the layouts take: a label's width at `DIAGRAM_FONT_SIZE`. */
export function measureDiagramText(text: string): number {
  return diagramTextWidth(text, DIAGRAM_FONT_SIZE);
}
