import { render, within } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import { AnswerBlock } from "@/components/rich/AnswerBlock";
import { lightTheme } from "@/lib/theme";
import { Space } from "@/lib/space";
import { Weight } from "@/lib/type";

const mockFormula = jest.fn((_props: Record<string, unknown>) => null);

jest.mock("@/components/rich/MathSvgView", () => ({
  MathSvgView: (props: Record<string, unknown>) => {
    mockFormula(props);
    return null;
  },
}));

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { text?: string; part?: string }) => {
      if (key === "rich.answer_a11y" && opts?.text != null) return `Answer: ${opts.text}`;
      if (key === "rich.answer_label") return "Answer";
      if (key === "rich.answer_part_label") return `Answer (${opts?.part})`;
      return key;
    },
  }),
}));

describe("AnswerBlock", () => {
  beforeEach(() => {
    mockFormula.mockClear();
  });

  it("draws the worked layout's Answer section: heading, then the value in a bordered box", async () => {
    const { getByTestId, getByText, queryByTestId } = await render(
      <AnswerBlock content={"label: answer\nverified: true\nx = 0"} />,
    );
    expect(getByText("Answer")).toBeOnTheScreen();
    expect(StyleSheet.flatten(getByTestId("answer-label").props.style)).toMatchObject({
      ...Weight.semibold,
      color: lightTheme.assistantText,
    });
    // No side rule: the bordered box alone frames the answer, centred in it.
    expect(queryByTestId("answer-rule")).toBeNull();
    const box = getByTestId("answer-box");
    expect(StyleSheet.flatten(box.props.style)).toMatchObject({
      backgroundColor: lightTheme.bg,
      borderWidth: 1,
      borderColor: lightTheme.border,
      flexDirection: "row",
      justifyContent: "center",
    });
    // The check sits in the box, after the value.
    expect(within(box).getByTestId("answer-success-check")).toBeOnTheScreen();
  });

  it("draws the Answer heading on a bare card too", async () => {
    const { getByTestId } = await render(<AnswerBlock content={"verified: true\n2 + 2 = 4"} />);
    expect(getByTestId("answer-label")).toBeOnTheScreen();
  });

  it("draws a model's answer in the same box, with no check", async () => {
    const { getByTestId, queryByTestId, getByText } = await render(
      <AnswerBlock content={"label: answer\nx = 0"} />,
    );
    expect(getByText("Answer")).toBeOnTheScreen();
    expect(StyleSheet.flatten(getByTestId("answer-box").props.style).backgroundColor).toBe(
      lightTheme.bg,
    );
    expect(queryByTestId("answer-success-check")).toBeNull();
  });

  it.each([
    String.raw`\begin{cases} x = 1 \\ y = 2 \end{cases}`,
    String.raw`\int_0^1 x^2 \, dx = \frac{1}{3}`,
  ])("draws the check after a heavy SVG answer once verified: %s", async (latex) => {
    const { getByTestId } = await render(<AnswerBlock content={`verified: true\n${latex}`} />);
    expect(mockFormula).toHaveBeenCalledTimes(1);
    expect(within(getByTestId("answer-box")).getByTestId("answer-success-check")).toBeOnTheScreen();
    mockFormula.mockClear();
    const unmarked = await render(<AnswerBlock content={latex} />);
    expect(mockFormula).toHaveBeenCalledTimes(1);
    expect(unmarked.queryByTestId("answer-success-check")).toBeNull();
  });

  it.each([
    ["\\$7.20", "Answer: $7.20"],
    ["\u00a310.00", "Answer: \u00a310.00"],
  ])("draws money with its sign: %s", async (body, label) => {
    // A tip or tax the server verified (apps/api/.../school/charges.py).
    const { getByLabelText } = await render(<AnswerBlock content={`verified: true\n${body}`} />);
    expect(getByLabelText(label)).toBeOnTheScreen();
  });

  it("keeps light finals on MathText (no display-math renderer)", async () => {
    const { getByLabelText } = await render(
      <AnswerBlock content={String.raw`x = \pm 2`} />,
    );
    expect(getByLabelText("Answer: x = ± 2")).toBeOnTheScreen();
    expect(mockFormula).not.toHaveBeenCalled();
  });

  it("shows the page background inside a thin grey border, like a written-out answer", async () => {
    const { getByTestId } = await render(<AnswerBlock content="x = 1" />);
    expect(StyleSheet.flatten(getByTestId("answer-box").props.style)).toMatchObject({
      backgroundColor: lightTheme.bg,
      borderWidth: 1,
      borderColor: lightTheme.border,
    });
  });

  it.each([["a", "Answer (a)"], ["b", "Answer (b)"]])(
    "labels one part's card with its letter: part %s",
    async (part, label) => {
      const { getByTestId } = await render(
        <AnswerBlock content={`part: ${part}\nverified: true\n2.04\\,\\mathrm{s}`} />,
      );
      expect(getByTestId("answer-label")).toHaveTextContent(label);
      expect(getByTestId("answer-box")).not.toHaveTextContent(/part/);
    },
  );

  it("marks the verified final with a green success check", async () => {
    const { getByTestId } = await render(<AnswerBlock content={"verified: true\n20"} />);
    expect(getByTestId("answer-success-check").props.color).toBe(
      lightTheme.success,
    );
  });

  it("draws no check for a value the server did not mark, or while streaming", async () => {
    const unmarked = await render(<AnswerBlock content="20" />);
    expect(unmarked.queryByTestId("answer-success-check")).toBeNull();
    const streaming = await render(
      <AnswerBlock content={"verified: true\n20"} settled={false} />,
    );
    expect(streaming.queryByTestId("answer-success-check")).toBeNull();
  });

  it("keeps the success check beside a fractional final instead of at the screen edge", async () => {
    const { getByTestId } = await render(
      <AnswerBlock content={"verified: true\n" + String.raw`x = \frac{1}{2}`} />,
    );
    const row = getByTestId("answer-row");
    const check = getByTestId("answer-success-check");
    expect(check.parent).toBe(row);
    expect(StyleSheet.flatten(check.props.style)).toMatchObject({ marginLeft: Space.xs });
  });

  it("BUG FIX regression: two roots joined with or stay on MathText so the last root is not clipped", async () => {
    const { getByLabelText } = await render(
      <AnswerBlock content={String.raw`x = \frac{1}{2} \text{ or } x = 3`} />,
    );
    expect(getByLabelText(/x = 3/)).toBeOnTheScreen();
    expect(mockFormula).not.toHaveBeenCalled();
  });

  it("keeps both T05 solution branches reachable at their normal math size", async () => {
    const latex = String.raw`x = 2 \pi k + \frac{\pi}{6} \text{ or } x = 2 \pi k + \frac{5 \pi}{6},\quad k \in \mathbb{Z}`;
    const { getByTestId, getAllByTestId, getByLabelText } = await render(
      <AnswerBlock content={latex} />,
    );
    expect(getByLabelText(/Answer: x = 2 π k.*or.*k ∈ ℤ/)).toBeOnTheScreen();
    expect(getAllByTestId("math-text-tall")).toHaveLength(2);
    for (const index of [0, 1]) {
      const viewport = getByTestId(`answer-line-scroll-${index}`);
      expect(viewport.props.horizontal).toBe(true);
      expect(viewport.props.showsHorizontalScrollIndicator).toBe(true);
      expect(StyleSheet.flatten(viewport.props.style).alignSelf).toBe(
        "stretch",
      );
      expect(
        StyleSheet.flatten(viewport.props.contentContainerStyle).minWidth,
      ).toBe("100%");
    }
    expect(mockFormula).not.toHaveBeenCalled();
  });

  it("provides horizontal overflow for a long native answer without an OR separator", async () => {
    const latex = String.raw`x = \frac{1}{2} + \frac{3}{4} + \frac{5}{6} + \frac{7}{8} + \frac{9}{10}`;
    const { getByTestId, queryByTestId } = await render(
      <AnswerBlock content={latex} />,
    );
    expect(getByTestId("answer-line-scroll-0").props.horizontal).toBe(true);
    expect(queryByTestId("answer-line-scroll-1")).toBeNull();
    expect(mockFormula).not.toHaveBeenCalled();
  });

  it("BUG FIX regression: strips a streaming ``` closer leaked into the answer body", async () => {
    const { queryByText } = await render(
      <AnswerBlock content={"x = -2 or x = 2\n```"} />,
    );
    expect(queryByText("```")).toBeNull();
    expect(queryByText(/x = −2/)).toBeOnTheScreen();
  });

  it("routes heavy \\begin{…} answers to the MathJax-SVG display path", async () => {
    const latex = String.raw`\begin{cases} x = 1 \\ y = 2 \end{cases}`;
    await render(<AnswerBlock content={latex} />);
    expect(mockFormula).toHaveBeenCalledTimes(1);
    const props = mockFormula.mock.calls[0][0];
    expect(props.latex).toBe(latex);
  });

  it("BUG FIX regression: a \\sqrt answer hosts MathText as a direct View (not clipped by a Text)", async () => {
    // iOS clips a View nested inside a Text to the line box — the radicand's
    // bottom (the digit under √) was cut off in this gray box. A sqrt must
    // render inside the answerRow View, never wrapped in a Text.
    const { getByTestId } = await render(
      <AnswerBlock content={String.raw`2\sqrt{2}`} />,
    );
    expect(getByTestId("answer-row")).toBeOnTheScreen();
    expect(getByTestId("math-sqrt-radicand")).toBeOnTheScreen();
    expect(mockFormula).not.toHaveBeenCalled();
  });

  it("uses MathJax-SVG for heavy answers regardless of WebView availability", async () => {
    const latex = String.raw`\begin{matrix}a&b\\c&d\end{matrix}`;
    await render(<AnswerBlock content={latex} />);
    expect(mockFormula).toHaveBeenCalled();
  });
});
