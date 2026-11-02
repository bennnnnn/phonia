import {
  completeStreamingLatex,
  hasIncompleteStreamingLatex,
  prepareStreamingMathText,
} from "@/lib/math/streaming";
import { splitInlineMath } from "@/lib/markdown/inlineMath";
import { parseSimpleLatex, restoreMathEscapes, segmentsToPlain } from "@/lib/math/text";

describe("streaming math preview", () => {
  it.each([
    String.raw`\fr`,
    String.raw`\frac{1}`,
    String.raw`\frac{1}{`,
    String.raw`\sqrt{3`,
    String.raw`\sqrt[`,
    String.raw`x^`,
    String.raw`x_`,
    String.raw`\begin{cases}x`,
  ])(
    "holds incomplete syntax without inventing a finished answer: %s", (body) => {
      expect(hasIncompleteStreamingLatex(body)).toBe(true);
    },
  );
  it.each([String.raw`\frac{1}{2}`, String.raw`\sqrt[3]{3}`, String.raw`\int_0^1 x^2\,dx`])(
    "allows a complete math preview: %s", (body) => {
      expect(hasIncompleteStreamingLatex(body)).toBe(false);
    },
  );
  it.each(["$\\", String.raw`$\fr`, String.raw`$x^`, String.raw`\(\frac{1}`, String.raw`\[\int_0^1`, String.raw`$$\sqrt{3`])(
    "retains preceding prose while an explicit math span is open: %s", (formula) => {
      expect(prepareStreamingMathText(`Result: ${formula}`)).toEqual({ text: "Result: ", pending: true });
    },
  );
  it("protects a just-closed formula before the line-ending token arrives", () => {
    const result = prepareStreamingMathText(String.raw`Thus \(x_1 * x_2 = \frac{1}{2}\).`);
    expect(result.pending).toBe(false);
    const math = splitInlineMath(result.text).find((part) => part.type === "math");
    expect(segmentsToPlain(parseSimpleLatex(math!.value))).toBe("x_1 * x_2 = 1/2");
  });
  it.each([
    String.raw`\int_0^1 x^2\,dx=\frac{1}{3}`,
    String.raw`\text{force}=\frac{m}{s}`,
  ])("keeps multiple protected commands classified as math: %s", (formula) => {
    const result = prepareStreamingMathText(`Result: $${formula}$`);
    const math = splitInlineMath(result.text).filter((part) => part.type === "math");
    expect(math).toHaveLength(1);
    expect(restoreMathEscapes(math[0].value)).toBe(formula);
    expect(result.pending).toBe(false);
  });
  it("draws a closed fraction and leaves an unfinished one blank", () => {
    expect(completeStreamingLatex(String.raw`\frac{1}{2}`)).toBe(String.raw`\frac{1}{2}`);
    expect(completeStreamingLatex(String.raw`\frac{1}{2} + \frac{3`)).toBe(String.raw`\frac{1}{2} +`);
    expect(completeStreamingLatex(String.raw`\frac{1`)).toBe("");
    expect(completeStreamingLatex(String.raw`\begin{aligned} x &= 1`)).toBe("");
  });

  it.each([String.raw`So $12 \times 3`, String.raw`Check: $\$43 \text{ per hour}`, String.raw`Then $[\text{H}^+]`])(
    "holds an unfinished formula whose line already shows TeX: %s", (text) => {
      expect(prepareStreamingMathText(text).pending).toBe(true);
    },
  );

  it("reads a price-like span that holds a TeX command as maths, and one without as prose", () => {
    expect(splitInlineMath(String.raw`So $4! = 4 \times 3 \times 2 \times 1 = 24$.`)[1]).toEqual({
      type: "math",
      value: String.raw`4! = 4 \times 3 \times 2 \times 1 = 24`,
    });
    expect(splitInlineMath("It costs $5 each, so the total = $15.")).toEqual([
      { type: "text", value: "It costs $5 each, so the total = $15." },
    ]);
  });

  it.each(["Price: $5 and $10.", "It costs $5 for x^2 copies", String.raw`Price: \$5`, "Budget: ($$)", 'Type `$\\frac` in LaTeX.']) (
    "preserves code and currency: %s", (text) => {
      expect(prepareStreamingMathText(text)).toEqual({ text, pending: false });
    },
  );
});
