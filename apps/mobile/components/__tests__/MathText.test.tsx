import { Dimensions, StyleSheet } from "react-native";
import { render, screen } from "@testing-library/react-native";

import { MathText } from "@/components/rich/MathText";
import { FRAC_SIZE_RATIO, layoutMath, SCRIPT_RATIO } from "@/lib/math/layout";
import { findLayouts, layoutProblems } from "./layoutChecks";
import { fixImplicitExponents } from "@/lib/math/normalizeImplicit";
import { parseSimpleLatex } from "@/lib/math/text";
import { lightTheme } from "@/lib/theme";

function laidOut(latex: string, fontSize = 16) {
  const layout = layoutMath(parseSimpleLatex(fixImplicitExponents(latex.trim())), fontSize);
  return { layout, problems: layoutProblems(layout, fontSize) };
}

describe("MathText", () => {
  beforeEach(() => {
    jest.spyOn(Dimensions, "get").mockReturnValue({
      width: 390, height: 844, scale: 3, fontScale: 1,
    });
  });

  afterEach(() => jest.restoreAllMocks());
  it("renders plain text with no math markup unchanged", async () => {
    const { getByText } = await render(<MathText latex="x + 1" />);
    expect(getByText("x + 1")).toBeOnTheScreen();
  });

  it("uses the dedicated math face and keeps lowercase variables unmistakable", async () => {
    const { getByText, getByTestId } = await render(<MathText latex="x = 3" />);
    expect(getByText("x = 3")).toHaveStyle({ fontFamily: "KaTeX_Main" });
    expect(getByTestId("math-variable")).toHaveTextContent("x");
    expect(getByTestId("math-variable")).toHaveStyle({
      fontFamily: "KaTeX_MathItalic",
    });
  });

  it("keeps named functions upright while variables remain math italic", async () => {
    const { getByText, getAllByTestId } = await render(
      <MathText latex={String.raw`\sin{x} = y`} />,
    );
    expect(getByText("sin(x) = y")).toBeOnTheScreen();
    expect(getAllByTestId("math-variable").map((node) => node.props.children)).toEqual([
      "x",
      "y",
    ]);
  });

  it.each([
    [String.raw`\tau = F d \sin\theta`, ["τ", "F", "d", "θ"]],
    [String.raw`N = m g \cos\theta`, ["N", "m", "g", "θ"]],
    [String.raw`F_2\sin\phi`, ["F", "φ"]],
    // After variables with no space, as the torque law is written.
    [String.raw`\tau = Fd\sin(\theta)`, ["τ", "Fd", "θ"]],
  ])("keeps a function upright beside its variables: %s", async (latex, variables) => {
    // Read as one run, "sinθ" or "Fdsin" was not a function name and went italic.
    const { getAllByTestId } = await render(<MathText latex={latex} />);
    const italic = getAllByTestId("math-variable").map((node) => node.props.children);
    expect(italic).toEqual(variables);
  });

  it.each([
    [String.raw`\tau = Fd\sin(\theta)`, "τ = Fd sin(θ)"],
    [String.raw`\tau = F\sin\theta`, "τ = F sin θ"],
    [String.raw`\sin x\cos x`, "sin x cos x"],
    [String.raw`3\ln 2`, "3 ln 2"],
    [String.raw`2 + \sin(x)`, "2 + sin(x)"],
    [String.raw`(\sin x)`, "(sin x)"],
  ])("spaces a function name from a symbol, not from an operator: %s", async (latex, text) => {
    // Upright but unspaced, the torque law still read "Fdsin(θ)".
    const { getByText } = await render(<MathText latex={latex} />);
    expect(getByText(text)).toBeOnTheScreen();
  });

  it("draws a squared unit's ² as written, not as a caret", async () => {
    // An upright run is drawn as typed: converted to a script there, "m/s²" showed "m/s^2".
    const { getByTestId, queryByText } = await render(
      <MathText latex={String.raw`g = 9.81\,\mathrm{m/s²}`} />,
    );
    expect(getByTestId("math-upright-run")).toHaveTextContent("m/s²");
    expect(queryByText(/\^/)).toBeNull();
  });

  it("does not paint private-use markers when a text subscript has no braces", async () => {
    const rendered = await render(<MathText latex={String.raw`t_\text{flight}`} />);
    expect(rendered.getByTestId("math-upright-run")).toHaveTextContent("flight");
    expect(rendered.getAllByTestId("math-variable").map((node) => node.props.children)).toEqual(["t"]);
    expect(JSON.stringify(rendered.toJSON())).not.toMatch(/[\uE006\uE007]/);
  });

  it("keeps physics units in text and roman commands upright", async () => {
    const { getAllByTestId, getByTestId } = await render(
      <MathText latex={String.raw`x = 25\,\mathrm{m/s}`} />,
    );
    expect(getAllByTestId("math-variable").map((node) => node.props.children)).toEqual([
      "x",
    ]);
    expect(getByTestId("math-upright-run")).toHaveTextContent("m/s");
    expect(getByTestId("math-upright-run")).toHaveStyle({
      fontFamily: "KaTeX_Main",
    });
  });

  it("does not paint private-use marks or command names for other bare scripts", async () => {
    const italic = await render(<MathText latex={String.raw`t_\textit{rel}`} />);
    expect(italic.getByTestId("math-upright-run")).toHaveTextContent("rel");
    expect(JSON.stringify(italic.toJSON())).not.toMatch(/[\uE000-\uE00F]/);
    expect(italic.queryByText(/textit/)).toBeNull();

    const bold = await render(<MathText latex={String.raw`F_\mathbf{g}`} />);
    expect(bold.getByTestId("math-script")).toHaveTextContent("g");
    expect(JSON.stringify(bold.toJSON())).not.toMatch(/[\uE000-\uE00F]/);
    expect(bold.queryByText(/mathbf/)).toBeNull();

    const escaped = await render(<MathText latex={String.raw`x^\{2\}`} />);
    expect(escaped.getByTestId("math-script")).toHaveTextContent("2");
    expect(JSON.stringify(escaped.toJSON())).not.toMatch(/[\uE000-\uE00F]/);

    const spaced = await render(<MathText latex="x^ {2}" />);
    expect(spaced.getByTestId("math-script")).toHaveTextContent("2");

    const hat = await render(<MathText latex={String.raw`\hat\text{v}`} />);
    expect(hat.getByTestId("math-accent")).toBeOnTheScreen();
    expect(hat.getByTestId("math-upright-run")).toHaveTextContent("v");
    expect(hat.queryByText(/hat/)).toBeNull();
    expect(JSON.stringify(hat.toJSON())).not.toMatch(/[\uE000-\uE00F]/);
  });

  it("keeps upright words in subscripts instead of leaking markers or italics", async () => {
    const rendered = await render(<MathText latex={String.raw`t_{\mathrm{flight}}`} />);
    expect(rendered.getByTestId("math-upright-run")).toHaveTextContent("flight");
    expect(rendered.getByTestId("math-upright-run")).toHaveStyle({ fontFamily: "KaTeX_Main" });
    expect(JSON.stringify(rendered.toJSON())).not.toMatch(/[\uE006\uE007]/);
  });

  it("renders escaped braces inside upright text without leaking native markers", async () => {
    const rendered = await render(
      <MathText latex={String.raw`\text{\{x\}}`} />,
    );
    expect(rendered.getByTestId("math-upright-run")).toHaveTextContent("{x}");
    expect(JSON.stringify(rendered.toJSON())).not.toMatch(/[\uE005-\uE009]/);
  });

  it.each([
    [String.raw`\text{\}}`, "}"],
    [String.raw`\mathrm{\{}`, "{"],
  ])("renders a one-sided escaped brace in an upright group", async (latex, brace) => {
    const rendered = await render(<MathText latex={latex} />);
    expect(rendered.getByTestId("math-upright-run")).toHaveTextContent(brace);
    expect(JSON.stringify(rendered.toJSON())).not.toMatch(/[\uE005-\uE009]/);
  });

  it("raises a superscript in the math face instead of a unicode fallback glyph", async () => {
    const { getByTestId, queryByText } = await render(<MathText latex="x^2" />);
    const { layout, problems } = laidOut("x^2");
    const script = findLayouts(layout, "script")[0];
    expect(problems).toEqual([]);
    expect(getByTestId("math-script")).toHaveTextContent("2");
    expect(getByTestId("math-script")).toHaveStyle({
      fontFamily: "KaTeX_Main",
      fontSize: script.fontSize,
      transform: [{ translateY: -(script.raise ?? 0) }],
    });
    // The exponent only rises when its Text is a child of a View. Nested in
    // another Text, iOS ignores translateY and `x^2` draws as x2.
    expect(getByTestId("math-text-tall")).toHaveStyle({
      height: layout.height,
      paddingTop: layout.padTop,
    });
    expect(queryByText("x²")).toBeNull();
    expect(queryByText("²")).toBeNull();
  });

  it("renders nothing for empty latex", async () => {
    const { toJSON } = await render(<MathText latex="   " />);
    expect(toJSON()).toBeNull();
  });

  it("draws a red slash through a cancelled factor, not a red number", async () => {
    const { getAllByTestId, getAllByText } = await render(
      <MathText latex={String.raw`\frac{\cancel{3} x}{\cancel{3}}`} />,
    );
    expect(getAllByTestId("math-cancel")).toHaveLength(2);
    const threes = getAllByText("3");
    expect(threes).toHaveLength(2);
    for (const three of threes) {
      expect(StyleSheet.flatten(three.props.style).color).toBe(lightTheme.text);
    }
    for (const slash of getAllByTestId("math-cancel-slash")) {
      expect(StyleSheet.flatten(slash.props.style).backgroundColor).toBe(lightTheme.danger);
    }
  });

  it("paints a fraction inside an exponent at the script size", async () => {
    const { getByText } = await render(
      <MathText latex={String.raw`x^{\frac{1}{2}}`} />,
    );
    expect(getByText("1")).toHaveStyle({
      fontSize: 16 * SCRIPT_RATIO * FRAC_SIZE_RATIO,
    });
  });

  it("renders a simple fraction as a stacked vinculum (num / bar / den)", async () => {
    // User-requested: real stacked fraction with a straight horizontal
    // vinculum — not ½, not ¹⁄₂, and never the broken ¹─₂ bar hack.
    const { getByText, getByTestId } = await render(
      <MathText latex={"\\frac{1}{2}"} />,
    );
    expect(getByTestId("math-frac")).toBeOnTheScreen();
    expect(getByTestId("math-vinculum")).toBeOnTheScreen();
    expect(getByText("1")).toBeOnTheScreen();
    expect(getByText("2")).toBeOnTheScreen();
    // Root is a sized View (not Text wrapping a View) so the paragraph Text
    // can treat it as a character. Nested Text>View was 0×0 on iOS and the
    // next sentence painted on top of this one (live: part (b) smudge).
    const { layout, problems } = laidOut("\\frac{1}{2}");
    const frac = findLayouts(layout, "frac")[0];
    expect(problems).toEqual([]);
    expect(getByTestId("math-text-tall")).toHaveStyle({ minWidth: layout.width, height: layout.height });
    expect(getByTestId("math-frac")).toHaveStyle({ width: frac.width, height: frac.height });
    expect(frac.width).toBeGreaterThanOrEqual(frac.contentWidth ?? 0);
    expect(frac.pad ?? 0).toBeLessThanOrEqual(16 * 0.5);
    expect(getByText("1")).toHaveStyle({ fontSize: 14, lineHeight: 18 });
  });

  it("renders conditional-probability mid as a vertical relation, not raw text", async () => {
    const rendered = await render(
      <MathText latex={String.raw`P(D\mid +)`} />,
    );
    expect(JSON.stringify(rendered.toJSON())).toContain("∣");
    expect(rendered.queryByText(/mid/)).toBeNull();
  });

  it("gives a wide serif numerator a longer bar than the same run of digits", async () => {
    const wide = await render(<MathText latex={String.raw`\frac{mmmmmmmmmmmm}{1}`} />);
    const narrow = await render(<MathText latex={String.raw`\frac{111111111111}{1}`} />);
    const wideWidth = StyleSheet.flatten(wide.getByTestId("math-frac").props.style).width as number;
    const narrowWidth = StyleSheet.flatten(narrow.getByTestId("math-frac").props.style).width as number;
    const narrowLayout = findLayouts(laidOut(String.raw`\frac{111111111111}{1}`).layout, "frac")[0];
    expect(narrowWidth).toBe(narrowLayout.width);
    expect(wideWidth).toBeGreaterThan(narrowWidth + 40);
  });

  it("renders letter fractions stacked the same way (m over m)", async () => {
    const { getByTestId, getAllByText } = await render(
      <MathText latex={"\\frac{m}{m}"} />,
    );
    expect(getByTestId("math-frac")).toBeOnTheScreen();
    expect(getByTestId("math-vinculum")).toBeOnTheScreen();
    expect(getAllByText("m")).toHaveLength(2);
  });

  it("renders a complex fraction with the vinculum grouping its complete numerator", async () => {
    const { getByTestId, getByText } = await render(
      <MathText latex={"\\frac{-b + \\sqrt{2}}{2a}"} />,
    );
    expect(getByTestId("math-frac")).toBeOnTheScreen();
    expect(getByTestId("math-vinculum")).toBeOnTheScreen();
    expect(getByTestId("math-sqrt")).toBeOnTheScreen();
    expect(getByText("2")).toBeOnTheScreen();
    expect(getByText("2a")).toBeOnTheScreen();
  });

  it("does not invent parentheses or extra width around a Greek fraction numerator", async () => {
    const { getByText, queryByText, getByTestId } = await render(
      <MathText latex={String.raw`\frac{\pi}{2}`} />,
    );
    expect(getByText("π")).toBeOnTheScreen();
    expect(getByText("2")).toBeOnTheScreen();
    expect(queryByText(/[()]/)).toBeNull();
    const { layout } = laidOut(String.raw`\frac{\pi}{2}`);
    const frac = findLayouts(layout, "frac")[0];
    expect(getByTestId("math-frac")).toHaveStyle({ width: frac.width, height: frac.height });
    expect(getByTestId("math-text-tall")).toHaveStyle({ minWidth: layout.width, height: layout.height });
  });

  it("groups sums and scripts using the fraction bar without adding source characters", async () => {
    const { getByText, queryByText, getByTestId } = await render(
      <MathText latex={String.raw`\frac{x^2+1}{a+b}`} />,
    );
    expect(getByTestId("math-script")).toHaveTextContent("2");
    expect(queryByText("²")).toBeNull();
    expect(getByText("a+b")).toBeOnTheScreen();
    expect(queryByText(/[()]/)).toBeNull();
    expect(getByTestId("math-vinculum")).toBeOnTheScreen();
  });

  it("preserves parentheses explicitly included on either fraction side", async () => {
    const { getByText } = await render(<MathText latex={String.raw`\frac{(a+b)}{(c-d)}`} />);
    expect(getByText("(a+b)")).toBeOnTheScreen();
    expect(getByText("(c−d)")).toBeOnTheScreen();
  });

  it("BUG FIX regression: sqrt inside a fraction keeps one bar over b^2 - 4ac", async () => {
    // Live quadratic formula: flattened combining overlines turned `-` into a
    // fake `=` and sized the vinculum from those extra marks so it ran under
    // the following prose.
    const { getByTestId, getAllByText, getByText, queryByText } = await render(
      <MathText latex={String.raw`x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}`} />,
    );
    expect(getByTestId("math-sqrt")).toBeOnTheScreen();
    expect(getByTestId("math-sqrt-radicand")).toBeOnTheScreen();
    expect(queryByText(/̅/)).toBeNull();
    expect(getAllByText("b")).toHaveLength(2);
    expect(getByText(/4ac/)).toBeOnTheScreen();
    const frac = getByTestId("math-frac");
    const width = StyleSheet.flatten(frac.props.style).width as number;
    expect(width).toBeGreaterThan(40);
    expect(width).toBeLessThan(200);
  });

  it("BUG FIX regression: \\pm immediately followed by a digit does not become a false superscript", async () => {
    // Reported live: a step-by-step solve rendered "x = \pm\sqrt{4}" then
    // simplified to "x = \pm2" (no space) — the implicit-exponent heuristic
    // used to mistake the command's trailing letter for a bare variable and
    // rewrite it to "\pm^2", displaying "±²" ("plus or minus squared")
    // instead of "± 2".
    const { getByText } = await render(<MathText latex={String.raw`x = \pm2`} />);
    expect(getByText("x = ±2")).toBeOnTheScreen();
  });

  it("BUG FIX regression: a fraction inside \\sqrt{} still does not leak raw \\frac text", async () => {
    // Sqrt path flattens to plain text (radical + overline); nested View
    // stacks inside the radicand aren't used — but \\frac must not leak.
    const { queryByText } = await render(
      <MathText latex={String.raw`m = \pm\sqrt{\frac{M}{2}}`} />,
    );
    expect(queryByText(/\\frac/)).toBeNull();
    expect(screen.getByText(/m = ±/)).toBeOnTheScreen();
  });

  it("composes ≠ from the KaTeX not-glyph, which is the face that contains the slash", async () => {
    const neq = await render(<MathText latex={String.raw`a \neq 0`} />);
    expect(neq.getByTestId("math-negated").props.accessibilityLabel).toBe("≠");
    expect(neq.getByTestId("math-negated")).toHaveTextContent(`${"\uE020"}=`);
    expect(neq.queryByText(/≡/)).toBeNull();
    const ne = await render(<MathText latex={String.raw`a \ne 0`} />);
    expect(ne.getByTestId("math-negated").props.accessibilityLabel).toBe("≠");
    expect(ne.queryByText(/\bne\b/)).toBeNull();
  });

  it("does not turn \\cdots into a leftover s", async () => {
    const { getByText, queryByText } = await render(
      <MathText latex={String.raw`n \times (n-1) \times \cdots \times 1`} />,
    );
    expect(getByText(/⋯/)).toBeOnTheScreen();
    expect(queryByText(/·s/)).toBeNull();
    expect(queryByText(/\\cdots/)).toBeNull();
  });

  it("renders a square root with a vinculum, not nth-root brackets", async () => {
    const { getByTestId, queryByText } = await render(
      <MathText latex={String.raw`9\sqrt{9}`} />,
    );
    expect(getByTestId("math-sqrt")).toBeOnTheScreen();
    expect(getByTestId("math-radical-glyph")).toBeOnTheScreen();
    expect(queryByText(/√\[/)).toBeNull();
  });

  it("BUG FIX regression: the radicand is full size under the bar, not a subscript", async () => {
    // Reported live ("the square root is totally broken"): the radicand reused
    // the fraction-sized side renderer (11px) and bottom-aligned against the
    // 16px √, so `\sqrt{8}` read as "√ subscript 8" with the bar floating in
    // the sign's leading.
    const { getByTestId } = await render(<MathText latex={String.raw`\sqrt{8}`} />);
    const { layout, problems } = laidOut(String.raw`\sqrt{8}`);
    const radical = findLayouts(layout, "sqrt")[0];
    expect(problems).toEqual([]);
    expect(getByTestId("math-sqrt")).toHaveStyle({ alignItems: "flex-start" });
    expect(getByTestId("math-sqrt")).toHaveStyle({ width: radical.width, height: radical.height });
    expect(getByTestId("math-text-tall")).toHaveStyle({ minWidth: layout.width, height: layout.height });
    expect(getByTestId("math-sqrt-radicand")).toHaveStyle({
      marginLeft: radical.lead,
      marginTop: radical.bodyTop,
      width: radical.children[0]?.width,
      height: radical.bodyHeight,
    });
    const bar = (radical.barEnd ?? 0) - (radical.barStart ?? 0);
    expect(bar - (radical.bodyWidth ?? 0)).toBeLessThanOrEqual(16 * 0.28);
    expect(screen.getByText("8")).toHaveStyle({ fontSize: 16, lineHeight: 20 });
  });

  it("draws one continuous radical around a stacked x over y fraction", async () => {
    const { getByTestId, getByText } = await render(
      <MathText latex={String.raw`\sqrt{\frac{x}{y}}`} />,
    );
    const { layout, problems } = laidOut(String.raw`\sqrt{\frac{x}{y}}`);
    const radical = findLayouts(layout, "sqrt")[0];
    const frac = findLayouts(layout, "frac")[0];
    expect(problems).toEqual([]);
    expect(getByTestId("math-sqrt")).toHaveStyle({ width: radical.width, height: radical.height });
    expect(getByTestId("math-text-tall")).toHaveStyle({ minWidth: layout.width, height: layout.height });
    expect(getByTestId("math-sqrt-radicand")).toHaveStyle({
      marginLeft: radical.lead,
      marginTop: radical.bodyTop,
      width: radical.children[0]?.width,
      height: radical.bodyHeight,
    });
    expect(getByTestId("math-frac")).toHaveStyle({ width: frac.width, height: frac.height });
    expect(getByTestId("math-radical-glyph")).toHaveProp("width", radical.width);
    expect(getByTestId("math-radical-glyph")).toHaveProp("height", radical.height);
    expect(getByText("x")).toBeOnTheScreen();
    expect(getByText("y")).toBeOnTheScreen();
  });

  it("BUG FIX regression: a script inside \\sqrt{} does not leak a literal caret", async () => {
    // Live: "√ 8^3" — the radicand was flattened with segmentsToPlain, which
    // turns a sup segment back into `^3`.
    const { queryByText } = await render(<MathText latex={String.raw`\sqrt{8^3}`} />);
    expect(queryByText(/\^/)).toBeNull();
    expect(screen.getByText("8")).toBeOnTheScreen();
    expect(screen.getByTestId("math-script")).toHaveTextContent("3");
    expect(screen.queryByText("³")).toBeNull();
  });

  it("renders an nth-root index without \\sqrt[n] brackets", async () => {
    const { getByTestId, getAllByText, queryByText } = await render(
      <MathText latex={String.raw`\sqrt[9]{9}`} />,
    );
    expect(getByTestId("math-sqrt")).toBeOnTheScreen();
    expect(getAllByText("9")).toHaveLength(2);
    expect(queryByText("√[9]9̅")).toBeNull();
    expect(queryByText(/√\[9\]/)).toBeNull();
  });

  it("keeps a slash exponent readable and raised in a sized native View", async () => {
    const latex = "9^{1/6}";
    const { getByTestId, getByText, queryByText } = await render(<MathText latex={latex} />);
    const { layout, problems } = laidOut(latex);
    const script = findLayouts(layout, "script")[0];
    expect(problems).toEqual([]);
    expect(queryByText("1/6")).toBeNull();
    expect(getByText("1")).toBeOnTheScreen();
    expect(getByText("6")).toBeOnTheScreen();
    expect(getByTestId("math-script-bar")).toBeOnTheScreen();
    expect(getByTestId("math-fractional-sup")).toHaveStyle({
      height: script.height,
      paddingBottom: script.raise,
    });
    expect(getByTestId("math-text-tall")).toHaveStyle({ height: layout.height });
    expect(queryByText("¹⁄⁶")).toBeNull();
  });

  it("draws a fraction and a radical inside an exponent", async () => {
    const frac = String.raw`x^{\frac{1}{2}}`;
    const root = String.raw`x^{\sqrt{2}}`;
    const { getByTestId, queryByText, getAllByText } = await render(<MathText latex={frac} />);
    expect(laidOut(frac).problems).toEqual([]);
    expect(queryByText(/\\frac/)).toBeNull();
    expect(queryByText("1/2")).toBeNull();
    expect(getByTestId("math-frac")).toBeOnTheScreen();
    expect(getAllByText("1").length).toBeGreaterThan(0);
    expect(getAllByText("2").length).toBeGreaterThan(0);

    const rooted = await render(<MathText latex={root} />);
    expect(laidOut(root).problems).toEqual([]);
    expect(rooted.queryByText(/\\sqrt/)).toBeNull();
    expect(rooted.getByTestId("math-sqrt")).toBeOnTheScreen();
    expect(rooted.getByText("2")).toBeOnTheScreen();
  });

  it("draws a fraction root index instead of the characters \\frac", async () => {
    const latex = String.raw`\sqrt[\frac{1}{2}]{x}`;
    const { getByTestId, queryByText, getByText } = await render(<MathText latex={latex} />);
    expect(laidOut(latex).problems).toEqual([]);
    expect(queryByText(/\\frac/)).toBeNull();
    expect(getByTestId("math-sqrt-index")).toBeOnTheScreen();
    expect(getByTestId("math-frac")).toBeOnTheScreen();
    expect(getByText("x")).toBeOnTheScreen();
  });

  it("preserves scripts in fraction sides instead of flattening to literal carets", async () => {
    const { queryByText, getByText, getAllByTestId } = await render(
      <MathText latex={String.raw`\frac{x^2}{y_1}`} />,
    );
    expect(queryByText(/\^|_/)).toBeNull();
    expect(queryByText("²")).toBeNull();
    expect(queryByText("₁")).toBeNull();
    expect(getByText("2")).toBeOnTheScreen();
    expect(getByText("1")).toBeOnTheScreen();
    expect(getAllByTestId("math-script")).toHaveLength(2);
  });

  it("reserves the full height of nested fraction stacks", async () => {
    const { getAllByTestId, getByTestId } = await render(
      <MathText latex={String.raw`\frac{\frac{1}{2}}{\frac{3}{4}}`} />,
    );
    const stacks = getAllByTestId("math-frac");
    const outer = StyleSheet.flatten(stacks[0].props.style);
    const inner = StyleSheet.flatten(stacks[1].props.style);
    expect(outer.height).toBeGreaterThanOrEqual(2 * inner.height + 6);
    expect(getByTestId("math-text-tall")).toHaveStyle({ height: outer.height });
  });

  it("scales the native attachment bounds with the requested text size", async () => {
    const { getByTestId, getByText } = await render(
      <MathText latex={String.raw`\frac{1}{2}`} fontSize={24} />,
    );
    expect(getByText("1")).toHaveStyle({ fontSize: 21, lineHeight: 27 });
    const { layout } = laidOut(String.raw`\frac{1}{2}`, 24);
    const frac = findLayouts(layout, "frac")[0];
    expect(getByTestId("math-frac")).toHaveStyle({ width: frac.width, height: frac.height });
    expect(frac.width / findLayouts(laidOut(String.raw`\frac{1}{2}`).layout, "frac")[0].width).toBeCloseTo(1.5, 5);
  });

  it("reserves more space when the device increases its font scale", async () => {
    jest.spyOn(Dimensions, "get").mockReturnValue({
      width: 390, height: 844, scale: 3, fontScale: 1.5,
    });
    const { getByTestId, getByText } = await render(<MathText latex={String.raw`\frac{1}{2}`} />);
    const { layout } = laidOut(String.raw`\frac{1}{2}`);
    const frac = findLayouts(layout, "frac")[0];
    expect(getByTestId("math-frac")).toHaveStyle({ width: frac.width * 1.5, height: frac.height * 1.5 });
    expect(getByTestId("math-text-tall")).toHaveStyle({
      minWidth: layout.width * 1.5,
      height: layout.height * 1.5,
    });
    expect(getByText("1")).toHaveStyle({ fontSize: 14 });
  });

  it("places the root degree in the hook instead of above the bar", async () => {
    const latex = String.raw`\sqrt[6]{9}`;
    const { getByText } = await render(<MathText latex={latex} />);
    const radical = findLayouts(laidOut(latex).layout, "sqrt")[0];
    expect(radical.index).toBeDefined();
    expect(laidOut(latex).problems).toEqual([]);
    expect(getByText("6")).toHaveStyle({
      fontSize: radical.index?.fontSize,
      lineHeight: radical.index?.lineHeight,
      left: radical.index?.left,
      top: radical.index?.top,
    });
    const barY = (radical.em ?? 16) * 0.05;
    const indexTop = radical.index?.top ?? 0;
    const indexBottom = indexTop + (radical.index?.lineHeight ?? 0);
    expect(indexTop).toBeLessThanOrEqual(barY + 0.5);
    expect(indexBottom).toBeGreaterThan(barY + 1);
    expect((radical.index?.left ?? 0) + (radical.index?.width ?? 0)).toBeLessThan(radical.barStart ?? 0);
    expect(getByText("9")).toHaveStyle({ fontSize: 16 });
  });

  it("draws an overline from the ink width, not the container", async () => {
    const { getByTestId, queryByText } = await render(
      <MathText latex={String.raw`\overline{AB}`} />,
    );
    const { layout, problems } = laidOut(String.raw`\overline{AB}`);
    const accent = findLayouts(layout, "accent")[0];
    expect(problems).toEqual([]);
    expect(getByTestId("math-accent")).toHaveStyle({ width: accent.width, height: accent.height });
    expect(getByTestId("math-accent-rule")).toHaveStyle({ width: accent.ruleWidth });
    expect(Math.abs((accent.ruleWidth ?? 0) - accent.inkWidth)).toBeLessThanOrEqual(16 * 0.2);
    expect(queryByText(/̅/)).toBeNull();
  });

  it("paints blackboard bold with the AMS face, not a missing unicode glyph", async () => {
    const { getByTestId, queryByText } = await render(
      <MathText latex={String.raw`x \in \mathbb{R}`} />,
    );
    expect(getByTestId("math-blackboard")).toHaveTextContent("R");
    expect(getByTestId("math-blackboard")).toHaveStyle({ fontFamily: "KaTeX_AMS" });
    expect(queryByText("ℝ")).toBeNull();
  });

  it("stacks a subscript and superscript in one column", async () => {
    const { getByTestId } = await render(<MathText latex="x_i^2" />);
    const column = getByTestId("math-script-column");
    const { layout } = laidOut("x_i^2");
    const box = findLayouts(layout, "script").find((item) => item.children.length === 2);
    expect(box).toBeDefined();
    expect(column).toHaveStyle({ width: box?.width, height: box?.height });
    expect(getByTestId("math-script-column")).toBeOnTheScreen();
    expect(screen.getByText("i")).toBeOnTheScreen();
    expect(screen.getByText("2")).toBeOnTheScreen();
  });

  it("stretches a wide hat across the letters it covers", async () => {
    const { getByTestId } = await render(<MathText latex={String.raw`\widehat{ABC}`} />);
    const { layout, problems } = laidOut(String.raw`\widehat{ABC}`);
    const accent = findLayouts(layout, "accent")[0];
    expect(problems).toEqual([]);
    expect(accent.spanAccent).toBe(true);
    expect(Math.abs((accent.ruleWidth ?? 0) - accent.inkWidth)).toBeLessThanOrEqual(16 * 0.2);
    const rule = getByTestId("math-accent-rule");
    expect(rule.props.width ?? StyleSheet.flatten(rule.props.style).width).toBe(accent.ruleWidth);
  });
});
