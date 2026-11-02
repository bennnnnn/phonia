/**
 * A chart the card cannot draw is never a blank plot: it says so, shows the chart's
 * data as a table when it has any. Its source is never shown.
 */
import { act, render } from "@testing-library/react-native";
import type { ReactElement } from "react";

import { ChartBlock } from "@/components/rich/ChartBlock";
import { previewPageFile } from "@/lib/preview/previewPageFile";

jest.mock("expo-file-system/legacy", () => ({}));
jest.mock("@/lib/preview/previewPageFile", () => ({
  previewPageFile: jest.fn(async () => "file:///cache/preview-pages/chart-0123456789abcdef.html"),
  readyPreviewPageFile: jest.fn(() => null),
  forgetPreviewPageFile: jest.fn(),
}));

const mockRenders: Record<string, unknown>[] = [];
jest.mock("@/lib/webView", () => {
  const React = jest.requireActual<typeof import("react")>("react");
  const { View } = jest.requireActual<typeof import("react-native")>("react-native");
  function MockWebView(props: Record<string, unknown>) {
    mockRenders.push(props);
    return React.createElement(View, { testID: "preview-webview" });
  }
  return {
    ...jest.requireActual("@/lib/webView"),
    getPreviewWebView: () => ({ mode: "rnc", Component: MockWebView }),
  };
});

const renderChart = (content: string) => render(<ChartBlock content={content} /> as ReactElement);

beforeEach(() => {
  mockRenders.length = 0;
  jest.mocked(previewPageFile).mockClear();
});

it("does not load the chart page for a body it cannot draw, and never shows its source", async () => {
  // A curve written as a formula: the server draws these; the phone never evaluates one.
  const body = '{"type":"function","fn":"sin(x)","domain":[0,6.28]}';
  const view = await renderChart(body);

  expect(view.getByText("rich.chart_error")).toBeTruthy();
  expect(view.queryByTestId("preview-webview")).toBeNull();
  expect(previewPageFile).not.toHaveBeenCalled();
  expect(view.queryByText(body)).toBeNull();
  expect(view.queryByRole("button")).toBeNull();
});

it("shows the chart's data as a table when the page draws nothing", async () => {
  const body = JSON.stringify({
    mark: "bar",
    data: { values: [{ day: "Mon", value: 12 }, { day: "Tue", value: 19 }] },
  });
  const view = await renderChart(body);
  await view.findByTestId("preview-webview");

  const onMessage = mockRenders[mockRenders.length - 1]!.onMessage as (event: {
    nativeEvent: { data: string };
  }) => void;
  await act(async () =>
    onMessage({ nativeEvent: { data: JSON.stringify({ kind: "chart-error", message: "No data marks were drawn." }) } }),
  );

  expect(view.queryByTestId("preview-webview")).toBeNull();
  expect(view.getByText("rich.chart_data_instead")).toBeTruthy();
  for (const cell of ["day", "value", "Mon", "12", "Tue", "19"]) expect(view.getByText(cell)).toBeTruthy();
  // Vega's own message is not the user's to read.
  expect(view.queryByText("No data marks were drawn.")).toBeNull();
});
