import { render } from "@testing-library/react-native";
import { Dimensions, StyleSheet } from "react-native";

import { MathText } from "@/components/rich/MathText";
import { AnswerBlock } from "@/components/rich/AnswerBlock";
import { layoutMath } from "@/lib/math/layout";
import { findLayouts, layoutProblems } from "./layoutChecks";
import { fixImplicitExponents } from "@/lib/math/normalizeImplicit";
import { parseSimpleLatex } from "@/lib/math/text";

const ANSWER_FONT_SIZE = 20;

function laidOut(latex: string, fontSize = ANSWER_FONT_SIZE) {
  const layout = layoutMath(parseSimpleLatex(fixImplicitExponents(latex.trim())), fontSize);
  return { layout, problems: layoutProblems(layout, fontSize) };
}

const mockFormula = jest.fn((_props: Record<string, unknown>) => null);

jest.mock("@/components/rich/MathSvgView", () => ({
  MathSvgView: (props: Record<string, unknown>) => {
    mockFormula(props);
    return null;
  },
}));

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { text?: string }) =>
      key === "rich.answer_a11y" && opts?.text != null ? `Answer: ${opts.text}` : key,
  }),
}));

describe("standalone answer typography", () => {
  beforeEach(() => {
    jest.spyOn(Dimensions, "get").mockReturnValue({
      width: 390, height: 844, scale: 3, fontScale: 1,
    });
    mockFormula.mockClear();
  });
  afterEach(() => jest.restoreAllMocks());

  it("renders the exact C12 fraction larger than ordinary inline math", async () => {
    const latex = String.raw`\frac{\pi^{2}}{6}`;
    const answer = await render(<AnswerBlock content={latex} />);
    const { layout, problems } = laidOut(latex);
    const frac = findLayouts(layout, "frac")[0];
    const script = findLayouts(layout, "script")[0];
    expect(problems).toEqual([]);
    expect(answer.getByText("π")).toHaveStyle({ fontSize: 17.5, lineHeight: 22.5 });
    expect(answer.getByTestId("math-script")).toHaveStyle({ fontSize: script.fontSize });
    expect(answer.queryByText("²")).toBeNull();
    expect(script.fontSize).toBeLessThan(17.5);
    expect(answer.getByText("6")).toHaveStyle({ fontSize: 17.5 });
    expect(answer.getByTestId("math-frac")).toHaveStyle({ width: frac.width, height: frac.height });
    expect(answer.getByTestId("math-text-tall")).toHaveStyle({ minWidth: layout.width, height: layout.height });
    expect(answer.getByLabelText("Answer: π^2/6")).toBeOnTheScreen();
    expect(mockFormula).not.toHaveBeenCalled();

    const inline = await render(<MathText latex={latex} />);
    const inlineLayout = laidOut(latex, 16).layout;
    expect(inline.getByText("π")).toHaveStyle({ fontSize: 14, lineHeight: 18 });
    expect(inline.getByTestId("math-frac")).toHaveStyle({
      width: findLayouts(inlineLayout, "frac")[0].width,
      height: findLayouts(inlineLayout, "frac")[0].height,
    });
    expect(inlineLayout.width).toBeLessThan(layout.width);
  });

  it("scales fractional exponents in the answer without shrinking their digits", async () => {
    const { getByText, getByTestId, queryByText } = await render(<AnswerBlock content="9^{1/6}" />);
    const { layout } = laidOut("9^{1/6}");
    const script = findLayouts(layout, "script")[0];
    expect(getByText("9")).toHaveStyle({ fontSize: 20 });
    expect(queryByText("1/6")).toBeNull();
    expect(getByText("1")).toHaveStyle({ fontSize: script.fontSize });
    expect(getByText("6")).toHaveStyle({ fontSize: script.fontSize });
    expect(getByTestId("math-text-tall")).toHaveStyle({ height: layout.height });
    expect(getByTestId("math-fractional-sup")).toHaveStyle({ paddingBottom: script.raise });
  });

  it("preserves lowercase x in the final answer with an italic math glyph", async () => {
    const { getByLabelText, getByTestId } = await render(
      <AnswerBlock content={String.raw`x = \pm 1`} />,
    );
    expect(getByLabelText("Answer: x = ± 1")).toBeOnTheScreen();
    expect(getByTestId("math-variable")).toHaveTextContent("x");
    expect(getByTestId("math-variable")).toHaveStyle({
      fontFamily: "KaTeX_MathItalic",
    });
  });

  it("scales indexed roots and their radicands together", async () => {
    const { getByText, getByTestId } = await render(<AnswerBlock content={String.raw`\sqrt[6]{9}`} />);
    const { layout } = laidOut(String.raw`\sqrt[6]{9}`);
    const radical = findLayouts(layout, "sqrt")[0];
    expect(getByText("6")).toHaveStyle({
      fontSize: radical.index?.fontSize,
      lineHeight: radical.index?.lineHeight,
    });
    expect(getByText("9")).toHaveStyle({ fontSize: 20, lineHeight: 25 });
    expect(getByTestId("math-text-tall")).toHaveStyle({ height: layout.height });
  });

  it("keeps native fraction bounds proportional at larger accessibility text scale", async () => {
    jest.spyOn(Dimensions, "get").mockReturnValue({
      width: 390, height: 844, scale: 3, fontScale: 1.6,
    });
    const { layout } = laidOut(String.raw`\frac{\pi^{2}}{6}`);
    const frac = findLayouts(layout, "frac")[0];
    const { getByTestId, getByText } = await render(<AnswerBlock content={String.raw`\frac{\pi^{2}}{6}`} />);
    expect(getByTestId("math-frac")).toHaveStyle({ width: frac.width * 1.6, height: frac.height * 1.6 });
    expect(getByTestId("math-text-tall")).toHaveStyle({ minWidth: layout.width * 1.6, height: layout.height * 1.6 });
    // Native Text applies fontScale itself; the style must not multiply it twice.
    expect(getByText("6")).toHaveStyle({ fontSize: 17.5 });
    expect(getByTestId("answer-line-scroll-0").props.horizontal).toBe(true);
  });

  it.each([
    ["27", "27", 20],
    ["Value: $x^2$", "Value: x", 20],
    [String.raw`Area: $\frac{1}{2}$`, "1", 17.5],
  ] as const)(
    "uses the answer type scale across native content branches: %s", async (content, value, fontSize) => {
      const { getByText } = await render(<AnswerBlock content={content} />);
      expect(getByText(value)).toHaveStyle({ fontSize });
    },
  );

  it("retains horizontal overflow instead of reducing a long answer's type size", async () => {
    const content = String.raw`x = \frac{1}{2} + \frac{3}{4} + \frac{5}{6} + \frac{7}{8} + \frac{9}{10} + \frac{11}{12} + \frac{13}{14}`;
    const { getByTestId, getByText } = await render(<AnswerBlock content={content} />);
    expect(getByTestId("answer-line-scroll-0").props.horizontal).toBe(true);
    const bounds = StyleSheet.flatten(getByTestId("math-text-tall").props.style);
    const { layout, problems } = laidOut(content);
    expect(problems).toEqual([]);
    expect(bounds.minWidth).toBe(layout.width);
    expect(bounds.minWidth).toBeGreaterThan(280);
    expect(bounds.flexShrink).toBe(0);
    expect(getByText("14")).toHaveStyle({ fontSize: 17.5 });
  });
});
