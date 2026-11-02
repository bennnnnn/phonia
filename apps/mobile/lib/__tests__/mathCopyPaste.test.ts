import { extractPrimaryCopyText } from "@/lib/copyBlock";
import { normalizePastedMath } from "@/lib/math/pasteNormalize";
import { formatAssistantMathExpr, formatMathExpr } from "@/lib/math/formatInput";

function copyPaste(latex: string): { copied: string; pasted: string } {
  const copied = extractPrimaryCopyText(`\`\`\`answer\n${latex}\n\`\`\``);
  return { copied, pasted: normalizePastedMath(copied) };
}

describe("assistant Copy → math keypad Paste preserves mathematical grouping", () => {
  it.each([
    [String.raw`\frac{\pi^{2}}{6}`, "(π^2)/6", String.raw`$(\pi ^2)/6$`],
    [String.raw`\frac{a}{b}^{2}`, "(a/b)^2", String.raw`$(\frac{a}{b})^2$`],
    [String.raw`x^{\frac{a+b}{c}}`, String.raw`x^{\frac{a+b}{c}}`, String.raw`$x^{\frac{a+b}{c}}$`],
    [String.raw`9^{\frac{1}{6}}`, String.raw`9^{\frac{1}{6}}`, String.raw`$9^{\frac{1}{6}}$`],
    [String.raw`x^{a^{b+c}}`, String.raw`x^{a^{b+c}}`, String.raw`$x^{a^{b+c}}$`],
    [String.raw`\frac{3}{x^2}`, "3/(x^2)", "$3/(x^2)$"],
    [String.raw`\frac{a+b}{c}`, "(a+b)/c", "(a+b)/c"],
    [String.raw`\frac{1}{\frac{2}{3}}`, "1/(2/3)", "1/(2/3)"],
    [String.raw`\frac{\frac{1}{2}}{3}`, "(1/2)/3", "(1/2)/3"],
    [String.raw`\sqrt{\frac{1}{2}}`, "√(1/2)", String.raw`$\sqrt{1/2}$`],
    [String.raw`\frac{\sqrt{2}}{3}`, "(√(2))/3", String.raw`$(\sqrt{2})/3$`],
    [String.raw`\sqrt{1+\sqrt{2}}`, "√(1+√(2))", String.raw`$\sqrt{1+\sqrt{2}}$`],
    [String.raw`\sqrt[6]{9}`, "√[6](9)", String.raw`$\sqrt[6]{9}$`],
    [String.raw`x^{n+1}`, "x^{n+1}", "$x^{n+1}$"],
    [String.raw`x_{12}`, "x_{12}", "x_{12}"],
    [String.raw`5\ \mathrm{m}/\mathrm{s}^{2}`, "5 m/s^2", "$5 m/s^2$"],
  ])("round-trips %s without reassociating its operators", (latex, copied, pasted) => {
    expect(copyPaste(latex)).toEqual({ copied, pasted });
  });

  it.each(["x^2/6", "3/x^2", "a_i/2", "3/a_i", String.raw`\pi/2`, "2x/3", "3/xy", "x^2/6/3", "3/x!", "3/x'"])(
    "leaves ambiguous partial atoms intact: %s", (input) => {
      expect(formatMathExpr(input, { power: false })).toBe(input);
      expect(formatAssistantMathExpr(input)).toBe(input);
    },
  );

  it.each(["(x+1)^2/3", "3/(x+1)^2", "sin(x)/3"])(
    "does not split a powered group or function: %s", (input) => {
      expect(formatAssistantMathExpr(input)).not.toContain(String.raw`\frac`);
    },
  );

  it("keeps simple fraction copying and ordinary prose unchanged", () => {
    expect(copyPaste(String.raw`\frac{2}{3}`)).toEqual({ copied: "2/3", pasted: "2/3" });
    const prose = "The car travelled one hundred meters in twenty seconds today.";
    expect(normalizePastedMath(prose)).toBe(prose);
  });
});
