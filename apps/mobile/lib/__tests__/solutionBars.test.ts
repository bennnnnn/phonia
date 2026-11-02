import {
  displayMathToInline,
  rewriteSolutionSeparatorBars,
} from "@/lib/math/solutionBars";

describe("rewriteSolutionSeparatorBars", () => {
  it("turns a bar between two x= clauses into or", () => {
    expect(rewriteSolutionSeparatorBars(String.raw`x = \frac{1}{2} | x = 3`)).toContain(
      "\\text{ or }",
    );
    expect(rewriteSolutionSeparatorBars(String.raw`x = \frac{1}{2} | x = 3`)).not.toMatch(
      /\|/,
    );
  });

  it("turns \\mid between two assignments into or", () => {
    const out = rewriteSolutionSeparatorBars(String.raw`x=\frac{1}{2} \mid x=3`);
    expect(out).toContain("\\text{ or }");
    expect(out).not.toContain("\\mid");
  });

  it("leaves absolute value bars alone", () => {
    expect(rewriteSolutionSeparatorBars("|x-2| = 5")).toBe("|x-2| = 5");
    expect(rewriteSolutionSeparatorBars(String.raw`\left|x\right| = 5`)).toBe(
      String.raw`\left|x\right| = 5`,
    );
  });

  it("leaves such-that \\mid without equals on both sides", () => {
    expect(rewriteSolutionSeparatorBars(String.raw`\{x \mid x > 0\}`)).toBe(
      String.raw`\{x \mid x > 0\}`,
    );
  });
});

describe("displayMathToInline", () => {
  it("turns \\[...\\] display math into inline $...$", () => {
    expect(displayMathToInline(String.raw`\[ 2x^2-7x+3=0 \]`)).toBe("$2x^2-7x+3=0$");
  });

  it("keeps labels around several display blocks", () => {
    const out = displayMathToInline("Factor it:\n\\[ 2x-1=0 \\]\nor\n\\[ x-3=0 \\]");
    expect(out).toContain("$2x-1=0$");
    expect(out).toContain("$x-3=0$");
    expect(out).not.toContain("\\[");
  });

  it("keeps punctuation attached to a grouped slash fraction", () => {
    expect(displayMathToInline("Simplify (x^2-4)/(x^2-x-2). State restrictions.")).toBe(
      "Simplify $\\frac{x^2-4}{x^2-x-2}.$ State restrictions.",
    );
  });
});
