import { render } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import { FunctionGraphBlock } from "@/components/rich/FunctionGraphBlock";
import { darkTheme, lightTheme } from "@/lib/theme";

let mockScheme: "light" | "dark" = "light";
const mockPolyline = jest.fn((_props: Record<string, unknown>) => null);

jest.mock("@/lib/colorScheme", () => ({
  useResolvedColorScheme: () => mockScheme,
}));
jest.mock("@/lib/skiaAvailability", () => ({ isSkiaAvailable: () => false }));
jest.mock("react-native-svg", () => ({
  ...jest.requireActual("react-native-svg"),
  __esModule: true,
  Polyline: (props: Record<string, unknown>) => mockPolyline(props),
}));

describe("comparison graph series", () => {
  it.each([lightTheme, darkTheme])("distinguishes curves and matching series dots in $scheme mode", async (theme) => {
    mockScheme = theme.scheme;
    mockPolyline.mockClear();
    const content = JSON.stringify({
      type: "function", expr: "x**2", expr2: "2*x", title: "Comparison",
      points: [[-2, 4], [0, 0], [2, 4]], points2: [[-2, -4], [0, 0], [2, 4]],
      label: "Parabola", label2: "Line",
    });
    const { getByDisplayValue } = await render(<FunctionGraphBlock content={content} />);
    const strokes = mockPolyline.mock.calls.map(([props]) => props.stroke);
    expect(strokes).toEqual([theme.graphSeries[0], theme.graphSeries[1]]);
    expect(strokes[0]).not.toBe(strokes[1]);
    expect(getByDisplayValue("y = x^2")).toBeOnTheScreen();
    expect(getByDisplayValue("y = 2*x")).toBeOnTheScreen();
    for (const color of [theme.graphSeries[0], theme.graphSeries[1]]) {
      const marker = mockPolyline.mock.calls
        .map(([props]) => props)
        .find((props) => props.stroke === color);
      expect(marker).toBeTruthy();
    }
    const tree = getByDisplayValue("y = x^2").parent?.parent;
    expect(tree).toBeTruthy();
    const swatch = tree?.children.find(
      (child) => typeof child !== "string" && StyleSheet.flatten(child.props.style)?.backgroundColor,
    );
    expect(
      swatch && typeof swatch !== "string" && StyleSheet.flatten(swatch.props.style).backgroundColor,
    ).toBe(theme.graphSeries[0]);
  });
});
