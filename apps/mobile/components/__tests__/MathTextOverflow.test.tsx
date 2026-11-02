import { render, within } from "@testing-library/react-native";
import { Dimensions, StyleSheet } from "react-native";

import { MathText } from "@/components/rich/MathText";
import { layoutMath } from "@/lib/math/layout";
import { fixImplicitExponents } from "@/lib/math/normalizeImplicit";
import { parseSimpleLatex } from "@/lib/math/text";

function contentWidth(latex: string, fontSize = 16): number {
  return layoutMath(parseSimpleLatex(fixImplicitExponents(latex.trim())), fontSize).width;
}

const slantHeight = String.raw`\text{Slant Height} = \sqrt{ \left( \frac{6}{2} \right)^2 + 4^2 } = \sqrt{3^2 + 4^2} = \sqrt{9 + 16} = \sqrt{25} = 5\text{.}`;

describe("inline tall math overflow", () => {
  beforeEach(() => {
    jest.spyOn(Dimensions, "get").mockReturnValue({ width: 390, height: 844, scale: 3, fontScale: 1 });
  });
  afterEach(() => jest.restoreAllMocks());

  it("keeps the entire B12 chain reachable inside a paragraph-bounded horizontal viewport", async () => {
    const { getByTestId } = await render(<MathText latex={slantHeight} scrollOverflow />);
    const viewport = getByTestId("math-text-scroll");
    const formula = within(viewport).getByTestId("math-text-tall");
    const frameStyle = StyleSheet.flatten(viewport.props.style);
    const contentStyle = StyleSheet.flatten(formula.props.style);
    expect(viewport.props.horizontal).toBe(true);
    expect(viewport.props.showsHorizontalScrollIndicator).toBe(true);
    expect(viewport.props.bounces).toBe(false);
    expect(frameStyle).toMatchObject({ maxWidth: "100%", flexGrow: 0, flexShrink: 1 });
    expect(contentStyle.flexShrink).toBe(0);
    // The viewport is only maxWidth 100%. Setting width to the formula
    // made the scroll frame as wide as the math, so the tail could not move.
    expect(contentStyle.width).toBeUndefined();
    expect(frameStyle.width).toBeUndefined();
    expect(contentStyle.minWidth).toBe(contentWidth(slantHeight));
    expect(contentStyle.minWidth).toBeGreaterThan(390);
    const uprightRuns = within(viewport).getAllByTestId("math-upright-run");
    expect(uprightRuns[0]).toHaveTextContent("Slant Height");
    expect(uprightRuns[0]).toHaveStyle({ fontFamily: "KaTeX_Main", fontSize: 16 });
    expect(within(viewport).getByText(/= 5/)).toBeOnTheScreen();
    expect(within(viewport).getAllByTestId("math-sqrt")).toHaveLength(4);
    expect(within(viewport).getByText("6")).toHaveStyle({ fontSize: 14 });
    expect(viewport.props.accessibilityLabel).toMatch(/Slant Height.*= 5\./);
    expect(viewport.props.accessibilityLabel).not.toMatch(/\\sqrt|\\frac|\\text/);
  });

  it("lets native glyph width extend the scroll content beyond its estimate", async () => {
    const { getByTestId, getByText } = await render(
      <MathText latex={String.raw`\sqrt{99999999999999999999}`} scrollOverflow />,
    );
    const formula = getByTestId("math-text-tall");
    const style = StyleSheet.flatten(formula.props.style);
    const latex = String.raw`\sqrt{99999999999999999999}`;
    expect(style.minWidth).toBe(contentWidth(latex));
    expect(style.minWidth).toBeGreaterThan(160);
    expect(style.width).toBeUndefined();
    expect(style.maxWidth).toBeUndefined();
    expect(style.flexShrink).toBe(0);
    expect(getByText("99999999999999999999")).toHaveStyle({ fontSize: 16 });
    expect(getByTestId("math-text-scroll").props.horizontal).toBe(true);
  });

  it("keeps a short fraction's original width, height, and type size", async () => {
    const latex = String.raw`\frac{1}{2}`;
    const { getByTestId, getByText } = await render(<MathText latex={latex} scrollOverflow />);
    const width = contentWidth(latex);
    const height = layoutMath(parseSimpleLatex(fixImplicitExponents(latex)), 16).height;
    expect(StyleSheet.flatten(getByTestId("math-text-scroll").props.style).width).toBeUndefined();
    expect(getByTestId("math-text-scroll")).toHaveStyle({ height, maxWidth: "100%" });
    expect(getByTestId("math-text-tall")).toHaveStyle({ minWidth: width, height });
    expect(getByText("1")).toHaveStyle({ fontSize: 14, lineHeight: 18 });
  });

  it("raises a short power in a View without opening a scroller", async () => {
    const { rerender, queryByTestId, getByTestId } = await render(<MathText latex="x^2 + 1" scrollOverflow />);
    expect(queryByTestId("math-text-scroll")).toBeNull();
    expect(getByTestId("math-text-tall")).toBeOnTheScreen();
    expect(getByTestId("math-script")).toHaveTextContent("2");
    await rerender(<MathText latex={slantHeight} />);
    expect(queryByTestId("math-text-scroll")).toBeNull();
  });

  it("scrolls a long unstacked equation instead of wrapping it mid-formula", async () => {
    const latex = `${"x+1+".repeat(30)}x`;
    const { getByTestId } = await render(<MathText latex={latex} scrollOverflow />);
    const frame = StyleSheet.flatten(getByTestId("math-text-scroll").props.style);
    const formula = StyleSheet.flatten(getByTestId("math-text-wide").props.style);
    expect(frame.width).toBeUndefined();
    expect(frame.maxWidth).toBe("100%");
    expect(formula.minWidth).toBe(contentWidth(latex));
    expect(formula.flexShrink).toBe(0);
    expect(formula.minWidth).toBeGreaterThan(390);
  });
});
