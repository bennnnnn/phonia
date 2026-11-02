import { normalizeUnicodeScripts, toSuperscript } from "@/lib/unicodeSupSub";

describe("toSuperscript", () => {
  it("maps digits and common letters to Unicode superscripts", () => {
    expect(toSuperscript("2")).toBe("²");
    expect(toSuperscript("x")).toBe("ˣ");
    expect(toSuperscript("n")).toBe("ⁿ");
    expect(toSuperscript("10")).toBe("¹⁰");
  });

  it("maps +/-/= and parens", () => {
    expect(toSuperscript("+")).toBe("⁺");
    expect(toSuperscript("-")).toBe("⁻");
    expect(toSuperscript("(2)")).toBe("⁽²⁾");
  });

  it("maps a slash fraction so 3^{2/3} is not baseline 32/3", () => {
    expect(toSuperscript("2/3")).toBe("²\u2044³");
    expect(toSuperscript("1/2")).toBe("¹\u2044²");
    expect(toSuperscript("2/q")).toBeNull();
  });

  it("returns null when any char lacks a Unicode superscript", () => {
    expect(toSuperscript("q")).toBeNull();
    expect(toSuperscript("C")).toBeNull();
    expect(toSuperscript("2,3")).toBeNull();
  });

  it("returns null for empty input", () => {
    expect(toSuperscript("")).toBeNull();
  });
});

describe("normalizeUnicodeScripts", () => {
  it("rewrites unicode superscript runs to caret LaTeX", () => {
    expect(normalizeUnicodeScripts("x²")).toBe("x^2");
    expect(normalizeUnicodeScripts("2¹⁰")).toBe("2^{10}");
    expect(normalizeUnicodeScripts("eˣ")).toBe("e^x");
  });

  it("rewrites unicode subscript runs to underscore LaTeX", () => {
    expect(normalizeUnicodeScripts("a₁₀")).toBe("a_{10}");
    expect(normalizeUnicodeScripts("xₙ")).toBe("x_n");
  });

  it("leaves ordinary ASCII math unchanged", () => {
    expect(normalizeUnicodeScripts("x^2 + y_1")).toBe("x^2 + y_1");
  });
});
