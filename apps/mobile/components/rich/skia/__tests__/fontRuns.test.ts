/**
 * Canvas labels across fonts: SpaceMono has no Greek, so "τ = 15 N·m" lost
 * its τ until a label could fall back to the math faces.
 */
import type { SkFont } from "@shopify/react-native-skia";

import { fontRuns, measureRuns, needsFallback } from "@/components/rich/skia/fontRuns";

/** A stand-in font: draws `chars`, each `advance` wide; glyph 0 is "missing". */
function fakeFont(chars: string, advance: number): SkFont {
  const font = {
    getGlyphIDs: (text: string) =>
      Array.from(text).map((char) => (chars.includes(char) ? char.codePointAt(0)! : 0)),
    getGlyphWidths: (ids: number[]) => ids.map(() => advance),
    measureText: (text: string) => ({ x: 0, y: 0, width: Array.from(text).length * advance, height: 11 }),
  };
  return font as unknown as SkFont;
}

const mono = fakeFont("= 15N·mFabc", 6);
const greek = fakeFont("τθλΩ", 5);

describe("fontRuns", () => {
  it("sets a character the first font lacks in the next one that has it", () => {
    const runs = fontRuns("τ = 15 N·m", [mono, greek]);
    expect(runs.map((run) => [run.text, run.font === greek, run.dx])).toEqual([
      ["τ", true, 0],
      [" = 15 N·m", false, 5],
    ]);
  });

  it("keeps a label the first font can draw as one run, measured as before", () => {
    expect(needsFallback("F = 15 N", [mono, greek])).toBe(false);
    expect(fontRuns("F = 15 N", [mono, greek])).toHaveLength(1);
    expect(measureRuns("F = 15 N", [mono, greek])).toBe(48);
  });

  it("measures a mixed label run by run", () => {
    expect(needsFallback("Ω", [mono, greek])).toBe(true);
    expect(measureRuns("R = 4 Ω", [mono, greek])).toBe(6 * 6 + 5);
  });

  it("leaves a character no font has in the first font", () => {
    const runs = fontRuns("a☃b", [mono, greek]);
    expect(runs).toHaveLength(1);
    expect(runs[0].font).toBe(mono);
  });
});
