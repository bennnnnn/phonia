/**
 * Canvas text across more than one font.
 *
 * A Skia font draws nothing for a character it has no glyph for, and the
 * figures' label face (SpaceMono) has no Greek: "τ = 15 N·m" came out as
 * "= 15 N·m", and an ohm sign would vanish the same way. A label is split
 * into runs, each in the first font that can draw it, and the runs are set
 * side by side.
 */
import type { SkFont } from "@shopify/react-native-skia";

type FontRun = { text: string; font: SkFont; dx: number };

function hasGlyph(font: SkFont, char: string): boolean {
  const ids = font.getGlyphIDs(char);
  return ids.length > 0 && ids[0] !== 0;
}

/** Advance width of `text` in one font. */
function advanceWidth(font: SkFont, text: string): number {
  if (!text) return 0;
  return font.getGlyphWidths(font.getGlyphIDs(text)).reduce((sum, width) => sum + width, 0);
}

/**
 * `text` as runs, each in the first of `fonts` that has every glyph in it
 * (the first font when none does), with each run's offset from the start.
 */
export function fontRuns(text: string, fonts: readonly SkFont[]): FontRun[] {
  const runs: FontRun[] = [];
  if (fonts.length === 0) return runs;
  for (const char of Array.from(text)) {
    const font = fonts.find((candidate) => hasGlyph(candidate, char)) ?? fonts[0];
    const last = runs[runs.length - 1];
    if (last && last.font === font) last.text += char;
    else runs.push({ text: char, font, dx: 0 });
  }
  let dx = 0;
  for (const run of runs) {
    run.dx = dx;
    dx += advanceWidth(run.font, run.text);
  }
  return runs;
}

/** Whether `text` needs more than its first font. */
export function needsFallback(text: string, fonts: readonly SkFont[]): boolean {
  const runs = fontRuns(text, fonts);
  return runs.length > 1 || (runs.length === 1 && runs[0].font !== fonts[0]);
}

/**
 * The width a label takes. A single-font label keeps the font's own measure,
 * so a figure whose labels never leave it lays out exactly as before.
 */
export function measureRuns(text: string, fonts: readonly SkFont[]): number {
  if (fonts.length === 0) return 0;
  if (!needsFallback(text, fonts)) return fonts[0].measureText(text).width;
  const runs = fontRuns(text, fonts);
  const last = runs[runs.length - 1];
  return last.dx + advanceWidth(last.font, last.text);
}
