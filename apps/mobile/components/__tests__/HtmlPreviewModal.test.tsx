import { render } from "@testing-library/react-native";

import { HtmlPreviewModal } from "@/components/HtmlPreviewModal";

// Same guard pattern as MermaidBlock.test.tsx —
// without either WebView backend linked, the Run tab must fall back to the
// static renderer.
jest.mock("react-native-webview", () => {
  throw new Error("react-native-webview native module is not linked (test)");
});
jest.mock("@expo/dom-webview", () => {
  throw new Error("@expo/dom-webview native module is not linked (test)");
});

// openHtmlPreview.ts (Share action) pulls in expo-file-system, which wraps a
// native module this plain jest-preset environment doesn't stub.
jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/",
  writeAsStringAsync: jest.fn(),
  EncodingType: { UTF8: "utf8" },
}));

// expo-web-browser is a native module this plain jest-preset environment doesn't stub.
jest.mock("expo-web-browser", () => ({
  openBrowserAsync: jest.fn(),
}));

// A settings-style demo page: a decorative gear icon sits in static markup,
// but the actual content only exists inside the <script> that populates
// #app — the same shape a model emits for a "live" JS-driven page.
const SCRIPT_DRIVEN_HTML = `<!DOCTYPE html>
<html>
<head><style>.fab{position:fixed;top:16px;right:16px}</style></head>
<body>
  <div class="fab">⚙️</div>
  <div id="app"></div>
  <script>document.getElementById('app').innerHTML = '<h1>Hello</h1><p>Real content</p>';</script>
</body>
</html>`;

describe("HtmlPreviewModal static fallback (no dev-build WebView linked)", () => {
  it("shows the live-preview hint instead of the lone decorative icon left after stripping <script>/<style>", async () => {
    // RTL v14 made render() async (it now drives an async act() internally).
    const { getByText, queryByText } = await render(
      <HtmlPreviewModal visible html={SCRIPT_DRIVEN_HTML} onClose={() => {}} />,
    );

    expect(getByText(/needs a live browser preview/i)).toBeOnTheScreen();
    // The real content only ever existed inside the stripped <script> — it must not leak through,
    // and the page must not silently render as just the icon with everything else missing.
    expect(queryByText("Hello")).toBeNull();
  });

  it("still renders markup that has real static content", async () => {
    const { getByText } = await render(
      <HtmlPreviewModal visible html="<p>Plain paragraph</p>" onClose={() => {}} />,
    );

    expect(getByText("Plain paragraph")).toBeOnTheScreen();
  });
});
