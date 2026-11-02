import { render } from "@testing-library/react-native";

import { ChartBlock } from "@/components/rich/ChartBlock";

// No preview WebView here (as in Expo Go): the card says a dev build draws it.
jest.mock("react-native-webview", () => {
  throw new Error("react-native-webview native module is not linked (test)");
});
jest.mock("@expo/dom-webview", () => {
  throw new Error("@expo/dom-webview native module is not linked (test)");
});
jest.mock("expo-file-system/legacy", () => ({}));

const SPEC = JSON.stringify(
  { mark: "bar", data: { values: [{ a: "Mon", b: 12 }] }, encoding: {} },
  null,
  2,
);

describe("ChartBlock header", () => {
  it("names the chart without counting the lines of its JSON", async () => {
    const { getByText, queryByText } = await render(<ChartBlock content={SPEC} />);
    expect(getByText("rich.chart")).toBeOnTheScreen();
    expect(queryByText(/lines/)).toBeNull();
  });

  it("has no copy, source or chart-editor button", async () => {
    const { queryByLabelText } = await render(<ChartBlock content={SPEC} />);
    for (const label of ["common.copy", "rich.source", "rich.vega_editor"]) {
      expect(queryByLabelText(label)).toBeNull();
    }
  });
});
