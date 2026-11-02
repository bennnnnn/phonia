import {
  extractInsertedDelta,
  MATH_GLYPH_RE,
  normalizePastedMath,
  PASTE_GROWTH_MIN,
  pastedDeltaLooksLikeMath,
  restoreCopiedFractions,
  shouldProbeClipboardForImagePaste,
} from "@/lib/math/pasteNormalize";

describe("normalizePastedMath", () => {
  it("maps Unicode math glyphs to LaTeX and wraps $...$", () => {
    expect(normalizePastedMath("x² + y² = 1")).toBe("$x^2 + y^2 = 1$");
    expect(normalizePastedMath("½")).toBe("$\\frac{1}{2}$");
    expect(normalizePastedMath("√(x)")).toBe("$\\sqrt{x}$");
    expect(normalizePastedMath("√9")).toBe("$\\sqrt{9}$");
    expect(normalizePastedMath("√x")).toBe("$\\sqrt{x}$");
    expect(normalizePastedMath("√{9}")).toBe("$\\sqrt{9}$");
    expect(normalizePastedMath("6√4")).toBe("$6 \\times \\sqrt{4}$");
    expect(normalizePastedMath("∛8")).toBe("$\\sqrt[3]{8}$");
    expect(normalizePastedMath("∜16")).toBe("$\\sqrt[4]{16}$");
    expect(normalizePastedMath("a ≤ b ≠ c")).toBe("$a \\leq b \\neq c$");
    expect(normalizePastedMath("2 × π")).toBe("$2 \\times \\pi$");
    expect(normalizePastedMath("2⋅x")).toBe("$2\\cdot x$");
  });

  it("leaves already-delimited math dollars in place", () => {
    expect(normalizePastedMath("$x^2$")).toBe("$x^2$");
  });

  it("rebuilds stacked fractions flattened by an HTML copy (MathPapa)", () => {
    // Live: copy 1/3 x = 1/4 x + -5 from a rendered page → composer got
    // "1 3 x = 1 4 x \\pm 5" (num/den split; + - smashed to \\pm).
    expect(normalizePastedMath("1 3 x = 1 4 x + -5")).toBe(
      "$\\frac{1}{3} x = \\frac{1}{4} x + -5$",
    );
    expect(
      normalizePastedMath("1\n3\nx = 1\n4\nx + -5"),
    ).toBe("$\\frac{1}{3} x = \\frac{1}{4} x + -5$");
    expect(normalizePastedMath("1/3 x = 1/4 x + -5")).toBe(
      "$\\frac{1}{3} x = \\frac{1}{4} x + -5$",
    );
  });

  it("does not rewrite non-math prose, bullets, or filenames", () => {
    expect(normalizePastedMath("* first\n* second")).toBe("* first\n* second");
    expect(normalizePastedMath("notes_draft.txt")).toBe("notes_draft.txt");
    expect(normalizePastedMath("**bold** text here")).toBe("**bold** text here");
    expect(normalizePastedMath("hello world")).toBe("hello world");
  });

  it("wraps each line of a pasted equation system instead of gluing them", () => {
    expect(normalizePastedMath("x + y = 3\n2x - y = 1")).toBe("$x + y = 3$\n$2x - y = 1$");
  });
});

describe("restoreCopiedFractions", () => {
  it("maps a flattened coefficient fraction to \\frac", () => {
    expect(restoreCopiedFractions("1 3 x")).toBe("\\frac{1}{3} x");
    expect(restoreCopiedFractions("1\n3 x")).toBe("\\frac{1}{3} x");
  });
  it("leaves slash fractions alone", () => {
    expect(restoreCopiedFractions("1/3 x")).toBe("1/3 x");
  });
});

describe("extractInsertedDelta", () => {
  it("ignores short typing bursts", () => {
    expect(extractInsertedDelta("ab", "abc")).toBeNull();
    expect("x".repeat(PASTE_GROWTH_MIN - 1).length).toBeLessThan(PASTE_GROWTH_MIN);
  });
});

describe("normalizePastedMath edge cases", () => {
  it("rewrites a short math paste, not only long ones", () => {
    expect(normalizePastedMath("½")).toBe("$\\frac{1}{2}$");
    expect(normalizePastedMath("x=4")).toBe("$x = 4$");
    expect(normalizePastedMath("x²")).toBe("$x^2$");
  });

  it("keeps existing $ delimiters and formats the inside", () => {
    expect(normalizePastedMath("$x=4$")).toBe("$x = 4$");
  });

  it("does not wrap a long prose paste", () => {
    const next = "please read notes_draft.txt later";
    expect(normalizePastedMath(next)).toBe(next);
  });

  it("leaves a pasted physics word problem verbatim, including m/s²", () => {
    const pasted =
      "A car starts from rest and accelerates at a constant rate of 1.2 m/s². How long does it take the car to travel a distance of 500 meters?";
    expect(normalizePastedMath(pasted)).toBe(pasted);
  });

  it("does not wrap a \\[...\\] homework paste in one $...$", () => {
    const pasted =
      "\\[ 2x^2-7x+3=0 \\]\nFactor it:\n\\[ 2x-1=0 \\]\nor\n\\[ x-3=0 \\]";
    expect(normalizePastedMath(pasted)).toBe(pasted);
  });
});

describe("MATH_GLYPH_RE covers server _UNICODE_OP_SUBS", () => {
  it("detects math operator glyphs parse.py rewrites, not prose dashes", () => {
    // Keep in sync with apps/api/app/services/math_service/parse.py _UNICODE_OP_SUBS.
    // En/em dashes are rewritten only after other math evidence — they must
    // not make `wait—what?` look like a formula.
    const serverOpGlyphs = ["×", "⋅", "·", "∗", "÷", "∕", "⁄", "−", "π", "∞"];
    for (const glyph of serverOpGlyphs) {
      expect(MATH_GLYPH_RE.test(glyph)).toBe(true);
    }
    expect(MATH_GLYPH_RE.test("–")).toBe(false);
    expect(MATH_GLYPH_RE.test("—")).toBe(false);
  });

  it("does not wrap short prose that only contains an em dash", () => {
    expect(pastedDeltaLooksLikeMath("wait—what?")).toBe(false);
    expect(normalizePastedMath("wait—what?")).toBe("wait—what?");
  });
});

describe("shouldProbeClipboardForImagePaste", () => {
  it("does not probe ordinary typing or autocorrect", () => {
    expect(shouldProbeClipboardForImagePaste("because")).toBe(false);
    expect(shouldProbeClipboardForImagePaste(" world")).toBe(false);
    expect(shouldProbeClipboardForImagePaste("he quick")).toBe(false);
    expect(shouldProbeClipboardForImagePaste("x=")).toBe(false);
  });

  it("probes a math-glyph paste or a large insert", () => {
    expect(shouldProbeClipboardForImagePaste("√16+x=20")).toBe(true);
    expect(shouldProbeClipboardForImagePaste("a".repeat(40))).toBe(true);
  });
});
