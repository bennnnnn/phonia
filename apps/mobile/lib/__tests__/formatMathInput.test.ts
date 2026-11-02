import {
  formatAssistantMathExpr,
  formatMathExpr,
} from "@/lib/math/formatInput";

describe("formatMathExpr", () => {
  describe("power", () => {
    it("converts a bare variable+digit to an exponent", () => {
      expect(formatMathExpr("x2+2=6")).toBe("x^2 + 2 = 6");
    });
    it("leaves an explicit caret exponent as-is", () => {
      expect(formatMathExpr("x^2 = 4")).toBe("x^2 = 4");
    });
    it("does not turn a command tail into a false exponent", () => {
      // \pm2 must stay \pm2, not \pm^2 (regression guard from applyImplicitPowerNotation).
      expect(formatMathExpr("x = \\pm2")).toBe("x = \\pm2");
    });
    it("can be disabled", () => {
      expect(formatMathExpr("x2=4", { power: false })).toBe("x2 = 4");
    });
  });

  describe("spacing", () => {
    it("spaces a bare equals", () => {
      expect(formatMathExpr("x=3")).toBe("x = 3");
    });
    it("spaces binary + and -", () => {
      expect(formatMathExpr("2x+3=7")).toBe("2x + 3 = 7");
      expect(formatMathExpr("a-b")).toBe("a - b");
    });
    it("leaves a unary minus unspaced", () => {
      expect(formatMathExpr("x=-3")).toBe("x = -3");
      expect(formatMathExpr("-x+2")).toBe("-x + 2");
    });
    it("does not space inside ^{...} exponents", () => {
      expect(formatMathExpr("x^{n+1}=2")).toBe("x^{n+1} = 2");
    });
    it("does not space inside _{...} subscripts", () => {
      expect(formatMathExpr("a_{ij}=0")).toBe("a_{ij} = 0");
    });
    it("does not break a LaTeX command name", () => {
      expect(formatMathExpr("\\sqrt{4}=2")).toBe("\\sqrt{4} = 2");
    });
    it("can be disabled", () => {
      expect(formatMathExpr("x=3", { spacing: false })).toBe("x=3");
    });
  });

  describe("relations", () => {
    it("converts >=, <=, !=", () => {
      expect(formatMathExpr("x>=3")).toBe("x \\geq 3");
      expect(formatMathExpr("x<=2")).toBe("x \\leq 2");
      expect(formatMathExpr("x!=0")).toBe("x \\neq 0");
    });
    it("does not leave a bare = from >=", () => {
      expect(formatMathExpr("x>=3")).not.toContain("=");
      expect(formatMathExpr("x>=3")).not.toContain(">= ");
    });
    it("can be disabled", () => {
      // Relations off → `>=` is not converted to \geq. Spacing still applies to
      // the standalone `=`, so `>=` splits into `>` + ` = ` → "x> = 3"
      // (ugly but accurate; relations are ON by default, so this only
      // happens when a caller explicitly opts out).
      expect(formatMathExpr("x>=3", { relations: false })).toBe("x> = 3");
      expect(formatMathExpr("x>=3", { relations: false })).not.toContain("\\geq");
    });
  });

  describe("pm", () => {
    it("converts +- to \\pm", () => {
      expect(formatMathExpr("x = +-3")).toBe("x = \\pm 3");
    });
    it("does not treat plus then unary minus as \\pm", () => {
      expect(formatMathExpr("x + -5")).toBe("x + -5");
      expect(formatMathExpr("\\frac{1}{4}x + -5")).toBe("\\frac{1}{4}x + -5");
    });
    it("can be disabled", () => {
      // pm off → `+-` stays as `+-` (both unary after `=`), no \pm.
      const out = formatMathExpr("x = +-3", { pm: false });
      expect(out).toBe("x = +-3");
      expect(out).not.toContain("\\pm");
    });
  });

  describe("combined / real input", () => {
    it("formats a full unspaced equation", () => {
      expect(formatMathExpr("x2+2=6")).toBe("x^2 + 2 = 6");
    });
    it("formats a quadratic with a minus", () => {
      expect(formatMathExpr("x2-5x+6=0")).toBe("x^2 - 5x + 6 = 0");
    });
    it("preserves an already-spaced equation", () => {
      expect(formatMathExpr("x^2 + 2 = 6")).toBe("x^2 + 2 = 6");
    });
    it("handles a fraction and sqrt without corrupting them", () => {
      expect(formatMathExpr("\\frac{1}{2}=0.5")).toBe("\\frac{1}{2} = 0.5");
    });
    it("keeps 9\\sqrt{9} as 9 times square root, not a 9th root", () => {
      expect(formatMathExpr("9\\sqrt{9}")).toBe("9 \\times \\sqrt{9}");
    });
    it("does not insert times between \\pm and a square root", () => {
      expect(formatMathExpr("x = \\pm\\sqrt{4}")).toBe("x = \\pm\\sqrt{4}");
    });
    it("leaves an nth-root \\sqrt[n]{x} unchanged", () => {
      expect(formatMathExpr("\\sqrt[9]{9}")).toBe("\\sqrt[9]{9}");
    });
    it("returns empty for empty input", () => {
      expect(formatMathExpr("")).toBe("");
    });
  });

  describe("times", () => {
    it("converts binary * to \\times", () => {
      expect(formatMathExpr("2*x=6")).toBe("2 \\times x = 6");
    });
  });

  describe("slashFrac", () => {
    it("converts a simple a/b to \\frac", () => {
      expect(formatMathExpr("1/2")).toBe("\\frac{1}{2}");
      expect(formatMathExpr("a/b=1")).toBe("\\frac{a}{b} = 1");
    });
    it("does not turn SI unit slashes into fractions", () => {
      expect(formatMathExpr("1.2 m/s^2")).toBe("1.2 m/s^2");
      expect(formatMathExpr("1.2 m/s^2")).not.toContain("\\frac");
      expect(formatMathExpr("80 km/h")).toBe("80 km/h");
    });
  });
});

describe("formatAssistantMathExpr", () => {
  it("converts a simple a/b to \\frac like the composer", () => {
    expect(formatAssistantMathExpr("18/6")).toBe("\\frac{18}{6}");
    expect(formatAssistantMathExpr("4/6 = 2/3")).toBe("\\frac{4}{6} = \\frac{2}{3}");
  });

  it("converts a parenthesized numerator/denominator the composer's slashToFrac skips", () => {
    expect(formatAssistantMathExpr("(11 + 7)/6")).toBe("\\frac{11 + 7}{6}");
    expect(formatAssistantMathExpr("(11 - 7)/6")).toBe("\\frac{11 - 7}{6}");
  });

  it("converts Unicode radicals to \\sqrt{}", () => {
    expect(formatAssistantMathExpr("√(49)")).toBe("\\sqrt{49}");
    expect(formatAssistantMathExpr("√49")).toBe("\\sqrt{49}");
  });

  it("does not apply composer-only x2 -> x^2 OCR to model text", () => {
    expect(formatAssistantMathExpr("x2 = 4")).toBe("x2 = 4");
  });

  it("fixes the reported quadratic-formula step end-to-end", () => {
    const input = "x = ( -(-11) ± √(49) ) / (2(3)) = (11 ± 7) / 6";
    const out = formatAssistantMathExpr(input);
    expect(out).toBe("x = \\frac{-(-11) \\pm \\sqrt{49}}{2(3)} = \\frac{11 \\pm 7}{6}");
  });

  it("fixes both split-root step lines from the same screenshot", () => {
    expect(formatAssistantMathExpr("x = (11 + 7)/6 = 18/6 = 3")).toBe(
      "x = \\frac{11 + 7}{6} = \\frac{18}{6} = 3",
    );
    expect(formatAssistantMathExpr("x = (11 - 7)/6 = 4/6 = 2/3")).toBe(
      "x = \\frac{11 - 7}{6} = \\frac{4}{6} = \\frac{2}{3}",
    );
  });

  it("does not touch SI unit slashes", () => {
    expect(formatAssistantMathExpr("1.2 m/s^2")).not.toContain("\\frac");
  });

  it("leaves already-correct LaTeX alone (idempotent)", () => {
    expect(formatAssistantMathExpr("x = \\frac{2}{3}")).toBe("x = \\frac{2}{3}");
    expect(formatAssistantMathExpr("\\sqrt{49}")).toBe("\\sqrt{49}");
  });
});
