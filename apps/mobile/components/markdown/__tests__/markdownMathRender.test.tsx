import { render } from "@testing-library/react-native";

import { MarkdownContent } from "@/components/MarkdownContent";
import { formatAssistantMathExpr } from "@/lib/math/formatInput";

jest.mock("@/components/LinkPreviewCard", () => ({
  LinkPreviewCard: "LinkPreviewCard",
}));
jest.mock("expo-web-browser", () => ({ openBrowserAsync: jest.fn() }));
jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/",
  writeAsStringAsync: jest.fn(),
  EncodingType: { UTF8: "utf8" },
}));
jest.mock("@/components/WebPreviewCodeBlock", () => ({
  WebPreviewCodeBlock: "WebPreviewCodeBlock",
}));
jest.mock("@/components/rich/CircularClockBlock", () => ({
  CircularClockBlock: "CircularClockBlock",
}));
jest.mock("@/components/rich/AnswerBlock", () => ({
  AnswerBlock: "AnswerBlock",
}));
// Display math renders via MathJax-SVG now; this suite asserts markdown
// splitting/punctuation, so stand in the native MathText fallback.
jest.mock("@/components/rich/MathSvgView", () => {
  const React = jest.requireActual("react");
  const { MathText } = jest.requireActual("@/components/rich/MathText");
  return {
    MathSvgView: ({ latex }: { latex: string }) => React.createElement(MathText, { latex }),
  };
});
jest.mock("@/components/CodeBlock", () => {
  const { Text: RNText } = jest.requireActual("react-native");
  return {
    CodeBlock: ({ code, lang }: { code: string; lang: string }) => (
      <RNText>{`${lang}:${code}`}</RNText>
    ),
  };
});

describe("MarkdownContent math rendering", () => {
  it("keeps the exact B12 explanation chain inside a scrollable list viewport", async () => {
    const { getAllByTestId, getByText, queryByText } = await render(
      <MarkdownContent content={"The surface area of a square pyramid is found by adding the area of the base to the area of the four triangular faces. Here's the step-by-step process for a square pyramid with a base side of 6 and a height of 4:\n\n1. **Calculate the area of the base**  \n   The base is a square, so its area is side length squared:  \n   $ \\text{Base Area} = 6^2 = 36 $.  \n\n2. **Calculate the slant height**  \n   The slant height is the height of the triangular faces. Use the Pythagorean theorem:  \n   $ \\text{Slant Height} = \\sqrt{ \\left( \\frac{6}{2} \\right)^2 + 4^2 } = \\sqrt{3^2 + 4^2} = \\sqrt{9 + 16} = \\sqrt{25} = 5 $.  \n\n3. **Calculate the area of the triangular faces**  \n   Each triangle has an area of $\\frac{1}{2} \\times \\text{base} \\times \\text{slant height}$:  \n   $ \\text{Triangle Area} = \\frac{1}{2} \\times 6 \\times 5 = 15 $.  \n   Since there are four triangles:  \n   $ \\text{Total Triangle Area} = 4 \\times 15 = 60 $.  \n\n4. **Add the base and triangular areas**  \n   $ \\text{Surface Area} = \\text{Base Area} + \\text{Total Triangle Area} = 36 + 60 = 96 $.  \n\nThe total surface area is **96**."} />,
    );
    const chain = getAllByTestId("math-text-scroll").find(
      (node) => node.props.accessibilityLabel.includes("Slant Height"),
    )!;
    expect(chain).toBeDefined();
    expect(chain).toHaveStyle({ maxWidth: "100%", flexShrink: 1 });
    expect(chain.props.horizontal).toBe(true);
    // The wide radical stays one formula. Each later simplification is its own row.
    expect(chain.props.accessibilityLabel).toMatch(/Slant Height/);
    expect(chain.props.accessibilityLabel).not.toMatch(/\\sqrt|\\frac|\\text/);
    expect(getByText(/Use the Pythagorean theorem/)).toBeOnTheScreen();
    expect(getByText(/= 5\./)).toBeOnTheScreen();
    expect(getByText(/Since there are four triangles/)).toBeOnTheScreen();
    expect(queryByText(/\\sqrt|\\frac|\\text/)).toBeNull();
  });

  it("renders the exact H22 explanation fractions without invented pi parentheses", async () => {
    const { getByText, getAllByText, getAllByTestId, getByLabelText, queryByText } = await render(
      <MarkdownContent content={String.raw`- Convert angle: $90^\circ = \frac{\pi}{2}$ radians
- Calculation: $4 \times \frac{\pi}{2} = 2\pi \approx 6.28$`} />,
    );
    expect(getByLabelText("Convert angle: 90° = π/2 radians")).toBeOnTheScreen();
    expect(getByText("radians")).toBeOnTheScreen();
    expect(getByText(/= 2π/)).toBeOnTheScreen();
    expect(getByText(/≈ 6.28/)).toBeOnTheScreen();
    // The approximation repeats the fraction, so the angle's π is joined by both rows.
    expect(getAllByText("π").length).toBeGreaterThanOrEqual(3);
    expect(getAllByTestId("math-frac")).toHaveLength(3);
    expect(queryByText(/\(π\)|\\frac|\\pi/)).toBeNull();
  });

  it("renders the exact S04 mean line without stray dollar delimiters", async () => {
    const { getByText, getByLabelText, queryByText, getByTestId } = await render(
      <MarkdownContent content={String.raw`- Mean (\(\mu\)) = \( \frac{1+2+3}{3} = 2 \),`} />,
    );
    expect(getByLabelText(/Mean \(μ\) =/)).toBeOnTheScreen();
    expect(getByText("1+2+3")).toBeOnTheScreen();
    expect(getByText("= 2,")).toBeOnTheScreen();
    expect(getByTestId("math-frac")).toBeOnTheScreen();
    expect(queryByText(/\$/)).toBeNull();
  });

  it("does not flash an unfinished inline fraction as raw LaTeX", async () => {
    const { queryByText, getByText } = await render(
      <MarkdownContent content={String.raw`Result: $\frac{1}`} streaming />,
    );
    expect(getByText(/Result:/)).toBeOnTheScreen();
    expect(queryByText(/\\frac|\$|frac/)).toBeNull();
  });

  it("gives a heavy inline integral full width outside a Text parent", async () => {
    const { getByTestId } = await render(
      <MarkdownContent content={String.raw`Evaluate $\int_0^1 x^2\,dx$.`} />,
    );
    expect(getByTestId("md-math-inline-wrap")).toBeOnTheScreen();
    expect(getByTestId("md-heavy-math-run")).toHaveStyle({ width: "100%" });
  });

  it("keeps prose and punctuation together beside a heavy limit", async () => {
    const { getByTestId, getByText, queryByText } = await render(
      <MarkdownContent content={String.raw`For $A \subseteq B$, use $\lim_{x\to0} x=0$.`} />,
    );
    expect(getByTestId("md-heavy-math-run")).toHaveStyle({ width: "100%" });
    // The comma shares one Text with its formula, so a line never starts with it.
    expect(getByText(/⊆.*B,$/)).toBeOnTheScreen();
    expect(queryByText(/^\.$/)).toBeNull();
  });

  it.each([",", ";"])("keeps leading %s with a heavy formula while retaining the following prose", async (punctuation) => {
    const { getByText, getByLabelText, queryByText } = await render(
      <MarkdownContent content={String.raw`Evaluate $\int_0^1 x\,dx$${punctuation} then compare.`} />,
    );
    expect(getByText(`x dx${punctuation}`)).toBeOnTheScreen();
    expect(getByLabelText(`Evaluate ∫_0^1 x dx${punctuation} then compare.`)).toBeOnTheScreen();
    expect(queryByText(/^[,;]\s*then compare\./)).toBeNull();
  });

  it("keeps the exact H11 inline prose together and punctuation attached to its fraction", async () => {
    const { getByText, getByLabelText, queryByText, getByTestId, getAllByTestId } = await render(
      <MarkdownContent content={String.raw`Since $3^2 + 4^2 = 5^2$, it's a right triangle with legs 3 and 4, so area $= \tfrac{1}{2}(3)(4) = 6$.`} />,
    );
    expect(getByText(/Since/)).toBeOnTheScreen();
    expect(getByLabelText(/, it’s a right triangle with legs 3 and 4, so area =/)).toBeOnTheScreen();
    expect(getAllByTestId("math-script").length).toBeGreaterThanOrEqual(3);
    expect(getByText("(3)(4) = 6.")).toBeOnTheScreen();
    expect(queryByText(/^, it[’']s a right triangle/)).toBeNull();
    expect(queryByText(/^\.$/)).toBeNull();
    expect(getAllByTestId("md-math-inline-wrap").length).toBeGreaterThan(0);
    expect(getByTestId("math-frac")).toBeOnTheScreen();
  });

  it("attaches a root's comma while retaining following prose and simple math", async () => {
    const { getByLabelText, queryByText, getByTestId, getAllByTestId } = await render(
      <MarkdownContent content={String.raw`Use $\sqrt{2}$, then compare $x^2$ with 4.`} />,
    );
    expect(getByLabelText(/^Use .+, then compare x\^2 with 4\.$/)).toBeOnTheScreen();
    expect(getByTestId("math-script")).toHaveTextContent("2");
    expect(queryByText(/^, then compare/)).toBeNull();
    expect(getByTestId("md-math-inline-wrap")).toBeOnTheScreen();
    expect(getAllByTestId("math-text-tall").length).toBeGreaterThanOrEqual(2);
  });

  it("typesets the exact cube-root callout note without raw LaTeX", async () => {
    const { getByTestId, queryByText } = await render(
      <MarkdownContent content={String.raw`> [!NOTE]
> The expression doesn’t simplify to a whole number or a simpler radical, so $\sqrt[3]{3}$ is the exact form.`} />,
    );
    expect(getByTestId("rich-math-body")).toBeOnTheScreen();
    expect(queryByText(/\\sqrt|\$\\/)).toBeNull();
  });

  it("typesets math on every callout line and preserves source examples in code", async () => {
    const { getAllByTestId, getByText, queryByText } = await render(
      <MarkdownContent content={'```callout-note\nExact $x^2$\nUse $\\frac{1}{2}$; code: `x_1` costs $5 and $10.\n```'} />,
    );
    // The title is the kind; both lines, math included, are the body.
    expect(getAllByTestId("rich-math-body")).toHaveLength(1);
    expect(getByText("Exact")).toBeOnTheScreen();
    expect(getAllByTestId("math-script").length).toBeGreaterThanOrEqual(1);
    expect(getByText("x_1")).toBeOnTheScreen();
    expect(getByText("$5")).toBeOnTheScreen();
    expect(getByText("$10.")).toBeOnTheScreen();
    expect(queryByText(/\\frac/)).toBeNull();
  });

  it("keeps explicit LaTeX source code literal inside a callout", async () => {
    const { getByText } = await render(
      <MarkdownContent content={'```callout-note\nWrite `$\\frac{1}{2}$` to display $x^2$.\n```'} />,
    );
    expect(getByText('$\\frac{1}{2}$')).toBeOnTheScreen();
  });

  it("typesets inline math in a numbered step, not raw \\frac", async () => {
    const { getByTestId, queryByText } = await render(
      <MarkdownContent content={"1. So $m = \\frac{1}{2}$."} />,
    );
    expect(getByTestId("math-frac")).toBeOnTheScreen();
    expect(getByTestId("md-math-inline-wrap")).toBeOnTheScreen();
    expect(queryByText(/\\frac/)).toBeNull();
  });

  it("typesets inline math inside a list item", async () => {
    const { getByTestId, getByText } = await render(
      <MarkdownContent content="- Let $x^2$ be the square." />,
    );
    expect(getByTestId("math-script")).toHaveTextContent("2");
    expect(getByText(/square/)).toBeOnTheScreen();
  });

  it("keeps a bold math label and its value on one list line", async () => {
    const { queryByText } = await render(
      <MarkdownContent content={"- **Slope ($m$):** 3, meaning y increases by 3."} />,
    );
    expect(queryByText(/^:$/)).toBeNull();
    expect(queryByText(")")).toBeNull();
    expect(queryByText("m")).toBeOnTheScreen();
  });

  it("BUG FIX regression: inline split-± fractions keep numerators visible", async () => {
    // Live: "Now we split it for the ±" + $x = \frac{5+1}{2}$ painted the
    // stacked frac over the prose (iOS View-in-Text 0×0) so the numbers
    // above the vinculum could not be read.
    const { getAllByTestId, getByText, queryByText } = await render(
      <MarkdownContent
        content={
          "Now, we split it for the ±:\n\n" +
          "* **Solution 1:** $x = \\frac{5+1}{2} = \\frac{6}{2} = 3$\n" +
          "* **Solution 2:** $x = \\frac{5-1}{2} = \\frac{4}{2} = 2$"
        }
      />,
    );
    expect(getAllByTestId("md-math-inline-wrap").length).toBeGreaterThan(0);
    expect(getAllByTestId("math-frac").length).toBeGreaterThanOrEqual(4);
    expect(getByText("5+1")).toBeOnTheScreen();
    expect(getByText("5−1")).toBeOnTheScreen();
    expect(queryByText(/\\frac/)).toBeNull();
  });

  it("BUG FIX regression: bare-ASCII quadratic-formula steps stack a real fraction (not literal '/'), given the assistant mathFormat", async () => {
    // Live bug: Recall answered "3x^2 - 11x + 6 = 0" with steps written as
    // plain ASCII division ("(11 ± 7) / 6", "√(49)") because the model
    // never wrapped them in \frac{}/\sqrt{} — MessageBubble now passes
    // `formatAssistantMathExpr` as `mathFormat` so normalizeImplicitMath's
    // bare-equation wrap also converts the slash/radical, not just ±→\pm.
    const { getAllByTestId, queryByText } = await render(
      <MarkdownContent
        content={
          "Steps\n\n" +
          "4. Split the two roots:\n" +
          "- x = (11 + 7) / 6 = 18 / 6 = 3\n" +
          "- x = (11 - 7) / 6 = 4 / 6 = 2/3"
        }
        mathFormat={formatAssistantMathExpr}
      />,
    );
    expect(getAllByTestId("math-frac").length).toBeGreaterThanOrEqual(4);
    // No leftover literal division text once every fraction is stacked.
    expect(queryByText(/\(11 \+ 7\) \/ 6/)).toBeNull();
    expect(queryByText(/\(11 - 7\) \/ 6/)).toBeNull();
    expect(queryByText(/\\frac/)).toBeNull();
  });

  it("treats a single newline in a list item as a space, not a stacked line", async () => {
    const { queryByText } = await render(
      <MarkdownContent
        content={"- It's a\n**linear equation**\nin slope-intercept form."}
      />,
    );
    expect(queryByText(/^It's a$/)).toBeNull();
    expect(queryByText(/linear equation/)).toBeOnTheScreen();
  });

  it("BUG FIX regression: second quadratic root stays on the solve bullet", async () => {
    const { getByText, queryByText } = await render(
      <MarkdownContent
        content={[
          "4. **Solve for x**:",
          "   - $2x - 1 = 0 \\rightarrow x = 1/2$",
          "   -",
          "",
          "```math",
          "x - 3 = 0 \\rightarrow x = 3",
          "```",
        ].join("\n")}
      />,
    );
    expect(queryByText(/\\rightarrow/)).toBeNull();
    expect(getByText(/x = 3/)).toBeOnTheScreen();
  });

  it("BUG FIX regression: For x = 3: check is not packed onto the formula line", async () => {
    const { getAllByText, queryByText } = await render(
      <MarkdownContent
        content={
          "You can check:\n" +
          "- For $x = 3$: $2(3)^2 - 7(3) + 3 = 18 - 21 + 3 = 0$ ✓\n" +
          "- For $x$ = $\\frac{1}{2}$\n" +
          "$2(\\frac{1}{2})^2 - 7(\\frac{1}{2}) + 3 = \\frac{1}{2} - \\frac{7}{2} + 3 = -3 + 3 = 0$\n" +
          "✓"
        }
      />,
    );
    expect(getAllByText(/For/).length).toBeGreaterThanOrEqual(2);
    expect(queryByText(/18 - 21 \+ 3 = 0/)).toBeNull();
    expect(queryByText(/1\/2 - 7\/2 \+ 3 = 0/)).toBeNull();
    expect(getAllByText("= 0").length).toBeGreaterThanOrEqual(2);
    expect(getAllByText("= 18 − 21 + 3").length).toBeGreaterThanOrEqual(1);
  });

  it("keeps a lesson formula off the step label line", async () => {
    const { getByText, queryByText } = await render(
      <MarkdownContent
        content={"**2. Simplify**\n\n$3 x = 3$"}
      />,
    );
    expect(getByText("2")).toBeOnTheScreen();
    expect(getByText("Simplify")).toBeOnTheScreen();
    expect(getByText("3x = 3")).toBeOnTheScreen();
    expect(queryByText(/Simplify 3/)).toBeNull();
  });

  it("renders an escaped pay formula as dollars, not backslashes or command names", async () => {
    const content = [
      "Weekly Pay:",
      "",
      String.raw`$\$43 \text{ per hour} \times 40 \text{ hours} = \mathbf{\$1,720} \text{ per week}$`,
      "",
      String.raw`Example: 35 hrs/week → 43 × 35 = \$1,505$`,
      "",
      String.raw`$1,720 \times 2 = \mathbf{\$3,440}$ per paycheck`,
    ].join("\n");
    const { getByText, queryByText } = await render(<MarkdownContent content={content} />);
    expect(getByText("$43 per hour × 40 hours = $1,720 per week")).toBeOnTheScreen();
    expect(getByText(/43 × 35 = \$1,505/)).toBeOnTheScreen();
    expect(getByText("1,720 × 2 = $3,440")).toBeOnTheScreen();
    expect(queryByText(/\\text|\\times|mathbf|[\uE000-\uE00F]/)).toBeNull();
  });

  it("keeps the dollars in a display-math pay formula", async () => {
    const { getByText, queryByText } = await render(
      <MarkdownContent
        content={String.raw`#### Weekly Pay:
$$
\$43 \text{/hour} \times 40 \text{ hours} = \mathbf{\$1,720\ per\ week}
$$`}
      />,
    );
    expect(getByText("$43 /hour × 40 hours = $1,720 per week")).toBeOnTheScreen();
    expect(queryByText(/\\text|mathbf|[\uE000-\uE00F]/)).toBeNull();
  });

  it("renders the same pay formula while the reply is still streaming", async () => {
    const content = String.raw`Weekly Pay:

$\$43 \text{ per hour} \times 40 \text{ hours} = \mathbf{\$1,720} \text{ per week}$
`;
    const { getByText, queryByText } = await render(
      <MarkdownContent content={content} streaming />,
    );
    expect(getByText("$43 per hour × 40 hours = $1,720 per week")).toBeOnTheScreen();
    expect(queryByText(/\\text|\\times|mathbf|[\uE000-\uE00F]/)).toBeNull();
  });

  it("unwraps a details fence so the body is markdown, not a collapsed card", async () => {
    const { getByText, getByTestId, queryByText, queryByRole } = await render(
      <MarkdownContent
        content={"```details\nClick for answer\n$x^2$\n- first step\n```"}
      />,
    );
    expect(getByText("Click for answer")).toBeOnTheScreen();
    expect(getByText("first step")).toBeOnTheScreen();
    expect(queryByText(/\$x/)).toBeNull();
    expect(getByTestId("math-text-tall")).toBeOnTheScreen();
    expect(getByTestId("math-script")).toHaveTextContent("2");
    expect(queryByRole("button", { name: "Click for answer" })).toBeNull();
  });
});
