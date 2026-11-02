import { act, render } from "@testing-library/react-native";

import { HtmlPreviewModal } from "@/components/HtmlPreviewModal";

// The Run tab executes model-written JavaScript. A reply that sets
// `location` or calls `window.open` must stay inside the sandbox: with no
// guard, react-native-webview opened any URL outside originWhitelist through
// Linking.openURL (Safari, the dialer, a deep link into the app).
const mockWebViewProps: Record<string, unknown>[] = [];

jest.mock("@/lib/webView", () => {
  const actual = jest.requireActual("@/lib/webView");
  const { View } = jest.requireActual("react-native");
  const FakeWebView = (props: Record<string, unknown>) => {
    mockWebViewProps.push(props);
    return <View testID="run-webview" />;
  };
  return {
    ...actual,
    getPreviewWebView: () => ({ Component: FakeWebView, mode: "rnc" }),
  };
});
jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/",
  writeAsStringAsync: jest.fn(),
  EncodingType: { UTF8: "utf8" },
}));
jest.mock("expo-web-browser", () => ({ openBrowserAsync: jest.fn() }));

const HOSTILE_HTML = `<!DOCTYPE html><html><head></head><body>
<script>location = "https://accounts-google.example/signin";</script>
</body></html>`;

describe("HtmlPreviewModal Run tab navigation", () => {
  it("decides every navigation itself and refuses to leave the preview", async () => {
    mockWebViewProps.length = 0;
    const { getByTestId } = await render(
      <HtmlPreviewModal visible html={HOSTILE_HTML} onClose={() => {}} />,
    );
    expect(getByTestId("run-webview")).toBeOnTheScreen();

    const props = mockWebViewProps[mockWebViewProps.length - 1];
    expect(props.originWhitelist).toEqual(["*"]);
    const decide = props.onShouldStartLoadWithRequest as (request: unknown) => boolean;
    expect(typeof decide).toBe("function");
    expect(decide({ url: "about:blank", isTopFrame: true })).toBe(true);
    expect(decide({ url: "about:srcdoc", isTopFrame: false })).toBe(true);
    // CDN scripts, styles and images never come through here; a CDN URL that
    // does is page script replacing the preview with a page anyone can publish.
    const cdnPage = "https://cdn.jsdelivr.net/gh/someone/demo@1.0.0/signin.html";
    expect(decide({ url: cdnPage, isTopFrame: true })).toBe(false);
    expect(decide({ url: cdnPage, isTopFrame: false })).toBe(false);
    expect(decide({ url: "https://accounts-google.example/signin", isTopFrame: true })).toBe(
      false,
    );
    expect(decide({ url: "tel:+19005550100", isTopFrame: true })).toBe(false);
    expect(decide({ url: "recall://settings", isTopFrame: true })).toBe(false);
  });

  it("runs the page in a sandboxed frame and opens no second window", async () => {
    mockWebViewProps.length = 0;
    await render(<HtmlPreviewModal visible html={HOSTILE_HTML} onClose={() => {}} />);

    const props = mockWebViewProps[mockWebViewProps.length - 1];
    const html = (props.source as { html: string }).html;
    // The page's script lives only inside the frame's srcdoc.
    expect(html).toMatch(/^<!DOCTYPE html>[\s\S]*<iframe sandbox="allow-scripts[^"]*" srcdoc="/);
    expect(html.replace(/srcdoc="[^"]*"/, "")).not.toContain("accounts-google.example");
    expect(props.setSupportMultipleWindows).toBe(false);
    expect(props.onOpenWindow).toBeUndefined();
  });

  it("does nothing with a message from the page but show the empty hint", async () => {
    // Every frame can post to the app (iOS registers the handler for all
    // frames, Android's listener matches every origin), so a page can forge one.
    mockWebViewProps.length = 0;
    const { queryByText } = await render(
      <HtmlPreviewModal visible html={HOSTILE_HTML} onClose={() => {}} />,
    );
    const onMessage = mockWebViewProps[mockWebViewProps.length - 1].onMessage as (event: {
      nativeEvent: { data: string };
    }) => void;
    // i18n is not set up here, so the overlay shows its key.
    const empty = "preview.empty_sandbox";
    for (const data of [
      "not json",
      JSON.stringify({ kind: "navigate", url: "https://cdn.jsdelivr.net/x.html" }),
      JSON.stringify(null),
    ]) {
      await act(async () => onMessage({ nativeEvent: { data } }));
    }
    expect(queryByText(empty)).toBeNull();
    await act(async () => onMessage({ nativeEvent: { data: JSON.stringify({ kind: "preview-empty" }) } }));
    expect(queryByText(empty)).not.toBeNull();
  });
});
