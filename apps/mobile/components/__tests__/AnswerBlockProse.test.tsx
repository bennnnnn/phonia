// The incline answer card: the model wrote a sentence in the ```answer fence. Every
// dollar pair was unwrapped, so "which at … gives" was typeset as italic variables,
// and the one long line ran off the card's edge with nothing to show there was more.
import { fireEvent, render, within } from "@testing-library/react-native";
import { ScrollView, StyleSheet } from "react-native";

import { AnswerBlock } from "@/components/rich/AnswerBlock";
import { MATH_VARIABLE_FONT } from "@/lib/fonts";
import { answerReadsAsProse } from "@/lib/math/answerLayout";

jest.mock("@/components/rich/MathSvgView", () => ({ MathSvgView: () => null }));

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { text?: string }) =>
      key === "rich.answer_a11y" && opts?.text != null ? `Answer: ${opts.text}` : key,
  }),
}));

const INCLINE = String.raw`$a = g(\sin\theta - \mu\cos\theta)$, which at $30^\circ$ gives $a = 4.9 - 8.5\mu\ \text{m/s}^2$ down the slope.`;

describe("answerReadsAsProse", () => {
  it.each([
    [INCLINE, true],
    [String.raw`$E = mc^2$, where energy equals mass times $c^2$`, true],
    // A formula with stray wraps, branches and a unit stay maths.
    [String.raw`n! = n $\times$ (n-1)!`, false],
    [String.raw`$x = 3$ or $x = -2$`, false],
    [String.raw`$v = 19.8$ m/s`, false],
    // Words with no maths, or LaTeX outside the dollars, are not a sentence answer.
    ["the box slides down the slope", false],
    [String.raw`$a = 4.9$ \text{down the slope}`, false],
  ])("%s → %s", (text, prose) => {
    expect(answerReadsAsProse(text)).toBe(prose);
  });
});

describe("AnswerBlock with a sentence answer", () => {
  it("draws its words as text and wraps them inside the card", async () => {
    const { getByTestId, getByText, queryByTestId } = await render(<AnswerBlock content={INCLINE} />);
    const flow = within(getByTestId("answer-box")).getByTestId("answer-prose");
    expect(flow).toHaveStyle({ flexWrap: "wrap" });
    for (const word of ["which", "gives", "down", "slope."]) {
      const fontFamily = StyleSheet.flatten(getByText(word).props.style).fontFamily;
      expect(fontFamily).not.toBe(MATH_VARIABLE_FONT);
    }
    // No sideways scroller: the sentence wraps rather than running off the edge.
    expect(queryByTestId("answer-line-scroll-0")).toBeNull();
    expect(within(flow).getAllByTestId("math-text-tall").length).toBeGreaterThan(0);
  });

  it("reads the sentence aloud with its formulas spoken", async () => {
    const { getByLabelText } = await render(<AnswerBlock content={INCLINE} />);
    expect(getByLabelText(/^Answer: a = g\(sin.*, which at 30° gives a = 4\.9 .* down the slope\.$/)).toBeOnTheScreen();
  });
});

describe("AnswerBlock with a long formula", () => {
  it("flashes the scroll bar once the line is wider than the card", async () => {
    const flash = jest.spyOn(ScrollView.prototype, "flashScrollIndicators");
    flash.mockClear();
    const { getByTestId } = await render(
      <AnswerBlock content={String.raw`x = \frac{-b + \sqrt{b^2 - 4ac}}{2a} = \frac{-7 + \sqrt{49 + 120}}{6} = 1`} />,
    );
    const line = getByTestId("answer-line-scroll-0");
    await fireEvent(line, "layout", { nativeEvent: { layout: { width: 200, height: 40, x: 0, y: 0 } } });
    expect(flash).not.toHaveBeenCalled();
    await fireEvent(line, "contentSizeChange", 520, 40);
    expect(flash).toHaveBeenCalledTimes(1);
    await fireEvent(line, "contentSizeChange", 530, 40);
    expect(flash).toHaveBeenCalledTimes(1);
  });

  it("leaves a line that fits alone", async () => {
    const flash = jest.spyOn(ScrollView.prototype, "flashScrollIndicators");
    flash.mockClear();
    const { getByTestId } = await render(<AnswerBlock content={String.raw`\frac{\pi^{2}}{6}`} />);
    const line = getByTestId("answer-line-scroll-0");
    await fireEvent(line, "contentSizeChange", 180, 40);
    await fireEvent(line, "layout", { nativeEvent: { layout: { width: 200, height: 40, x: 0, y: 0 } } });
    expect(flash).not.toHaveBeenCalled();
  });
});
