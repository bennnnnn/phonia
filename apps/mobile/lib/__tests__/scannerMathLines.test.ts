import { preprocessMarkdown } from "@/lib/markdown/preprocess";
import { markdownItInstance } from "@/lib/markdown/parser";
import { preprocessMarkdownForStream } from "@/lib/markdown/preprocessStream";
import { splitInlineMath } from "@/lib/markdown/inlineMath";
import { restoreMathEscapes } from "@/lib/math/text";

const SCANNER_RESPONSE = "Here's how to solve for $x$ step-by-step:\n\n1.  **Original Equation:** `$2x + 3 = 5$`\n2.  **Subtract 3 from both sides:** To isolate the term with $x$, subtract 3 from both sides of the equation.\n    `$2x + 3 - 3 = 5 - 3$`\n    `$2x = 2$`\n3.  **Divide by 2:** To solve for $x$, divide both sides by 2.\n    `$\\frac{2x}{2} = \\frac{2}{2}$`\n    `$x = 1$`\n\nSo, the solution is $x = 1$.";
const children = (source: string) => markdownItInstance.parse(preprocessMarkdown(source), {}).flatMap((token) => token.children ?? []);

describe("separate consecutive calculation lines", () => {
  it("preserves both pairs of steps from the actual scanner reply as Markdown hard breaks", () => {
    const tokens = children(SCANNER_RESPONSE);
    const breaks = tokens.flatMap((token, index) => token.type === "hardbreak" ? [index] : []);
    expect(breaks).toHaveLength(2);
    expect(restoreMathEscapes(tokens[breaks[0]-1].content)).toBe("$2x + 3 - 3 = 5 - 3$");
    expect(restoreMathEscapes(tokens[breaks[0]+1].content)).toBe("$2x = 2$");
    expect(restoreMathEscapes(tokens[breaks[1]-1].content)).toBe(String.raw`$\frac{2x}{2} = \frac{2}{2}$`);
    expect(restoreMathEscapes(tokens[breaks[1]+1].content)).toBe("$x = 1$");
  });
  it("recomputes the stable streaming prefix once the next calculation line completes", () => {
    const first = "1. Solve:\n   `$2x=2$`\n";
    const initial = preprocessMarkdownForStream(first, null);
    const complete = preprocessMarkdownForStream(first + "   `$x=1$`\n", initial.cache);
    expect(complete.prepared).toBe(preprocessMarkdown(first + "   `$x=1$`\n"));
    expect(complete.prepared).toContain("$2x=2$  \n");
  });
  it.each([
    "A prose line\ncontinues here.",
    "Use $x=2$ here.\nThen use $y=3$.",
    "```python\n$x=2$\n$y=3$\n```",
    "~~~python\n$x=2$\n$y=3$\n~~~",
    "$5\n$10",
  ])("leaves ordinary wrapping, code and currency unchanged: %s", (source) => {
    expect(children(source).filter((token) => token.type === "hardbreak")).toEqual([]);
    if (source.includes("python")) expect(preprocessMarkdown(source)).toBe(source);
  });
  it("keeps an explicit multiline inline formula together", () => {
    const source = String.raw`Compute \(\n x^2 +\n 2x \) now.`.replace(/\\n/g, "\n");
    const tokens = children(source);
    expect(tokens.some((token) => token.type === "hardbreak")).toBe(false);
    const math = tokens.flatMap((token) => token.type === "text" ? splitInlineMath(token.content).filter((part) => part.type === "math") : []);
    expect(math.map((part) => restoreMathEscapes(part.value))).toEqual(["x^2 + 2x"]);
  });
});
