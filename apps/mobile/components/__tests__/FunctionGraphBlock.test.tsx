import { fireEvent, render } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import { FunctionGraphBlock } from "@/components/rich/FunctionGraphBlock";
import { lightTheme } from "@/lib/theme";

jest.mock("@/lib/skiaAvailability", () => ({ isSkiaAvailable: () => false }));
// Chrome icons are SVG too; keep the path counts about the plotted curves.
jest.mock("@/ui/icons/Icon", () => ({ Icon: () => null }));

describe("FunctionGraphBlock", () => {
  it("renders the expression as the chart title", async () => {
    const content = JSON.stringify({
      type: "function",
      expr: "x**2",
      points: [
        [0, 0],
        [1, 1],
        [2, 4],
      ],
    });
    const { getByDisplayValue } = await render(<FunctionGraphBlock content={content} />);

    expect(getByDisplayValue("y = x^2")).toBeOnTheScreen();
  });

  it("outlines only the plot, not the surrounding function inputs", async () => {
    const content = JSON.stringify({
      type: "function",
      expr: "x**2",
      points: [
        [-1, 1],
        [0, 0],
        [1, 1],
      ],
    });
    const { getByTestId } = await render(<FunctionGraphBlock content={content} />);
    const card = StyleSheet.flatten(getByTestId("graph-card").props.style);
    const plot = StyleSheet.flatten(getByTestId("graph-expand").props.style);
    const expandCue = StyleSheet.flatten(getByTestId("graph-expand-cue").props.style);

    expect(card.backgroundColor).toBeUndefined();
    expect(card.borderWidth).toBeUndefined();
    expect(card.borderRadius).toBeUndefined();
    expect(card.padding).toBe(12);
    expect(card.shadowOpacity).toBeUndefined();
    expect(card.elevation).toBeUndefined();
    expect(plot.borderColor).toBe(lightTheme.primaryLight);
    expect(plot.borderWidth).toBe(1);
    expect(plot.borderRadius).toBeGreaterThanOrEqual(12);
    expect(plot.backgroundColor).toBe("#F7F7F8");
    expect(expandCue.backgroundColor).toBeUndefined();
    expect(expandCue.borderWidth).toBeUndefined();
    expect(expandCue.width).toBe(28);
    expect(expandCue.height).toBe(28);
  });

  it("renders even ticks for y = x², not padded −12 / 108 / −8", async () => {
    const content = JSON.stringify({
      type: "function",
      expr: "x**2",
      x_min: -10,
      x_max: 10,
      points: [
        [-10, 100],
        [0, 0],
        [10, 100],
      ],
    });
    const { getByDisplayValue, queryByText, toJSON } = await render(
      <FunctionGraphBlock content={content} />,
    );
    expect(getByDisplayValue("y = x^2")).toBeOnTheScreen();
    expect(queryByText("108")).toBeNull();
    expect(queryByText("-12")).toBeNull();
    expect(queryByText("-8")).toBeNull();
    const tree = JSON.stringify(toJSON());
    expect(tree).not.toContain('"-12"');
    expect(tree).toContain('"content":"-3"');
    expect(tree).toContain('"content":"-2"');
    expect(tree).toContain('"content":"-1"');
    expect(tree).toContain('"content":"0"');
    expect(tree).toContain('"content":"1"');
    expect(tree).toContain("RNSVGLine");
    expect(tree).toContain("RNSVGPath");
  });

  it("prefers an explicit title over the default y = expr label", async () => {
    const content = JSON.stringify({
      type: "function",
      expr: "x**2",
      title: "Parabola",
      points: [
        [0, 0],
        [1, 1],
      ],
    });
    const { getByText, toJSON } = await render(<FunctionGraphBlock content={content} />);

    expect(getByText("Parabola")).toBeOnTheScreen();
    // A 2-point scatter still gets markers; vertical lines (below) do not.
    expect(JSON.stringify(toJSON())).toContain("RNSVGCircle");
  });

  it("renders one polyline per segment for a discontinuous (segmented) function", async () => {
    // Segments are how a backend-detected asymptote (e.g. tan(x)) is drawn
    // as separate Polylines instead of one line straight across the gap —
    // this exercises the segmentPolylines branch, not the single-polyline one.
    const content = JSON.stringify({
      type: "function",
      expr: "tan(x)",
      points: [
        [-1, -1.5],
        [1, 1.5],
      ],
      segments: [
        [
          [-1, -1.5],
          [0, 0],
        ],
        [
          [0.1, 0.5],
          [1, 1.5],
        ],
      ],
    });
    const { toJSON } = await render(<FunctionGraphBlock content={content} />);
    const tree = toJSON();
    const pathCount = (JSON.stringify(tree).match(/"RNSVGPath"/g) ?? []).length;

    expect(pathCount).toBe(2);
  });

  it("renders the fallback message for unparseable content", async () => {
    const { getByText } = await render(<FunctionGraphBlock content="not json" />);
    expect(getByText("rich.graph_error")).toBeOnTheScreen();
  });

  it("BUG FIX regression: renders a vertical line fence (x = c)", async () => {
    const content = JSON.stringify({
      type: "vertical",
      x: 4,
      y_min: -5,
      y_max: 5,
      title: "x = 4",
    });
    const { getByText, toJSON } = await render(<FunctionGraphBlock content={content} />);
    expect(getByText("x = 4")).toBeOnTheScreen();
    expect(JSON.stringify(toJSON())).toContain("RNSVGSvgView");
    // Endpoint caps would make x = c look like a finite segment.
    expect(JSON.stringify(toJSON())).not.toContain("RNSVGCircle");
  });

  it("renders x > 3 as a 1D number line, not a 2D half-plane", async () => {
    const content = JSON.stringify({
      type: "number_line",
      expr: "x > 3",
      title: "x > 3",
      intervals: [{ start: 3, end: null, start_inclusive: false, end_inclusive: false }],
    });
    const { getByText, queryByText, toJSON } = await render(
      <FunctionGraphBlock content={content} />,
    );
    expect(getByText("x > 3")).toBeOnTheScreen();
    expect(queryByText("y = x > 3")).toBeNull();
    const tree = JSON.stringify(toJSON());
    expect(tree).toContain("RNSVGSvgView");
    // A number line has a ray arrow (Polygon), not a shaded Rect half-plane.
    expect(tree).toContain("RNSVGPath");
    expect(tree).not.toContain("RNSVGRect");
  });

  it("renders two curves with a legend when expr2/points2 are present", async () => {
    const content = JSON.stringify({
      type: "function",
      expr: "x**2",
      points: [
        [-2, 4],
        [0, 0],
        [2, 4],
      ],
      expr2: "2*x",
      points2: [
        [-2, -4],
        [2, 4],
      ],
      label: "y = x^2",
      label2: "y = 2x",
    });
    const { getByDisplayValue, getByTestId, queryByTestId, toJSON } = await render(
      <FunctionGraphBlock content={content} />,
    );

    expect(getByDisplayValue("y = x^2")).toBeOnTheScreen();
    expect(getByDisplayValue("y = 2*x")).toBeOnTheScreen();
    expect(getByTestId("graph-expand")).toBeOnTheScreen();
    expect(queryByTestId("graph-hide-1")).toBeNull();
    expect(queryByTestId("graph-remove-1")).toBeNull();
    // Polyline renders as RNSVGPath in this native mock (see the segmented
    // discontinuity test above) — one per curve.
    const pathCount = (JSON.stringify(toJSON()).match(/"RNSVGPath"/g) ?? []).length;
    expect(pathCount).toBe(2);
  });

  it("typesets the exponent in the exact x^2 < 4 number-line title", async () => {
    const content = JSON.stringify({
      type: "number_line",
      expr: "x^2 < 4",
      title: "x^2 < 4",
      intervals: [{ start: -2, end: 2, start_inclusive: false, end_inclusive: false }],
      points: [],
    });
    const { getByText, queryByText } = await render(<FunctionGraphBlock content={content} />);
    expect(getByText("x² < 4")).toBeOnTheScreen();
    expect(queryByText("x^2 < 4")).toBeNull();
  });

  it("renders the exact E07 number-line title with absolute-value bars", async () => {
    const content = JSON.stringify({
      type: "number_line",
      expr: "Abs(x-2) < 5",
      title: "Abs(x-2) < 5",
      intervals: [{ start: -3, end: 7, start_inclusive: false, end_inclusive: false }],
      points: [],
    });
    const { getByText, queryByText } = await render(<FunctionGraphBlock content={content} />);
    expect(getByText("|x-2| < 5")).toBeOnTheScreen();
    expect(queryByText("Abs(x-2) < 5")).toBeNull();
  });

  it("renders a single curve (no legend) when expr2 is absent", async () => {
    const content = JSON.stringify({
      type: "function",
      expr: "x**2",
      points: [
        [0, 0],
        [1, 1],
      ],
    });
    const { queryByText } = await render(<FunctionGraphBlock content={content} />);
    expect(queryByText(/y = 2x/)).toBeNull();
  });

  it("renders a verified trajectory on the native Skia canvas", async () => {
    const content = JSON.stringify({
      type: "trajectory",
      expr: "h(t) = 20 - 0.5*9.81*t^2",
      title: "Height vs. Time",
      x_label: "Time (s)",
      y_label: "Height (m)",
      trajectory_type: "position_vs_time",
      points: [
        [0, 20],
        [1, 15.095],
        [2, 0.38],
      ],
    });
    const { getByText, getByTestId } = await render(<FunctionGraphBlock content={content} />);

    expect(getByText("Height vs. Time")).toBeOnTheScreen();
    expect(getByTestId("trajectory-canvas")).toBeOnTheScreen();
  });

  it("formats a backend-supplied SymPy title", async () => {
    const content = JSON.stringify({
      type: "function",
      expr: "x**2/9 + y**2/4",
      title: "x**2/9 + y**2/4 = 1",
      points: [
        [0, 0],
        [1, 1],
      ],
    });
    const { getByText } = await render(<FunctionGraphBlock content={content} />);
    expect(getByText("x²/9 + y²/4 = 1")).toBeOnTheScreen();
  });

  it("formats comparison legend labels from raw SymPy", async () => {
    const content = JSON.stringify({
      type: "function",
      title: "Comparison",
      expr: "3*x**2",
      points: [
        [-1, 3],
        [1, 3],
      ],
      expr2: "2*x",
      points2: [
        [-1, -2],
        [1, 2],
      ],
      label: "y = 3*x**2",
      label2: "y = 2*x",
    });
    const { getByDisplayValue, getByText } = await render(
      <FunctionGraphBlock content={content} />,
    );
    expect(getByText("Comparison")).toBeOnTheScreen();
    expect(getByDisplayValue("y = 3*x^2")).toBeOnTheScreen();
    expect(getByDisplayValue("y = 2*x")).toBeOnTheScreen();
  });

  it("formats inequality titles including * multiplication", async () => {
    const content = JSON.stringify({
      type: "number_line",
      expr: "3*x - 6 >= 0",
      title: "3*x - 6 >= 0",
      intervals: [{ start: 2, end: null, start_inclusive: true, end_inclusive: false }],
    });
    const { getByText } = await render(<FunctionGraphBlock content={content} />);
    expect(getByText("3x - 6 ≥ 0")).toBeOnTheScreen();
  });

  it("resamples the curve when the expression is edited", async () => {
    const content = JSON.stringify({
      type: "function",
      expr: "x",
      points: [
        [-1, -1],
        [1, 1],
      ],
    });
    const { getByTestId } = await render(<FunctionGraphBlock content={content} />);
    expect(getByTestId("graph-expr-input").props.placeholder).toBe(
      "rich.graph_expr_placeholder",
    );
    await fireEvent.changeText(getByTestId("graph-expr-input"), "x^2/3");
    expect(getByTestId("graph-expr-input").props.value).toBe("x^2/3");
  });

  it("opens a pinchable graph when the plot is tapped", async () => {
    const content = JSON.stringify({
      type: "function",
      expr: "x**2",
      points: [
        [0, 0],
        [1, 1],
        [2, 4],
      ],
    });
    const { getByLabelText, getByTestId, queryByTestId } = await render(
      <FunctionGraphBlock content={content} />,
    );
    expect(queryByTestId("graph-close")).toBeNull();
    await fireEvent.press(getByTestId("graph-expand"));
    expect(getByTestId("graph-close")).toBeOnTheScreen();
    const expandedPlot = getByLabelText("rich.graph_plot_a11y");
    expect(expandedPlot).toBeOnTheScreen();
    const expandedPlotStyle = StyleSheet.flatten(expandedPlot.props.style);
    expect(expandedPlotStyle.backgroundColor).toBe("#F7F7F8");
    expect(expandedPlotStyle.borderWidth).toBeGreaterThan(0);
    expect(expandedPlotStyle.borderRadius).toBeGreaterThanOrEqual(12);
    expect(expandedPlotStyle.marginHorizontal).toBe(12);
    expect(getByTestId("graph-expr-input")).toBeOnTheScreen();
  });

  it("scrolls padded series in the expanded graph and shows a drag handle", async () => {
    const content = JSON.stringify({
      type: "function",
      expr: "x**2",
      points: [
        [0, 0],
        [1, 1],
      ],
    });
    const { getByTestId, queryByTestId } = await render(<FunctionGraphBlock content={content} />);
    expect(queryByTestId("graph-sheet-handle")).toBeNull();
    expect(queryByTestId("graph-series-scroll")).toBeNull();
    await fireEvent.press(getByTestId("graph-expand"));
    expect(getByTestId("graph-sheet-handle")).toBeOnTheScreen();
    expect(getByTestId("graph-close")).toBeOnTheScreen();
    const backdrop = StyleSheet.flatten(getByTestId("graph-modal-backdrop").props.style);
    const keyboardHost = StyleSheet.flatten(
      getByTestId("graph-modal-keyboard-host").props.style,
    );
    const sheet = StyleSheet.flatten(getByTestId("graph-modal-sheet").props.style);
    const handleBar = getByTestId("graph-sheet-handle").children[0];
    if (typeof handleBar === "string") throw new Error("the handle holds a bar, not text");
    const handle = StyleSheet.flatten(handleBar.props.style);
    expect(backdrop.backgroundColor).toBe("rgba(0,0,0,0.40)");
    expect(keyboardHost.backgroundColor).toBeUndefined();
    expect(sheet.marginTop).toBeGreaterThan(0);
    expect(sheet.borderTopLeftRadius).toBeGreaterThanOrEqual(24);
    expect(sheet.borderTopRightRadius).toBeGreaterThanOrEqual(24);
    expect(handle.width).toBeGreaterThanOrEqual(44);
    expect(handle.height).toBeGreaterThanOrEqual(5);
    const list = getByTestId("graph-series-scroll");
    expect(list).toBeOnTheScreen();
    const pad = StyleSheet.flatten(list.props.contentContainerStyle);
    expect(pad.paddingHorizontal).toBe(16);
    await fireEvent.press(getByTestId("graph-add-function"));
    expect(getByTestId("graph-expr-input-1")).toBeOnTheScreen();
  });

  it("adds a second series from Add function", async () => {
    const content = JSON.stringify({
      type: "function",
      expr: "x**2",
      points: Array.from({ length: 97 }, (_, i) => {
        const x = -6 + (12 * i) / 96;
        return [x, x * x];
      }),
    });
    const { getByTestId } = await render(<FunctionGraphBlock content={content} />);
    await fireEvent.press(getByTestId("graph-add-function"));
    await fireEvent.changeText(getByTestId("graph-expr-input-1"), "x^2/3");
    expect(getByTestId("graph-expr-input-1").props.value).toBe("x^2/3");
    expect(getByTestId("graph-hide-1")).toBeOnTheScreen();
    expect(getByTestId("graph-remove-1")).toBeOnTheScreen();
  });

  it("says when an added expression cannot be plotted", async () => {
    const content = JSON.stringify({
      type: "function",
      expr: "x**2",
      points: Array.from({ length: 97 }, (_, i) => {
        const x = -6 + (12 * i) / 96;
        return [x, x * x];
      }),
    });
    const { getByTestId, getByText } = await render(<FunctionGraphBlock content={content} />);
    await fireEvent.press(getByTestId("graph-add-function"));
    await fireEvent.changeText(getByTestId("graph-expr-input-1"), "banana");
    expect(getByText("rich.graph_invalid")).toBeOnTheScreen();
  });

  it("plots an added inequality such as y < 2x", async () => {
    const content = JSON.stringify({
      type: "function",
      expr: "x**2",
      points: Array.from({ length: 97 }, (_, i) => {
        const x = -6 + (12 * i) / 96;
        return [x, x * x];
      }),
    });
    const { getByTestId } = await render(<FunctionGraphBlock content={content} />);
    await fireEvent.press(getByTestId("graph-add-function"));
    await fireEvent.changeText(getByTestId("graph-expr-input-1"), "y < 2x");
    expect(getByTestId("graph-expr-input-1").props.value).toBe("y < 2x");
    expect(getByTestId("graph-shade-1")).toBeOnTheScreen();
  });
});
