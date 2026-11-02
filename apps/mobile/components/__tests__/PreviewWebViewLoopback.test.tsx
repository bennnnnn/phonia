import { render } from "@testing-library/react-native";
// react-native-webview's own gate: a URL that misses originWhitelist is handed
// to Linking.openURL; one that passes goes to onShouldStartLoadWithRequest.
import { createOnShouldStartLoadWithRequest } from "react-native-webview/lib/WebViewShared";

import { HtmlPreviewModal } from "@/components/HtmlPreviewModal";
import { INLINE_DOCUMENT_URL, LOOPBACK_URLS } from "@/lib/__tests__/fixtures/loopbackUrls";
import {
  allowPdfPageNavigation,
  allowPreviewPageNavigation,
  PDF_PAGE_ORIGIN_WHITELIST,
  PREVIEW_PAGE_ORIGIN_WHITELIST,
} from "@/lib/webView";

// A preview page could reach a server on the phone itself (a dev server,
// another app's local server) in its own frame, with the ReactNativeWebView
// bridge: every preview took any localhost or 127.0.0.1 URL as its inline
// document. And the Run tab let an HTTPS page load http: content on Android.
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

type Decide = (request: unknown) => boolean;

const PAGE_FILE = "file:///var/mobile/cache/preview-pages/mermaid-abc.html";

async function runTabProps(): Promise<Record<string, unknown>> {
  mockWebViewProps.length = 0;
  await render(<HtmlPreviewModal visible html="<p>hi</p>" onClose={() => {}} />);
  return mockWebViewProps[mockWebViewProps.length - 1];
}

/** Whether react-native-webview would load `url` in the preview's own frame. */
function loadsInFrame(originWhitelist: string[], decide: Decide, url: string): boolean {
  const loadRequest = jest.fn();
  const gate = createOnShouldStartLoadWithRequest(loadRequest, originWhitelist, decide);
  gate({
    nativeEvent: {
      url,
      lockIdentifier: 1,
      isTopFrame: true,
      navigationType: "other",
    },
  } as unknown as Parameters<typeof gate>[0]);
  expect(loadRequest).toHaveBeenCalledTimes(1);
  return loadRequest.mock.calls[0][0] === true;
}

async function previewWebViews(): Promise<[string, string[], Decide][]> {
  const run = await runTabProps();
  return [
    ["the HTML Run tab", run.originWhitelist as string[], run.onShouldStartLoadWithRequest as Decide],
    // The whitelist and guard the PDF card and viewer pass to their WebView.
    ["an inline PDF preview", PDF_PAGE_ORIGIN_WHITELIST, allowPdfPageNavigation],
    [
      "a diagram, chart or molecule page",
      PREVIEW_PAGE_ORIGIN_WHITELIST,
      (request) => allowPreviewPageNavigation(PAGE_FILE, request),
    ],
  ];
}

describe("preview WebViews and servers on the phone", () => {
  it("leaves Android's mixed-content mode at never in the Run tab", async () => {
    const props = await runTabProps();
    expect(props.mixedContentMode).toBeUndefined();
  });

  it("still loads each inline preview's own document", async () => {
    const [run, pdf] = await previewWebViews();
    for (const [, whitelist, decide] of [run, pdf]) {
      expect(loadsInFrame(whitelist, decide, INLINE_DOCUMENT_URL)).toBe(true);
    }
  });

  it.each(LOOPBACK_URLS)("loads %s in no preview", async (url) => {
    for (const [name, whitelist, decide] of await previewWebViews()) {
      expect([name, loadsInFrame(whitelist, decide, url)]).toEqual([name, false]);
    }
  });
});
