import {
  caretAfterExpression,
  findDraftNodes,
  spliceMathBackspace,
} from "@/lib/math/draftSlots";
import { MATH_KEYBOARD_SYMBOLS, spliceMathInsert } from "@/lib/math/keyboardSymbols";

describe("findDraftNodes", () => {
  it("finds fractions, roots, scripts, abs, and groups", () => {
    const nodes = findDraftNodes("$\\frac{8}{8}\\sqrt{x}x^{2}|y|\\sin()$");
    expect(nodes.filter((n) => n.kind !== "text").map((n) => n.kind)).toEqual([
      "frac",
      "sqrt",
      "script",
      "abs",
      "group",
    ]);
  });

  it("keeps an empty binomial, vector, and d/d slot as boxes", () => {
    expect(findDraftNodes("$\\binom{}{}$").some((n) => n.kind === "binom")).toBe(true);
    expect(findDraftNodes("$\\vec{}$").some((n) => n.kind === "vec")).toBe(true);
    expect(findDraftNodes("d{}").some((n) => n.kind === "brace")).toBe(true);
    expect(findDraftNodes("$\\mathrm{rad}$").some((n) => n.kind === "brace")).toBe(false);
  });

  it("keeps \\sin() / \\cos() as one group, not a repeated name", () => {
    const text = "$\\cos()$";
    const nodes = findDraftNodes(text);
    expect(nodes.filter((n) => n.kind === "group")).toHaveLength(1);
    const leftover = nodes
      .filter((n) => n.kind === "text")
      .map((n) => text.slice(n.start, n.end).replace(/\$/g, ""))
      .join("");
    expect(leftover).not.toMatch(/cos|\\cos/i);
  });

  it("keeps the continue caret inside the closing dollar", () => {
    expect(caretAfterExpression("$\\frac{8}{8}$")).toBe("$\\frac{8}{8}$".length - 1);
  });
});

describe("spliceMathBackspace", () => {
  it("deletes a denominator digit without exposing raw \\frac braces", () => {
    const text = "$\\frac{8}{8}$";
    const den = text.lastIndexOf("8") + 1;
    const once = spliceMathBackspace(text, { start: den, end: den });
    expect(once.text).toBe("$\\frac{8}{}$");
    const twice = spliceMathBackspace(once.text, once.selection);
    expect(twice.text).toBe("$\\frac{}{}$");
    const gone = spliceMathBackspace(twice.text, twice.selection);
    expect(gone.text).toBe("");
  });

  it("deletes \\times after a fraction instead of the closing brace", () => {
    const text = "$\\frac{8}{8}\\times $";
    const caret = text.length - 1;
    const result = spliceMathBackspace(text, { start: caret, end: caret });
    expect(result.text).toBe("$\\frac{8}{8}$");
  });

  it("deletes the first numerator digit when the caret is at the front", () => {
    const text = "$\\frac{8}{8}$";
    const result = spliceMathBackspace(text, { start: 1, end: 1 });
    expect(result.text).toBe("$\\frac{}{8}$");
  });

  it("deletes inside a nested superscript instead of the closing brace", () => {
    const text = "$\\frac{d^{2}}{dx^{2}}$";
    const result = spliceMathBackspace(text, { start: text.length - 1, end: text.length - 1 });
    expect(result.text).toBe("$\\frac{d^{2}}{dx^{}}$");
    let state = result;
    const seen = [state.text];
    while (state.text) {
      state = spliceMathBackspace(state.text, state.selection);
      seen.push(state.text);
      if (seen.length > 16) break;
    }
    expect(seen.at(-1)).toBe("");
    expect(seen.join("\n")).not.toMatch(/\\frac[^}]*$/m);
  });

  it("deletes a unit command as one key", () => {
    const text = "$\\mathrm{rad}$";
    const result = spliceMathBackspace(text, { start: text.length - 1, end: text.length - 1 });
    expect(result.text).toBe("");
  });

  it("deletes a binomial as one key", () => {
    const text = "$\\binom{}{}$";
    const result = spliceMathBackspace(text, { start: text.length - 1, end: text.length - 1 });
    expect(result.text).toBe("");
  });

  it("deletes a thin space with its differential", () => {
    const text = "$\\,dx$";
    let state = spliceMathBackspace(text, { start: text.length - 1, end: text.length - 1 });
    const seen = [state.text];
    while (state.text) {
      state = spliceMathBackspace(state.text, state.selection);
      seen.push(state.text);
      if (seen.length > 6) break;
    }
    expect(seen).not.toContain("$\\$");
    expect(state.text).toBe("");
  });

  it("deletes a finished fraction from the trailing dollar without leaking latex", () => {
    const text = "$\\frac{8}{8}$";
    const result = spliceMathBackspace(text, { start: text.length - 1, end: text.length - 1 });
    expect(result.text).toBe("$\\frac{8}{}$");
  });

  it.each([
    ["$\\cos()$", "$\\cos()$".length - 1, ""],
    ["$\\sin()$", "$\\sin()$".length - 1, ""],
    ["$\\sqrt{}$", "$\\sqrt{}$".length - 1, ""],
    ["$x^{}$", "$x^{}$".length - 1, "$x$"],
    ["$x_{}$", "$x_{}$".length - 1, "$x$"],
    ["$||$", "$||$".length - 1, ""],
    ["$[]$", "$[]$".length - 1, ""],
    ["$\\{\\}$", "$\\{\\}$".length - 1, ""],
  ])("peels empty %s without leaking latex", (text, caret, expected) => {
    const result = spliceMathBackspace(text, { start: caret, end: caret });
    expect(result.text).toBe(expected);
    expect(result.text).not.toMatch(/\\(cos|sin|sqrt|frac)\b/);
    expect(result.text).not.toMatch(/[{}]/);
  });

  it("types a digit inside [] and \\{\\}, then deletes the pair together", () => {
    const digit = MATH_KEYBOARD_SYMBOLS.find((spec) => spec.id === "digit-1")
      ?? { id: "digit-1", label: "1", insert: "1", cursorOffset: 1, group: "pad" as const };
    for (const id of ["brackets", "braces"] as const) {
      const spec = MATH_KEYBOARD_SYMBOLS.find((item) => item.id === id)!;
      const opened = spliceMathInsert("", { start: 0, end: 0 }, spec);
      const typed = spliceMathInsert(opened.text, opened.selection, digit);
      expect(typed.text).toBe(id === "brackets" ? "$[1]$" : "$\\{1\\}$");
      const withoutDigit = spliceMathBackspace(typed.text, typed.selection);
      expect(withoutDigit.text).toBe(id === "brackets" ? "$[]$" : "$\\{\\}$");
      const gone = spliceMathBackspace(withoutDigit.text, withoutDigit.selection);
      expect(gone.text).toBe("");
    }
  });

  it("BUG FIX regression: collapseEmptyMath does not corrupt $$display math$$ with content (KB-040)", () => {
    // Backspace inside display math should NOT strip the $$ delimiters when
    // there's content between them. Position 3 (^) deleted → "$$x2$$" (still has $$).
    const text = "$$x^2$$";
    const result = spliceMathBackspace(text, { start: 4, end: 4 });
    expect(result.text).toBe("$$x2$$");
    // The $$ delimiters are preserved because there's still content inside.
    expect(result.text).toContain("$$");
  });
});
