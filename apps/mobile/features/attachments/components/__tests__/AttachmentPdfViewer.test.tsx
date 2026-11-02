import { render, waitFor } from "@testing-library/react-native";
import { getInfoAsync, readAsStringAsync } from "expo-file-system/legacy";
import { Linking, StyleSheet } from "react-native";
import { createOnShouldStartLoadWithRequest } from "react-native-webview/lib/WebViewShared";

import { AttachmentPdfViewer } from "@/features/attachments/components/AttachmentPdfViewer";
import { MAX_ATTACHMENT_BYTES } from "@/features/attachments/model/attachmentLimits";
import { ensureLocalAttachmentFile } from "@/features/attachments/model/downloadChatAttachment";
import { lightTheme as mockLightTheme } from "@/lib/theme";
import { readVendorLibraries } from "@/lib/vendorAssets";

// One object, as the provider keeps it: a new getter per render re-runs every effect.
const mockAccountSession = { account: "user-1:0", getToken: () => "tok" };
jest.mock("@/contexts/accountSession", () => ({
  useAccountSession: () => mockAccountSession,
}));
jest.mock("@/contexts/AuthContext", () => ({
  useAuthToken: () => "tok",
}));
jest.mock("@/features/attachments/model/attachmentUri", () => ({
  resolveAttachmentUri: ({ attachmentId }: { attachmentId?: string }) => `https://api.test/attachments/${attachmentId}/file`,
}));
jest.mock("@/features/attachments/model/downloadChatAttachment", () => ({
  ensureLocalAttachmentFile: jest.fn(),
}));
jest.mock("@/lib/vendorAssets", () => ({
  readVendorLibraries: jest.fn(async () => ({ pdf: "/*pdf.js*/", pdfWorker: "/*worker*/" })),
}));
jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/",
  EncodingType: { Base64: "base64" },
  getInfoAsync: jest.fn(),
  readAsStringAsync: jest.fn(async () => "QUJD"),
}));
jest.mock("@/lib/theme", () => ({
  ...jest.requireActual("@/lib/theme"),
  useTheme: () => mockLightTheme,
}));

const mockWebViewProps: Record<string, unknown>[] = [];
jest.mock("@/lib/webView", () => ({
  ...jest.requireActual("@/lib/webView"),
  getPreviewWebView: () => ({
    mode: "rnc",
    Component: (props: Record<string, unknown>) => {
      mockWebViewProps.push(props);
      const { View: MockView } = jest.requireActual<typeof import("react-native")>("react-native");
      return <MockView testID="pdf-webview" />;
    },
  }),
}));

const lastProps = () => mockWebViewProps[mockWebViewProps.length - 1]!;

function viewer(visible: boolean) {
  return (
    <AttachmentPdfViewer visible={visible} onClose={jest.fn()} onShare={jest.fn()} attachmentId="doc" fileName="doc.pdf" />
  );
}

/** The page the WebView loads: it must be HTML handed over whole, never a file URL. */
async function shownPage(): Promise<{ html: string; props: Record<string, unknown> }> {
  const { findByTestId } = await render(viewer(true));
  await findByTestId("pdf-webview");
  const props = lastProps();
  const source = props.source as { html?: unknown; uri?: unknown };
  expect(source.uri).toBeUndefined();
  expect(typeof source.html).toBe("string");
  return { html: source.html as string, props };
}

beforeEach(() => {
  mockWebViewProps.length = 0;
  jest.mocked(readAsStringAsync).mockClear();
  jest.mocked(getInfoAsync).mockReset().mockResolvedValue({
    exists: true, isDirectory: false, size: 3, uri: "file:///cache/att-1-2-doc.pdf", modificationTime: 0,
  });
  jest.mocked(ensureLocalAttachmentFile).mockReset().mockResolvedValue("file:///cache/att-1-2-doc.pdf");
});

it("carries the cached PDF inline in its page, every page", async () => {
  const { html } = await shownPage();
  expect(ensureLocalAttachmentFile).toHaveBeenCalledWith(expect.objectContaining({
    uri: "https://api.test/attachments/doc/file", fileName: "doc.pdf", signal: expect.any(AbortSignal),
  }));
  // The bytes come from the cached file, read here, not by the page.
  expect(readAsStringAsync).toHaveBeenCalledWith("file:///cache/att-1-2-doc.pdf", { encoding: "base64" });
  expect(html).toContain('<script type="application/pdf" id="pdf-data">QUJD</script>');
  expect(html).toContain('"allPages":true');
  expect(html).not.toContain("att-1-2-doc.pdf");
  // pdf.js rides in the page too, read from its vendored asset.
  expect(readVendorLibraries).toHaveBeenCalledWith(["pdf", "pdfWorker"]);
  expect(html).toContain("/*pdf.js*/");
});

it("gives the PDF's page no file access on either platform", async () => {
  const { props } = await shownPage();
  // Android: off is react-native-webview's default; a file:// page would need it on.
  expect(props.allowFileAccess).not.toBe(true);
  expect(props.allowFileAccessFromFileURLs).toBeUndefined();
  expect(props.allowUniversalAccessFromFileURLs).toBeUndefined();
  // iOS: no read access to the cache directory, or to anything.
  expect(props.allowingReadAccessToURL).toBeUndefined();
  expect(props.injectedJavaScriptBeforeContentLoaded).toBeUndefined();
});

it("keeps the PDF's page in place: a navigation it starts loads nothing and opens nothing", async () => {
  const { props } = await shownPage();
  jest.mocked(Linking.openURL).mockClear();
  // What react-native-webview does with each navigation: a URL outside
  // originWhitelist goes to Linking.openURL, with no tap; the rest ask the guard.
  const loads: [boolean, string][] = [];
  const navigate = createOnShouldStartLoadWithRequest(
    (shouldStart, url) => loads.push([shouldStart, url]),
    props.originWhitelist as string[],
    props.onShouldStartLoadWithRequest as (request: unknown) => boolean,
  );
  const request = (url: string) =>
    ({ nativeEvent: { url, isTopFrame: true, navigationType: "other", lockIdentifier: 0 } }) as Parameters<typeof navigate>[0];

  // The page itself: iOS asks for the string-loaded document as about:blank.
  navigate(request("about:blank"));
  expect(loads).toEqual([[true, "about:blank"]]);

  const elsewhere = [
    "https://evil.example/steal",
    "http://localhost:8081/",
    "https://localhost/",
    "tel:5551234",
    "sms:5551234",
    "mailto:a@example.com",
    "recall://chat/1",
    "intent://x#Intent;end",
    "file:///etc/hosts",
    "data:text/html,hi",
    "blob:null/1",
    "javascript:alert(1)",
    "some-app:open",
    "some-app:open",
  ];
  for (const url of elsewhere) navigate(request(url));
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(Linking.openURL).not.toHaveBeenCalled();
  expect(loads.slice(1)).toEqual(elsewhere.map((url) => [false, url]));
});

it("opens no second window: on Android it would load with no guard", async () => {
  const { props } = await shownPage();
  expect(props.setSupportMultipleWindows).toBe(false);
  expect(props.allowsLinkPreview).toBe(false);
});

it("loads its page under a policy that fetches nothing: no file, no network", async () => {
  const { html } = await shownPage();
  const csp = /<meta http-equiv="Content-Security-Policy" content="([^"]*)">/.exec(html)?.[1];
  expect(csp).toBeDefined();
  expect(csp).toContain("default-src 'none'");
  expect(csp).toContain("connect-src 'none'");
  expect(csp).not.toMatch(/file:|https?:|\*/);
  // The page script reads nothing either.
  expect(html).not.toMatch(/XMLHttpRequest|fetch\(/);
});

it("does not preview a file past the upload cap: the page would hold all of it", async () => {
  jest.mocked(getInfoAsync).mockResolvedValue({
    exists: true, isDirectory: false, size: MAX_ATTACHMENT_BYTES + 1, uri: "file:///cache/att-1-2-doc.pdf", modificationTime: 0,
  });
  const { findByText, queryByTestId } = await render(viewer(true));
  await findByText("chat.pdf_preview_failed");
  expect(queryByTestId("pdf-webview")).toBeNull();
  expect(readAsStringAsync).not.toHaveBeenCalled();
});

it("lets go of the PDF when the viewer closes: opened again, it waits for a new read", async () => {
  const view = await render(viewer(true));
  await view.findByTestId("pdf-webview");
  await view.rerender(viewer(false));
  expect(view.queryByTestId("pdf-webview")).toBeNull();
  jest.mocked(readAsStringAsync).mockReturnValueOnce(new Promise(() => {}));
  await view.rerender(viewer(true));
  await waitFor(() => expect(readAsStringAsync).toHaveBeenCalledTimes(2));
  // Nothing of the last opening is kept to show.
  expect(view.queryByTestId("pdf-webview")).toBeNull();
});

it("stops the download when the viewer closes", async () => {
  jest.mocked(ensureLocalAttachmentFile).mockReturnValueOnce(new Promise(() => {}));
  const view = await render(viewer(true));
  const signal = jest.mocked(ensureLocalAttachmentFile).mock.calls[0]![0].signal!;
  expect(signal.aborted).toBe(false);
  await view.rerender(viewer(false));
  expect(signal.aborted).toBe(true);
});

it("lays the pages out across the screen: nothing above the page shrinks it", async () => {
  const { findByTestId } = await render(viewer(true));
  // react-native-webview's container takes its width from its parent's alignItems;
  // centered, it shrank to its content and the page drew 0 wide.
  let node = (await findByTestId("pdf-webview")).parent;
  while (node) {
    const align = StyleSheet.flatten(node.props.style)?.alignItems;
    expect(align === undefined || align === "stretch").toBe(true);
    node = node.parent;
  }
});
