/**
 * The Mermaid card's chrome: a title that names the kind of diagram, a
 * full-screen view that draws a wide diagram at its own size, and an editor
 * button that says what it does.
 */
import { fireEvent, render } from "@testing-library/react-native";
import * as Clipboard from "expo-clipboard";
import * as WebBrowser from "expo-web-browser";

import { MermaidBlock } from "@/components/rich/MermaidBlock";
import { previewPageFile, readyPreviewPageFile } from "@/lib/preview/previewPageFile";

jest.mock("expo-file-system/legacy", () => ({}));
jest.mock("expo-web-browser", () => ({ openBrowserAsync: jest.fn() }));
jest.mock("@/lib/preview/previewPageFile", () => ({
  previewPageFile: jest.fn(),
  readyPreviewPageFile: jest.fn(() => null),
  forgetPreviewPageFile: jest.fn(),
}));

/** Each preview WebView drawn, by its testID. */
const mockWebViews = new Map<string, Record<string, unknown>>();
jest.mock("@/lib/webView", () => {
  const React = jest.requireActual<typeof import("react")>("react");
  const { View } = jest.requireActual<typeof import("react-native")>("react-native");
  function MockWebView(props: Record<string, unknown>) {
    const testID = (props.testID as string | undefined) ?? "preview-webview";
    mockWebViews.set(testID, props);
    return React.createElement(View, { testID });
  }
  return {
    ...jest.requireActual("@/lib/webView"),
    getPreviewWebView: () => ({ mode: "rnc", Component: MockWebView }),
  };
});

const ER = "erDiagram\n  BOOKS ||--o{ LOANS : has\n  MEMBERS ||--o{ LOANS : makes";

beforeEach(() => {
  mockWebViews.clear();
  jest.mocked(readyPreviewPageFile).mockReturnValue(null);
  jest.mocked(previewPageFile).mockResolvedValue("file:///cache/preview-pages/mermaid-0123.html");
});

describe("MermaidBlock card", () => {
  it("names the kind of diagram, not the tool", async () => {
    const { getByText, queryByText } = await render(<MermaidBlock content={ER} />);
    expect(getByText("rich.mermaid_kind_er")).toBeOnTheScreen();
    expect(queryByText(/Mermaid Diagram/)).toBeNull();
  });

  it("opens the diagram full screen at its own size, and closes it", async () => {
    const { findByTestId, getByLabelText, queryByTestId } = await render(<MermaidBlock content={ER} />);
    await findByTestId("preview-webview");
    expect(mockWebViews.get("preview-webview")?.injectedJavaScript).toContain('"natural":false');

    await fireEvent.press(getByLabelText("rich.diagram_full_screen"));
    await findByTestId("mermaid-full-screen-diagram");
    const full = mockWebViews.get("mermaid-full-screen-diagram");
    expect(full?.injectedJavaScript).toContain('"natural":true');
    expect(full?.scrollEnabled).toBe(true);
    expect(full?.domStorageEnabled).toBe(false);

    await fireEvent.press(getByLabelText("preview.close"));
    expect(queryByTestId("mermaid-full-screen-diagram")).toBeNull();
  });

  it("labels the editor button by what it does: copy, then open the editor", async () => {
    const { getByLabelText } = await render(<MermaidBlock content={ER} />);
    const button = getByLabelText("rich.mermaid_editor");
    expect(button.props.accessibilityHint).toBe("rich.mermaid_editor_hint");

    await fireEvent.press(button);
    expect(Clipboard.setStringAsync).toHaveBeenCalledWith(ER);
    expect(WebBrowser.openBrowserAsync).toHaveBeenCalledWith("https://mermaid.live/edit");
  });
});
