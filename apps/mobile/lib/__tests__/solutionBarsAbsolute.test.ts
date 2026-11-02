import { rewriteSolutionSeparatorBars } from "@/lib/math/solutionBars";
import { parseSimpleLatex, segmentsToPlain } from "@/lib/math/text";

describe("only complete assignment alternatives use OR bars", () => {
  it.each([
    String.raw`x=1|x=2|x=3`,
    String.raw`x=\frac{1}{2} \mid x=3`,
    String.raw`x = |a| | x = -|a|`,
    String.raw`x_1=2 \bigm| x_1=3`,
  ])("retains supported alternative assignment intent: %s", (source) => {
    expect(rewriteSolutionSeparatorBars(source)).toContain(String.raw`\text{ or }`);
  });

  it.each([
    String.raw`\lim_{a \to 0^{-}} \int_{-1}^{a} \frac{1}{x} dx = \lim_{a \to 0^{-}} \left( \ln|a| - \ln|-1| \right) = -\infty`,
    String.raw`F(x)=\ln|x|=c`,
    String.raw`x=|a|=2`,
    String.raw`x=\left|a\right|=2`,
    String.raw`x=\lvert a\rvert=2`,
    String.raw`x=\vert a\vert=2`,
    String.raw`x=\{a \mid a=2\}`,
    String.raw`x=\{a | a=2\}`,
    String.raw`x=\frac{|a|}{|b|}=c`,
    String.raw`x=\left|x=2\right|`,
    String.raw`x=\bigl|x=2\bigr|`,
    String.raw`x=|x=2|`,
    String.raw`x=1|x=2|`,
    String.raw`x=1 | x=`,
    String.raw`x=\frac{1}{2 | x=3`,
    String.raw`x=1 \middleman x=2`,
    String.raw`x=1 \| x=2`,
    String.raw`x=1 | y=2`,
    String.raw`x=1=2 | x=3`,
    String.raw`x=1 | x=2=3`,
  ])("preserves delimiters, equality chains and incomplete math byte-exact: %s", (source) => {
    expect(rewriteSolutionSeparatorBars(source)).toBe(source);
  });

  it("keeps log absolute-value notation through the actual native parser", () => {
    const value = segmentsToPlain(parseSimpleLatex(String.raw`F(x)=\ln|x|=c`));
    expect(value).not.toContain("or");
    expect(value).toContain("|x|");
  });
});
