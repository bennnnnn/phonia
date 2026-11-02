import { applyPinnedTextChange, caretAfterMathBarClose } from "@/lib/math/composerChange";

describe("applyPinnedTextChange", () => {
  const frac = "$\\frac{8}{8}$";
  const pinFront = { start: 0, end: 0 };

  it("replays a denominator keystroke at the preview caret", () => {
    const native = "$\\frac{8}{8g}$";
    expect(applyPinnedTextChange(frac, native, pinFront)).toEqual({
      text: "g$\\frac{8}{8}$",
      caret: 1,
    });
  });

  it("keeps an insert that already landed on the pin", () => {
    expect(applyPinnedTextChange(frac, `do ${frac}`, pinFront)).toEqual({
      text: `do ${frac}`,
      caret: 3,
    });
  });

  it("backspaces in front of the formula, not inside a slot", () => {
    const prev = "a$\\frac{8}{8}$";
    const nativeDenDelete = "a$\\frac{8}{}$";
    expect(
      applyPinnedTextChange(prev, nativeDenDelete, { start: 1, end: 1 }),
    ).toEqual({
      text: "$\\frac{8}{8}$",
      caret: 0,
    });
  });

  it("inserts into the denominator when that slot is pinned", () => {
    const den = frac.indexOf("8}$") + 1;
    expect(applyPinnedTextChange(frac, "$\\frac{8}{8g}$", { start: den, end: den })).toEqual({
      text: "$\\frac{8}{8g}$",
      caret: den + 1,
    });
  });
});

describe("caretAfterMathBarClose", () => {
  it("sits after the last formula, not at the start of the draft", () => {
    expect(caretAfterMathBarClose("solve $x^2+1$")).toBe("solve $x^2+1$".length);
    expect(caretAfterMathBarClose("hello")).toBe(5);
    expect(caretAfterMathBarClose("$x$ more")).toBe("$x$".length);
  });
});
