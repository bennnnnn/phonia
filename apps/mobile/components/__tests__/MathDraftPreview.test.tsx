import { configure, fireEvent, render, within } from "@testing-library/react-native";

import { MathDraftPreview } from "@/features/chat/components/MathDraftPreview";
import { sentMessageShowsMathPreview } from "@/lib/math/draftText";
import { lightTheme } from "@/lib/theme";

// These tests read the drawing. The composer's preview is hidden from screen readers (its
// text field reads the draft), so queries look inside hidden views unless a test says not to.
configure({ defaultIncludeHiddenElements: true });
const READER = { includeHiddenElements: false };

describe("sentMessageShowsMathPreview", () => {
  it("keeps a question around an equation as text", () => {
    expect(sentMessageShowsMathPreview("Why does $x^2 = 9$ have two solutions?")).toBe(false);
    expect(sentMessageShowsMathPreview("$x^2 = 9$")).toBe(true);
  });
});

describe("MathDraftPreview for a screen reader", () => {
  it("leaves the composer's draft to its text field: no unnamed caret buttons", async () => {
    const { queryAllByRole, getByTestId } = await render(
      <MathDraftPreview input={String.raw`$\frac{1}{2}$ + $x_1^2$`} caret={0} onMoveCaret={jest.fn()} />,
    );
    expect(queryAllByRole("button", READER)).toHaveLength(0);
    expect(getByTestId("math-draft-preview").props.accessibilityElementsHidden).toBe(true);
  });

  it("reads a sent math message as one element, its maths in words", async () => {
    const { queryAllByRole, getByRole } = await render(
      <MathDraftPreview input={String.raw`Solve $\frac{1}{2}x = 3$`} sent showCaret={false} />,
    );
    expect(queryAllByRole("button", READER)).toHaveLength(0);
    expect(getByRole("text", { name: "Solve 1/2x = 3", ...READER })).toBeOnTheScreen();
  });
});

describe("MathDraftPreview", () => {
  it("draws the keyboard's x^{2} as a reply draws x²: italic x, a smaller 2 against it", async () => {
    const { getByText, getByTestId } = await render(
      <MathDraftPreview input="$x^{2}$" sent showCaret={false} />,
    );
    expect(getByText("x")).toHaveStyle({ fontFamily: "KaTeX_MathItalic", fontSize: 16 });
    expect(getByText("2")).toHaveStyle({ fontSize: 11 });
    expect(getByTestId("math-slot-sup")).toHaveStyle({ minWidth: 0 });
  });

  it("draws the keypad's set and upright letters, never their command names", async () => {
    const { getAllByTestId, getByText, queryByText } = await render(
      <MathDraftPreview input={String.raw`$\mathbb{N}$ $\mathbb{R}$ $\mathrm{i}$`} sent showCaret={false} />,
    );
    expect(getAllByTestId("math-blackboard").map((letter) => letter.props.children)).toEqual(["N", "R"]);
    expect(getByText("i")).toBeOnTheScreen();
    expect(queryByText(/mathbb|mathrm/)).toBeNull();
  });

  it("reads a letter after an earlier $…$ as math too", async () => {
    const { getByText } = await render(
      <MathDraftPreview input={String.raw`$\sqrt{2}$ $x_{2}$`} sent showCaret={false} />,
    );
    expect(getByText("x")).toHaveStyle({ fontFamily: "KaTeX_MathItalic" });
  });

  it("raises a script inside a fraction onto its base", async () => {
    const { getAllByTestId } = await render(
      <MathDraftPreview input={String.raw`$\frac{d^{2}}{dx^{2}}$`} sent showCaret={false} />,
    );
    expect(getAllByTestId("math-script-stack")).toHaveLength(2);
  });

  it("keeps the text before an integral or a sum, not only the operator", async () => {
    const integral = await render(
      <MathDraftPreview input={String.raw`$\int $ $\int_{0}^{1}$`} sent showCaret={false} />,
    );
    expect(integral.getAllByText("∫")).toHaveLength(2);
    const sum = await render(<MathDraftPreview input={String.raw`$y=\sum_{n}^{3}$`} sent showCaret={false} />);
    expect(sum.getByText("y")).toBeOnTheScreen();
  });

  it("draws a row of calculus keys, which read as prose and drew an empty bubble", async () => {
    const row = String.raw`$\partial $ $\frac{\partial}{\partial x}$ $\nabla $ $\vec{2}$ $\cdot $ $\infty $`;
    const { getByTestId, getByText } = await render(<MathDraftPreview input={row} sent showCaret={false} />);
    expect(getByTestId("math-draft-preview")).toBeOnTheScreen();
    expect(getByText("∇")).toBeOnTheScreen();
  });

  it("gives a sent bubble no caret targets, which wrapped to an empty line", async () => {
    const sent = await render(<MathDraftPreview input="$x y 7$" sent showCaret={false} />);
    expect(sent.queryByTestId("math-slot-before")).toBeNull();
    expect(sent.queryByTestId("math-slot-after")).toBeNull();
    const composer = await render(<MathDraftPreview input="$x y 7$" caret={2} />);
    expect(composer.getByTestId("math-slot-after")).toBeOnTheScreen();
  });

  it("shrinks every script, a definite integral's limits included", async () => {
    const { getByText } = await render(
      <MathDraftPreview input={String.raw`$\int_{0}^{1}$`} showCaret={false} />,
    );
    expect(getByText("0")).toHaveStyle({ fontSize: 11 });
    expect(getByText("1")).toHaveStyle({ fontSize: 11 });
  });

  it("keeps words outside the dollars as upright text", async () => {
    const { getByText } = await render(<MathDraftPreview input="solve $x$" showCaret={false} />);
    expect(getByText(/solve/)).not.toHaveStyle({ fontFamily: "KaTeX_MathItalic" });
  });

  it("uses readable root degree text while preserving the full-size radicand", async () => {
    const { getByText, getByTestId } = await render(
      <MathDraftPreview input={String.raw`$\sqrt[6]{9}$`} showCaret={false} />,
    );
    expect(getByTestId("math-slot-nroot-index")).toBeOnTheScreen();
    expect(getByText("6")).toHaveStyle({ fontSize: 12, lineHeight: 15 });
    expect(getByText("9")).toHaveStyle({ fontSize: 16, lineHeight: 20 });
  });

  it("paints a dropped command slash as a fraction", async () => {
    const { getByTestId, queryByText } = await render(
      <MathDraftPreview input="$frac{d^{2}}{dx^{2}}$" showCaret={false} />,
    );
    expect(getByTestId("math-frac")).toBeOnTheScreen();
    expect(queryByText(/frac\{/)).toBeNull();
  });

  it("highlights only an empty slot", async () => {
    const empty = await render(<MathDraftPreview input={String.raw`$\frac{}{}$`} caret={7} />);
    expect(empty.getByTestId("math-slot-num")).toHaveStyle({
      backgroundColor: lightTheme.primaryLight,
    });
    expect(empty.getByTestId("math-slot-den")).toHaveStyle({
      backgroundColor: lightTheme.primaryLight,
    });
    expect(empty.getByTestId("math-slot-den-placeholder")).not.toHaveStyle({
      borderBottomWidth: 1,
    });

    const symbol = await render(<MathDraftPreview input="$y$" caret={2} />);
    expect(symbol.getByTestId("math-slot-text")).not.toHaveStyle({
      backgroundColor: lightTheme.primaryLight,
    });

    const filled = await render(<MathDraftPreview input={String.raw`$\frac{8}{}$`} caret={8} />);
    expect(filled.getByTestId("math-slot-num")).not.toHaveStyle({
      backgroundColor: lightTheme.primaryLight,
    });
    expect(filled.getByTestId("math-slot-den")).toHaveStyle({
      backgroundColor: lightTheme.primaryLight,
    });
  });

  it("draws a definite integral with a lower limit and an upper limit", async () => {
    const { getByTestId } = await render(
      <MathDraftPreview input={String.raw`$\int_{}^{}$`} showCaret={false} />,
    );
    expect(getByTestId("math-integral-sign")).toHaveStyle({ fontSize: 32, lineHeight: 36 });
    expect(getByTestId("math-integral-limits")).toHaveStyle({ marginLeft: 4 });
    expect(getByTestId("math-slot-sub")).toHaveStyle({
      backgroundColor: lightTheme.primaryLight,
    });
    expect(getByTestId("math-slot-sup")).toHaveStyle({
      backgroundColor: lightTheme.primaryLight,
    });
  });
});

describe("MathDraftPreview: one piece per draft node", () => {
  const press = (locationX: number) => ({ nativeEvent: { locationX } });

  it("draws plain text in the math face and a command run as math", async () => {
    const plain = await render(<MathDraftPreview input="$x+1$" showCaret={false} />);
    expect(plain.getByText("x+1")).toHaveStyle({ fontSize: 16 });
    const command = await render(<MathDraftPreview input={String.raw`$\pi r$`} showCaret={false} />);
    expect(command.queryByText(String.raw`\pi r`)).toBeNull();
    expect(command.getByTestId("math-slot-text")).toBeOnTheScreen();
  });

  it("moves the caret to a text run's near or far end by where it is tapped", async () => {
    const onMoveCaret = jest.fn();
    const { getByTestId } = await render(
      <MathDraftPreview input="$ab$" showCaret={false} onMoveCaret={onMoveCaret} />,
    );
    await fireEvent.press(getByTestId("math-slot-text"), press(2));
    await fireEvent.press(getByTestId("math-slot-text"), press(30));
    expect(onMoveCaret.mock.calls).toEqual([[1], [3]]);
  });

  it("shows a text run's caret at its start or its end", async () => {
    const inside = await render(<MathDraftPreview input={String.raw`$x+\frac{1}{2}$`} caret={7} />);
    expect(inside.queryByTestId("math-slot-text-caret")).toBeNull();
    expect(inside.queryByTestId("math-slot-text-caret-start")).toBeNull();
    const end = await render(<MathDraftPreview input={String.raw`$x+\frac{1}{2}$`} caret={3} />);
    expect(end.getByTestId("math-slot-text-caret")).toBeOnTheScreen();
    const after = await render(<MathDraftPreview input={String.raw`$\frac{1}{2}+x$`} caret={12} />);
    expect(after.getByTestId("math-slot-text-caret-start")).toBeOnTheScreen();
  });

  it("stacks a fraction's numerator over its denominator", async () => {
    const { getByTestId } = await render(
      <MathDraftPreview input={String.raw`$\frac{a}{b}$`} showCaret={false} />,
    );
    const frac = getByTestId("math-frac");
    const ids = frac.children.map((child) => (typeof child === "string" ? child : child.props.testID));
    expect(ids).toEqual(["math-slot-num", "math-vinculum", "math-slot-den"]);
  });

  it("draws a square root without an index and an nth root with one", async () => {
    const square = await render(<MathDraftPreview input={String.raw`$\sqrt{2}$`} showCaret={false} />);
    expect(square.getByTestId("math-slot-sqrt")).toBeOnTheScreen();
    expect(square.queryByTestId("math-slot-nroot-index")).toBeNull();
    const cube = await render(<MathDraftPreview input={String.raw`$\sqrt[3]{8}$`} showCaret={false} />);
    expect(cube.getByTestId("math-slot-nroot-index")).toBeOnTheScreen();
    expect(cube.getByTestId("math-slot-sqrt")).toBeOnTheScreen();
  });

  it("raises a superscript and drops a subscript beside their base", async () => {
    const { getByTestId } = await render(
      <MathDraftPreview input={String.raw`$x^{2}y_{1}$`} showCaret={false} />,
    );
    expect(getByTestId("math-sup")).toBeOnTheScreen();
    expect(getByTestId("math-slot-sup")).toBeOnTheScreen();
    expect(getByTestId("math-sub")).toBeOnTheScreen();
    expect(getByTestId("math-slot-sub")).toBeOnTheScreen();
  });

  it("puts a sum's limits over and under it", async () => {
    const { getByTestId, queryByTestId } = await render(
      <MathDraftPreview input={String.raw`$\sum_{i=1}^{n}$`} showCaret={false} />,
    );
    expect(getByTestId("math-slot-sup")).toBeOnTheScreen();
    expect(getByTestId("math-slot-sub")).toBeOnTheScreen();
    expect(queryByTestId("math-integral")).toBeNull();
  });

  it("draws a braced group, absolute value bars, a binomial and a vector arrow", async () => {
    const brace = await render(<MathDraftPreview input="${x}$" showCaret={false} />);
    expect(brace.getByTestId("math-brace")).toBeOnTheScreen();
    expect(brace.getByTestId("math-slot-brace")).toBeOnTheScreen();
    const abs = await render(<MathDraftPreview input="$|x|$" showCaret={false} />);
    expect(abs.getByTestId("math-abs")).toBeOnTheScreen();
    expect(abs.getAllByText("|")).toHaveLength(2);
    const binom = await render(<MathDraftPreview input={String.raw`$\binom{5}{2}$`} showCaret={false} />);
    expect(binom.getByTestId("math-binom")).toBeOnTheScreen();
    expect(binom.getByText("C(")).toBeOnTheScreen();
    expect(binom.getByText(",")).toBeOnTheScreen();
    expect(binom.getByText(")")).toBeOnTheScreen();
    expect(binom.getByTestId("math-slot-binom-n")).toBeOnTheScreen();
    expect(binom.getByTestId("math-slot-binom-k")).toBeOnTheScreen();
    const vec = await render(<MathDraftPreview input={String.raw`$\vec{v}$`} showCaret={false} />);
    expect(vec.getByTestId("math-vec")).toBeOnTheScreen();
    expect(vec.getByText("→")).toBeOnTheScreen();
    expect(vec.getByTestId("math-slot-vec")).toBeOnTheScreen();
  });

  it("keeps a function's name with its parentheses and a set's braces", async () => {
    const call = await render(<MathDraftPreview input={String.raw`$\sin(x)$`} showCaret={false} />);
    expect(call.getByTestId("math-group")).toBeOnTheScreen();
    expect(call.getByText("sin(")).toBeOnTheScreen();
    expect(call.getByText(")")).toBeOnTheScreen();
    const set = await render(<MathDraftPreview input={String.raw`$\{1,2\}$`} showCaret={false} />);
    expect(set.getByTestId("math-group")).toBeOnTheScreen();
    expect(set.getByText("{")).toBeOnTheScreen();
    expect(set.getByText("}")).toBeOnTheScreen();
  });

  it("nests a structured slot's pieces inside it", async () => {
    const { getByTestId } = await render(
      <MathDraftPreview input={String.raw`$\sqrt{\frac{1}{x^{2}}}$`} showCaret={false} />,
    );
    const radicand = getByTestId("math-slot-sqrt");
    expect(within(radicand).getByTestId("math-frac")).toBeOnTheScreen();
    expect(within(radicand).getByTestId("math-sup")).toBeOnTheScreen();
  });

  it("moves the caret into a slot's front or back half, or into an empty slot", async () => {
    const onMoveCaret = jest.fn();
    const { getByTestId } = await render(
      <MathDraftPreview input={String.raw`$\frac{12}{}$`} showCaret={false} onMoveCaret={onMoveCaret} />,
    );
    const num = getByTestId("math-slot-num");
    await fireEvent.press(num, press(5));
    await fireEvent(num, "layout", { nativeEvent: { layout: { width: 40, height: 20 } } });
    await fireEvent.press(num, press(5));
    await fireEvent.press(num, press(30));
    await fireEvent.press(getByTestId("math-slot-den"), press(0));
    expect(onMoveCaret.mock.calls).toEqual([[9], [7], [9], [11]]);
  });
});
