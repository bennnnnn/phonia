import { markdownHasNestedMathView, splitInlineMath } from "@/lib/markdown/inlineMath";
import { parseRichMathText } from "@/lib/markdown/richMathText";

describe("rich math text", () => {
  it("recognizes the cube-root note without processing nested rich fences", () => {
    const parts = parseRichMathText(String.raw`The expression doesn't simplify, so $\sqrt[3]{3}$ is exact.`);
    expect(parts.filter((part) => part.type === "math")).toEqual([
      { type: "math", value: String.raw`\sqrt[3]{3}` },
    ]);
    expect(parts.filter((part) => part.type === "text").map((part) => part.value).join("")).toBe(
      "The expression doesn't simplify, so  is exact.",
    );
  });

  it("preserves emphasis around math and multiplication inside math", () => {
    expect(parseRichMathText(String.raw`**Exact $a*b*c$**`)).toEqual([
      { type: "text", value: "Exact ", bold: true },
      { type: "math", value: "a*b*c", bold: true },
    ]);
  });

  it.each([
    [String.raw`\(\int_0^1 x^2\,dx\)`, String.raw`\int_0^1 x^2\,dx`],
    [String.raw`\[\sum_{n=1}^{\infty} n^{-2}\]`, String.raw`\sum_{n=1}^{\infty} n^{-2}`],
    [String.raw`$$\frac{1}{2}$$`, String.raw`\frac{1}{2}`],
  ])("reads a complete math span: %s", (source, value) => {
    expect(parseRichMathText(source)).toEqual([{ type: "math", value }]);
  });

  it("keeps LaTeX source examples in code and preserves prices", () => {
    expect(parseRichMathText('Use `$\\frac{1}{2}$` with $5 and $10.')).toEqual([
      { type: "text", value: "Use " },
      { type: "code", value: "$\\frac{1}{2}$" },
      { type: "text", value: " with $5 and $10." },
    ]);
    expect(splitInlineMath(String.raw`Prices: \$5 and \$10; solve $x+1=2$.`)).toEqual([
      { type: "text", value: String.raw`Prices: \$5 and \$10; solve ` },
      { type: "math", value: "x+1=2" },
      { type: "text", value: "." },
    ]);
    expect(splitInlineMath('`$x^2$`')).toEqual([{ type: "text", value: '`$x^2$`' }]);
    expect(splitInlineMath("$2 sin x$ and $2 x$" )).toEqual([
      { type: "math", value: "2 sin x" },
      { type: "text", value: " and " },
      { type: "math", value: "2 x" },
    ]);
    expect(splitInlineMath("Costs $5 and $10; solve $x=2$." )).toEqual([
      { type: "text", value: "Costs $5 and $10; solve " },
      { type: "math", value: "x=2" },
      { type: "text", value: "." },
    ]);
  });

  it("lifts only delimited exponents out of a text run", () => {
    expect(markdownHasNestedMathView("$x^2$")).toBe(true);
    expect(markdownHasNestedMathView("a^2(1+9+81)")).toBe(false);
    expect(markdownHasNestedMathView("`__init__` vs `__new__`")).toBe(false);
  });
});
