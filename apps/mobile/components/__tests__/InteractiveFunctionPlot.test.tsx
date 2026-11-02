/**
 * The function plot card and its full-screen explorer, rendered directly:
 * the card's size and title, the series editor in the card and then in the
 * explorer, hole markers, the explorer's own plot size, and the Skia canvas
 * with the SVG one standing in while it loads.
 */
import { act, fireEvent, render } from "@testing-library/react-native";
import { ScrollView, StyleSheet } from "react-native";

import { InteractiveFunctionPlot } from "@/components/rich/InteractiveFunctionPlot";
import { parseGraphSpec, type GraphSpec } from "@/lib/math/graphSpec";
import { lightTheme } from "@/lib/theme";

jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 20, bottom: 10, left: 0, right: 0 }),
}));
let mockSkia = false;
jest.mock("@/lib/skiaAvailability", () => ({ isSkiaAvailable: () => mockSkia }));
jest.mock("@/ui/icons/Icon", () => ({ Icon: () => null }));

const STYLES = { wrap: { marginVertical: 4 }, title: { color: "#111111" } };

function spec(fence: Record<string, unknown>): GraphSpec {
  const parsed = parseGraphSpec(JSON.stringify(fence));
  if (!parsed) throw new Error("expected the fence to parse");
  return parsed;
}

const PARABOLA = spec({
  type: "function",
  expr: "x**2",
  points: [
    [-2, 4],
    [-1, 1],
    [0, 0],
    [1, 1],
    [2, 4],
  ],
});

function plot(graph: GraphSpec, chartWidth = 300) {
  return render(<InteractiveFunctionPlot spec={graph} chartWidth={chartWidth} styles={STYLES} theme={lightTheme} />);
}

beforeEach(() => {
  mockSkia = false;
});

describe("InteractiveFunctionPlot", () => {
  it("sizes the card's plot to the chart less its inset, then to its laid-out width", async () => {
    const { getByTestId } = await plot(PARABOLA);
    const press = () => StyleSheet.flatten(getByTestId("graph-expand").props.style);
    expect(press().width).toBe(276);
    expect(press().height).toBe(220);
    await fireEvent(getByTestId("graph-card"), "layout", { nativeEvent: { layout: { width: 340, height: 300 } } });
    expect(press().width).toBe(316);
    // A width that rounds to the same size, or to nothing, keeps the plot as it is.
    await fireEvent(getByTestId("graph-card"), "layout", { nativeEvent: { layout: { width: 340.2, height: 300 } } });
    await fireEvent(getByTestId("graph-card"), "layout", { nativeEvent: { layout: { width: 10, height: 300 } } });
    expect(press().width).toBe(316);
  });

  it("titles a custom title, never a title that repeats the expression", async () => {
    const titled = await plot(spec({ type: "function", expr: "x**2", title: "Area x**2", points: [[0, 0], [1, 1]] }));
    expect(titled.getByText("Area x²")).toBeOnTheScreen();
    const plain = await plot(spec({ type: "function", expr: "x**2", title: "x**2", points: [[0, 0], [1, 1]] }));
    expect(plain.queryByText("x²")).toBeNull();
    expect(plain.getByDisplayValue("y = x^2")).toBeOnTheScreen();
  });

  it("titles a vertical line and offers no editor for it", async () => {
    const { getByText, queryByTestId } = await plot(spec({ type: "vertical", expr: "x = 3", x: 3 }));
    expect(getByText("x = 3")).toBeOnTheScreen();
    expect(queryByTestId("graph-expr-input")).toBeNull();
    expect(queryByTestId("graph-add-function")).toBeNull();
  });

  it("adds, hides and removes a series in the card", async () => {
    const { getByTestId, queryByTestId } = await plot(PARABOLA);
    await fireEvent.press(getByTestId("graph-add-function"));
    await fireEvent.changeText(getByTestId("graph-expr-input-1"), "2x");
    expect(getByTestId("graph-expr-input-1").props.value).toBe("2x");
    await fireEvent.press(getByTestId("graph-hide-1"));
    expect(StyleSheet.flatten(getByTestId("graph-expr-input-1").props.style).opacity).toBe(0.4);
    await fireEvent.press(getByTestId("graph-hide-1"));
    expect(StyleSheet.flatten(getByTestId("graph-expr-input-1").props.style).opacity).toBeUndefined();
    await fireEvent.press(getByTestId("graph-remove-1"));
    expect(queryByTestId("graph-expr-input-1")).toBeNull();
    // The seeded expression is locked: it has no hide or remove buttons.
    expect(queryByTestId("graph-hide-0")).toBeNull();
  });

  it("marks holes while the seeded expression stands, and drops them once it is edited", async () => {
    const holed = spec({
      type: "function",
      expr: "(x**2-1)/(x-1)",
      points: [[-2, -1], [0, 1], [2, 3]],
      holes: [[1, 2]],
    });
    const { getByTestId, queryByTestId } = await plot(holed);
    expect(getByTestId("graph-hole-0")).toBeOnTheScreen();
    await fireEvent.changeText(getByTestId("graph-expr-input"), "x + 1");
    expect(queryByTestId("graph-hole-0")).toBeNull();
  });

  it("moves the editor into the explorer while it is open, and back when it closes", async () => {
    const { getByTestId, getAllByTestId, queryByTestId } = await plot(PARABOLA);
    expect(queryByTestId("graph-modal-sheet")).toBeNull();
    expect(queryByTestId("graph-series-scroll")).toBeNull();
    await fireEvent.press(getByTestId("graph-expand"));
    expect(getByTestId("graph-modal-sheet")).toBeOnTheScreen();
    expect(getAllByTestId("graph-expr-input")).toHaveLength(1);
    expect(getByTestId("graph-series-scroll")).toBeOnTheScreen();
    const sheet = StyleSheet.flatten(getByTestId("graph-modal-sheet").props.style);
    expect(sheet.marginTop).toBe(20);
    expect(sheet.paddingBottom).toBe(10);
    expect(sheet.backgroundColor).toBe(lightTheme.elevated);
    await fireEvent.press(getByTestId("graph-close"));
    expect(queryByTestId("graph-modal-sheet")).toBeNull();
    expect(getByTestId("graph-expr-input")).toBeOnTheScreen();
    expect(queryByTestId("graph-series-scroll")).toBeNull();
  });

  it("scrolls an added series into view in the explorer", async () => {
    const scrollToEnd = jest.spyOn(ScrollView.prototype, "scrollToEnd").mockImplementation(() => undefined);
    const frame = jest.spyOn(globalThis, "requestAnimationFrame").mockImplementation((callback) => {
      callback(0);
      return 0;
    });
    try {
      const { getByTestId } = await plot(PARABOLA);
      await fireEvent.press(getByTestId("graph-add-function"));
      expect(scrollToEnd).not.toHaveBeenCalled();
      await fireEvent.press(getByTestId("graph-expand"));
      await fireEvent.press(getByTestId("graph-add-function"));
      expect(getByTestId("graph-expr-input-2")).toBeOnTheScreen();
      expect(scrollToEnd).toHaveBeenCalledWith({ animated: true });
    } finally {
      scrollToEnd.mockRestore();
      frame.mockRestore();
    }
  });

  it("sizes the explorer's plot to its laid-out box", async () => {
    const { getByTestId, getByLabelText, toJSON } = await plot(PARABOLA);
    await fireEvent.press(getByTestId("graph-expand"));
    const surface = getByLabelText("rich.graph_plot_a11y");
    await fireEvent(surface, "layout", { nativeEvent: { layout: { width: 333.4, height: 411.6 } } });
    const tree = JSON.stringify(toJSON());
    expect(tree).toContain('"width":333');
    expect(tree).toContain('"height":412');
  });

  it("draws on Skia when it is available, with the SVG plot standing in while it loads", async () => {
    mockSkia = true;
    const { getByTestId, findByTestId, queryByTestId } = await plot(PARABOLA);
    expect(queryByTestId("skia-graph-card") ?? getByTestId("graph-expand")).toBeOnTheScreen();
    expect(await findByTestId("skia-graph-card")).toBeOnTheScreen();
    await fireEvent.press(getByTestId("graph-expand"));
    expect(getByTestId("graph-interaction-surface")).toBeOnTheScreen();
    await act(async () => {});
    expect(getByTestId("skia-graph-canvas")).toBeOnTheScreen();
  });
});
