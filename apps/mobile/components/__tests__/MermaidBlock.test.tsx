// Proof-of-pattern component test for the WebView-gated preview components:
// when the native preview WebView isn't linked, MermaidBlock must render its
// documented static-source fallback instead of crashing. See lib/webView.ts
// (getPreviewWebView) for the detection/fallback chain this exercises.
//
// Imports come first (ESLint import/first) — jest.mock calls below are still
// hoisted above them at execution time by babel-plugin-jest-hoist, so mock
// registration order relative to these imports is unaffected.
import { render } from "@testing-library/react-native";

import { MermaidBlock } from "@/components/rich/MermaidBlock";

// react-native-webview and @expo/dom-webview are the two require() calls
// getPreviewWebView() falls through in turn; forcing both to throw is how a
// real device without either native module linked (e.g. Expo Go) behaves
// from getPreviewWebView()'s point of view, so this keeps the guard's own
// fallback logic under real test rather than stubbing lib/webView.ts itself.
jest.mock("react-native-webview", () => {
  throw new Error("react-native-webview native module is not linked (test)");
});
jest.mock("@expo/dom-webview", () => {
  throw new Error("@expo/dom-webview native module is not linked (test)");
});

// expo-web-browser wraps a native module that this test's plain
// @react-native/jest-preset environment (no jest-expo) doesn't stub.
// MermaidBlock only calls it from a button-press handler, not during
// render, so a no-op fake is enough to keep import-time safe.
jest.mock("expo-web-browser", () => ({
  openBrowserAsync: jest.fn(),
}));

// The diagram page is a file the block reads from expo-file-system, whose
// native module cannot load here; with no preview WebView it is never written.
jest.mock("expo-file-system/legacy", () => ({}));

describe("MermaidBlock", () => {
  it("renders the static source fallback when no preview WebView is available", async () => {
    const content = "graph TD; A-->B;";

    // RTL v14 made render() async (it now drives an async act() internally).
    const { getByText } = await render(<MermaidBlock content={content} />);

    expect(getByText(content)).toBeOnTheScreen();
    expect(getByText("rich.mermaid_dev_build")).toBeOnTheScreen();
  });
});
