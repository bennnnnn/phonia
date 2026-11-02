/**
 * Mermaid diagrams, charts and SMILES drawings load one shared page file per
 * kind (lib/preview/previewPageFile.ts) and hand it each block's data, instead of
 * building a page of up to 3.4 MB per block. These tests pin what the WebView
 * gets: the file, the data, and settings no looser than the inline pages had.
 */
import { act, render, waitFor } from "@testing-library/react-native";
import type { ReactElement } from "react";
import { Linking, Platform } from "react-native";

import { ChartBlock } from "@/components/rich/ChartBlock";
import { Chemistry2DView } from "@/components/rich/ChemistryBlock";
import { MermaidBlock } from "@/components/rich/MermaidBlock";
import { CHART_PAGE } from "@/lib/chartPreviewHtml";
import { SMILES_DRAWER_PAGE } from "@/lib/chemistry/smilesDrawerHtml";
import { MERMAID_PAGE } from "@/lib/mermaidPreviewHtml";
import type { PreviewPage } from "@/lib/preview/previewPage";
import {
  forgetPreviewPageFile,
  previewPageFile,
  readyPreviewPageFile,
} from "@/lib/preview/previewPageFile";

jest.mock("expo-file-system/legacy", () => ({}));
jest.mock("expo-web-browser", () => ({ openBrowserAsync: jest.fn() }));
jest.mock("@/lib/preview/previewPageFile", () => ({
  previewPageFile: jest.fn(),
  readyPreviewPageFile: jest.fn(() => null),
  forgetPreviewPageFile: jest.fn(),
}));

const mockTheme = { dark: false };
jest.mock("@/lib/theme", () => {
  const actual = jest.requireActual("@/lib/theme");
  return { ...actual, useTheme: () => (mockTheme.dark ? actual.darkTheme : actual.lightTheme) };
});

/** Every render of the preview WebView, and how many times one mounted. */
const mockWebView = { renders: [] as Record<string, unknown>[], mounts: 0 };
jest.mock("@/lib/webView", () => {
  const React = jest.requireActual<typeof import("react")>("react");
  const { View } = jest.requireActual<typeof import("react-native")>("react-native");
  function MockWebView(props: Record<string, unknown>) {
    React.useEffect(() => {
      mockWebView.mounts += 1;
    }, []);
    mockWebView.renders.push(props);
    return React.createElement(View, { testID: "preview-webview" });
  }
  return {
    ...jest.requireActual("@/lib/webView"),
    getPreviewWebView: () => ({ mode: "rnc", Component: MockWebView }),
  };
});

const lastProps = () => mockWebView.renders[mockWebView.renders.length - 1]!;

type Case = {
  page: PreviewPage;
  element: (data: string) => ReactElement;
  /** The block's data, and another to switch to. */
  data: [string, string];
  /** How the data reads inside the injected JSON. */
  inScript: (data: string) => string;
  failure: string;
  /** What the page posts when it cannot draw the data, and what the card then says. */
  drawError: [message: object, text: string];
};

const CASES: [string, Case][] = [
  [
    "a Mermaid diagram",
    {
      page: MERMAID_PAGE,
      element: (data) => <MermaidBlock content={data} />,
      data: ["graph TD; A-->B", "graph LR; X-->Y"],
      inScript: (data) => `"source":${JSON.stringify(data)}`,
      failure: "rich.mermaid_error",
      drawError: [{ kind: "mermaid-error", message: "Parse error on line 1" }, "Parse error on line 1"],
    },
  ],
  [
    "a chart",
    {
      page: CHART_PAGE,
      element: (data) => <ChartBlock content={data} />,
      data: ['{"mark":"bar","data":{"values":[{"a":1}]}}', '{"mark":"line","data":{"values":[{"a":2}]}}'],
      inScript: (data) => JSON.stringify(data),
      failure: "rich.chart_error",
      // Not Vega's message: the card says it could not draw the chart and shows its data.
      drawError: [{ kind: "chart-error", message: "Unrecognized mark" }, "rich.chart_data_instead"],
    },
  ],
  [
    "a SMILES drawing",
    {
      page: SMILES_DRAWER_PAGE,
      element: (data) => <Chemistry2DView smiles={data} fence="chemistry" />,
      data: ["CCO", "c1ccccc1"],
      inScript: (data) => `"smiles":${JSON.stringify(data)}`,
      failure: "rich.chemistry_renderer_unavailable",
      drawError: [{ kind: "chemistry-error", code: "render" }, "rich.chemistry_invalid"],
    },
  ],
];

const fileFor = (page: PreviewPage) => `file:///cache/preview-pages/${page.name}-0123456789abcdef.html`;

type Guard = (request: Record<string, unknown>) => boolean;
const guard = () => lastProps().onShouldStartLoadWithRequest as Guard;
/** The native touch system: the user's finger lands on the card (script in the page cannot do this). */
const touch = () => (lastProps().onTouchStart as (event: unknown) => void)({ nativeEvent: { timestamp: 0 } });
/** What react-native-webview 14 sends on Android: a URL, no navigation type, frame or gesture. */
const android = (url: string) => ({ url, loading: false, canGoBack: false, canGoForward: false, lockIdentifier: 1 });
/** The page posting `message` to the app. */
const post = (message: object) =>
  act(async () =>
    (lastProps().onMessage as (event: { nativeEvent: { data: string } }) => void)({
      nativeEvent: { data: JSON.stringify(message) },
    }),
  );

afterEach(() => {
  jest.restoreAllMocks();
});

beforeEach(() => {
  jest.replaceProperty(Platform, "OS", "ios");
  jest.spyOn(Linking, "openURL").mockReset().mockResolvedValue(true);
  mockWebView.renders.length = 0;
  mockWebView.mounts = 0;
  mockTheme.dark = false;
  jest.mocked(readyPreviewPageFile).mockReset().mockReturnValue(null);
  jest.mocked(forgetPreviewPageFile).mockReset();
  jest.mocked(previewPageFile).mockReset().mockImplementation(async (page) => fileFor(page));
});

describe.each(CASES)("%s", (_name, { page, element, data, inScript, failure, drawError }) => {
  const file = fileFor(page);

  it("loads its kind's page file and hands it this block's data", async () => {
    const { findByTestId } = await render(element(data[0]));
    await findByTestId("preview-webview");

    expect(previewPageFile).toHaveBeenCalledWith(page);
    const props = lastProps();
    expect(props.source).toEqual({ uri: file });
    // Handed before the page loads and again once it has (Android may run the first late).
    expect(props.injectedJavaScriptBeforeContentLoaded).toBe(props.injectedJavaScript);
    expect(props.injectedJavaScript).toContain(inScript(data[0]));
  });

  it("keeps the WebView as locked down as the inline page was", async () => {
    const { findByTestId } = await render(element(data[0]));
    await findByTestId("preview-webview");
    const props = lastProps();

    expect(props.javaScriptEnabled).toBe(true);
    expect(props.domStorageEnabled).toBe(false);
    // Android needs file access to open a file:// page; iOS reads only the page itself.
    expect(props.allowFileAccess).toBe(true);
    expect(props.allowingReadAccessToURL).toBeUndefined();
    expect(props.allowFileAccessFromFileURLs).toBeUndefined();
    expect(props.allowUniversalAccessFromFileURLs).toBeUndefined();
    expect(props.originWhitelist).toEqual(["*"]);
    // A link opens only right after the native touch system saw a finger on the card.
    expect(props.onTouchStart).toEqual(expect.any(Function));
    // No window (Android) or link preview (iOS) that loads outside the guard.
    expect(props.setSupportMultipleWindows).toBe(false);
    expect(props.allowsLinkPreview).toBe(false);

    const allow = guard();
    expect(allow({ url: file })).toBe(true);
    expect(allow({ url: "https://example.com/?leak=1" })).toBe(false);
    expect(allow({ url: "file:///cache/att-1-2-doc.pdf" })).toBe(false);
    expect(allow({ url: "about:blank" })).toBe(false);
    // What the page loads by itself never opens outside the card either.
    expect(Linking.openURL).not.toHaveBeenCalled();
  });

  it("opens a link the user taps in the card as a chat link would", async () => {
    const { findByTestId } = await render(element(data[0]));
    await findByTestId("preview-webview");

    // iOS: a tap on a link the page did not catch reaches the guard.
    touch();
    expect(guard()({ url: "javascript:alert(1)", navigationType: "click", isTopFrame: true })).toBe(false);
    expect(guard()({ url: "file:///cache/att-1-2-doc.pdf", navigationType: "click", isTopFrame: true })).toBe(false);
    expect(guard()({ url: "https://example.com/a", navigationType: "click", isTopFrame: true })).toBe(false);
    // One tap, one link.
    expect(guard()({ url: "tel:123", navigationType: "click", isTopFrame: true })).toBe(false);
    expect(Linking.openURL).toHaveBeenCalledTimes(1);
    expect(Linking.openURL).toHaveBeenCalledWith("https://example.com/a");

    // Android says nothing about what started a navigation: the touch decides.
    jest.replaceProperty(Platform, "OS", "android");
    touch();
    expect(guard()(android("https://example.com/b"))).toBe(false);
    expect(Linking.openURL).toHaveBeenCalledTimes(2);
    expect(Linking.openURL).toHaveBeenLastCalledWith("https://example.com/b");
  });

  it.each(["ios", "android"] as const)(
    "opens nothing on %s that the page's script sends it to with no finger on the card",
    async (os) => {
      jest.replaceProperty(Platform, "OS", os);
      const { findByTestId } = await render(element(data[0]));
      await findByTestId("preview-webview");

      for (const url of ["tel:+19005550100", "sms:+15550100?body=hi", "https://evil.example/phish"]) {
        // location = "…" (Android reports nothing), or a link script made and clicked (iOS says "click").
        expect(guard()(os === "ios" ? { url, navigationType: "click", isTopFrame: true } : android(url))).toBe(false);
        // window.open, or a link message the script posted itself.
        await post({ kind: "preview-link", url });
      }
      expect(Linking.openURL).not.toHaveBeenCalled();
    },
  );

  it("opens the links the page hands over and leaves the rest of its messages to the card", async () => {
    const { findByTestId, findByText, queryByTestId } = await render(element(data[0]));
    await findByTestId("preview-webview");

    touch();
    await post({ kind: "preview-link", url: "javascript:alert(1)" });
    await post({ kind: "preview-link", url: "recall://chat/1" });
    await post({ kind: "preview-link", url: "https://example.com/b" });
    await post({ kind: "preview-link", url: "https://example.com/c" });
    expect(Linking.openURL).toHaveBeenCalledTimes(1);
    expect(Linking.openURL).toHaveBeenCalledWith("https://example.com/b");
    expect(queryByTestId("preview-webview")).toBeTruthy();

    await post(drawError[0]);
    expect(await findByText(drawError[1])).toBeTruthy();
    expect(Linking.openURL).toHaveBeenCalledTimes(1);
  });

  it("waits for the page file before mounting a WebView", async () => {
    let finish: (uri: string) => void = () => undefined;
    jest.mocked(previewPageFile).mockReturnValue(new Promise((resolve) => (finish = resolve)));
    const { queryByTestId, findByTestId } = await render(element(data[0]));
    expect(queryByTestId("preview-webview")).toBeNull();

    await act(async () => finish(file));
    expect(await findByTestId("preview-webview")).toBeTruthy();
  });

  it("mounts at once on a page file this run already has", async () => {
    jest.mocked(readyPreviewPageFile).mockReturnValue(file);
    const { findByTestId } = await render(element(data[0]));
    await findByTestId("preview-webview");
    expect(previewPageFile).not.toHaveBeenCalled();
    expect(lastProps().source).toEqual({ uri: file });
  });

  it("says so when the page file cannot be written", async () => {
    jest.mocked(previewPageFile).mockRejectedValue(new Error("Storage unavailable."));
    const { findByText, queryByTestId } = await render(element(data[0]));
    expect(await findByText(failure)).toBeTruthy();
    expect(queryByTestId("preview-webview")).toBeNull();
  });

  it("writes the page file again when the WebView cannot load it, once", async () => {
    const { findByTestId, findByText, queryByText } = await render(element(data[0]));
    await findByTestId("preview-webview");
    expect(mockWebView.mounts).toBe(1);

    // The system cleared the cache: the file is written again and loads in a fresh WebView.
    await act(async () => (lastProps().onError as () => void)());
    expect(forgetPreviewPageFile).toHaveBeenCalledWith(page, file);
    await waitFor(() => expect(mockWebView.mounts).toBe(2));
    expect(previewPageFile).toHaveBeenCalledTimes(2);
    expect(lastProps().source).toEqual({ uri: file });
    expect(queryByText(failure)).toBeNull();

    // It failed again: the card says so instead of trying forever.
    await act(async () => (lastProps().onError as () => void)());
    expect(forgetPreviewPageFile).toHaveBeenCalledTimes(2);
    expect(await findByText(failure)).toBeTruthy();
    expect(previewPageFile).toHaveBeenCalledTimes(2);
  });

  it("writes again a page file this run had at once, when the WebView cannot load it", async () => {
    jest.mocked(readyPreviewPageFile).mockReturnValue(file);
    const { findByTestId } = await render(element(data[0]));
    await findByTestId("preview-webview");

    await act(async () => (lastProps().onError as () => void)());
    expect(forgetPreviewPageFile).toHaveBeenCalledWith(page, file);
    await waitFor(() => expect(mockWebView.mounts).toBe(2));
    expect(previewPageFile).toHaveBeenCalledWith(page);
  });

  it("starts a fresh WebView on the same file for new data or a new theme", async () => {
    const view = await render(element(data[0]));
    await view.findByTestId("preview-webview");
    expect(mockWebView.mounts).toBe(1);

    await view.rerender(element(data[1]));
    await waitFor(() => expect(mockWebView.mounts).toBe(2));
    expect(lastProps().injectedJavaScript).toContain(inScript(data[1]));

    mockTheme.dark = true;
    await view.rerender(element(data[1]));
    await waitFor(() => expect(mockWebView.mounts).toBe(3));
    expect(lastProps().source).toEqual({ uri: file });
    expect(previewPageFile).toHaveBeenCalledTimes(1);
  });
});
