import { textLooksLikeMath } from "@/lib/math/composerIntent";

describe("textLooksLikeMath", () => {
  it("detects latex, glyphs, and homework verbs", () => {
    expect(textLooksLikeMath("$\\sqrt{9}$")).toBe(true);
    expect(textLooksLikeMath("solve x^2 = 9")).toBe(true);
    expect(textLooksLikeMath("√9")).toBe(true);
    expect(textLooksLikeMath("```math\n1+1\n```")).toBe(true);
  });

  it("does not treat ordinary chat as math", () => {
    expect(textLooksLikeMath("")).toBe(false);
    expect(textLooksLikeMath("what's the weather")).toBe(false);
    expect(textLooksLikeMath("I'm going later")).toBe(false);
  });

  it("does not treat a physics word problem as composer math", () => {
    const pasted =
      "A car starts from rest and accelerates at a constant rate of 1.2 m/s². How long does it take the car to travel a distance of 500 meters?";
    expect(textLooksLikeMath(pasted)).toBe(false);
  });

  it("BUG FIX regression: MATH_ASK words without math signal do not trigger (KB-039)", () => {
    // "solve" in prose without any math signal (digits, =, operators) should not trigger.
    expect(textLooksLikeMath("solve this mystery")).toBe(false);
    expect(textLooksLikeMath("what's the equation for happiness")).toBe(false);
    // But "solve" with a math signal should still trigger.
    expect(textLooksLikeMath("solve 2x + 3 = 7")).toBe(true);
    expect(textLooksLikeMath("factor x^2 - 1")).toBe(true);
  });
});
