import { layoutMath, measureTextWidth } from "@/lib/math/layout";
import { fixImplicitExponents } from "@/lib/math/normalizeImplicit";
import { parseSimpleLatex } from "@/lib/math/text";

/**
 * Arrows measured as an unknown glyph (0.7 em) where KaTeX_Main draws a full
 * em, so "$2H_2 + O_2 \rightarrow 2H_2O$ shows" ran its ink into the space
 * before "shows". Advances are KaTeX's own (katex/src/fontMetricsData.js).
 */
const ARROWS: [string, string, number][] = [
  [String.raw`\rightarrow`, "→", 1],
  [String.raw`\to`, "→", 1],
  [String.raw`\leftarrow`, "←", 1],
  [String.raw`\leftrightarrow`, "↔", 1],
  [String.raw`\Rightarrow`, "⇒", 1],
  [String.raw`\implies`, "⇒", 1],
  [String.raw`\Leftarrow`, "⇐", 1],
  [String.raw`\Leftrightarrow`, "⇔", 1],
  [String.raw`\iff`, "⇔", 1],
  [String.raw`\rightleftharpoons`, "⇌", 1],
  [String.raw`\mapsto`, "↦", 1],
  [String.raw`\longrightarrow`, "⟶", 1.638],
  [String.raw`\Longrightarrow`, "⟹", 1.638],
  [String.raw`\longleftarrow`, "⟵", 1.609],
  [String.raw`\longleftrightarrow`, "⟷", 1.859],
  [String.raw`\uparrow`, "↑", 0.5],
  [String.raw`\Downarrow`, "⇓", 0.611],
];

function width(latex: string): number {
  return layoutMath(parseSimpleLatex(fixImplicitExponents(latex)), 16).width;
}

describe("arrow advances", () => {
  it.each(ARROWS)("%s draws %s at %s em", (latex, glyph, em) => {
    expect(parseSimpleLatex(latex)).toEqual([{ type: "text", value: glyph }]);
    expect(measureTextWidth(glyph, 16)).toBeCloseTo(em * 16, 5);
  });

  it("widens a reaction by the arrow's full em, not an unknown glyph's", () => {
    const arrow = width(String.raw`2H_2 + O_2 \rightarrow 2H_2O`);
    const equals = width(String.raw`2H_2 + O_2 = 2H_2O`);
    // "=" is 0.78 em in the same place, with the same spaces around it.
    expect(arrow - equals).toBeCloseTo((1 - 0.78) * 16, 5);
  });
});
