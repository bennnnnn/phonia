import { allowHtmlRunNavigation, HTML_RUN_ORIGIN_WHITELIST } from "@/lib/webView";

jest.mock("react-native", () => ({
  NativeModules: {},
  TurboModuleRegistry: { get: () => null },
}));

// Anyone can publish a page to these hosts (npm, GitHub through jsDelivr).
const CDN_PAGE = "https://cdn.jsdelivr.net/gh/someone/demo@1.0.0/signin.html";

describe("HTML Run navigation", () => {
  it("lets every URL reach the guard so nothing is handed to the OS", () => {
    // A URL that misses originWhitelist goes to Linking.openURL; "*" means
    // the guard below decides, and a refusal opens nothing.
    expect(HTML_RUN_ORIGIN_WHITELIST).toEqual(["*"]);
  });

  it.each<[string, Record<string, unknown>]>([
    ["the wrapper page (source.html with no baseUrl)", { url: "about:blank", isTopFrame: true }],
    ["the sandboxed page frame", { url: "about:srcdoc", isTopFrame: false }],
    ["a #link inside the page frame", { url: "about:srcdoc#results", isTopFrame: false }],
    ["a blank frame a library makes", { url: "about:blank", isTopFrame: false }],
    ["WebKit's name for a string-loaded page", { url: "applewebdata://6F1C2A/", isTopFrame: true }],
    ["the native event shape", { nativeEvent: { url: "about:blank", isTopFrame: true } }],
  ])("keeps %s", (_label, request) => {
    expect(allowHtmlRunNavigation(request)).toBe(true);
  });

  it.each<[string, Record<string, unknown>]>([
    // `location.href = …` in the page: iOS reports the main frame.
    ["a CDN page in the top frame", { url: CDN_PAGE, isTopFrame: true, navigationType: "other" }],
    // iOS asks about subframes; Android never sends their http(s) navigations
    // (the wrapper's frame-src stops those, see htmlRunDocument.test.ts).
    ["a CDN page in a subframe", { url: CDN_PAGE, isTopFrame: false }],
    // Android's event carries no frame flag at all.
    ["a CDN page with no frame flag", { url: "https://unpkg.com/some-pkg@1.0.0/index.html" }],
    ["a CDN page in the native event shape", { nativeEvent: { url: CDN_PAGE, isTopFrame: true } }],
    ["a CDN stylesheet URL", { url: "https://fonts.googleapis.com/css2?family=Inter" }],
    ["a CDN look-alike host", { url: "https://cdn.jsdelivr.net.evil.example/signin.html" }],
    ["plain-http CDN", { url: "http://cdn.jsdelivr.net/npm/x.js" }],
    ["the old https://localhost/ base URL", { url: "https://localhost/" }],
    ["a local dev server", { url: "http://127.0.0.1:8081/" }],
    ["javascript:", { url: "javascript:alert(document.cookie)" }],
    ["data:", { url: "data:text/html,<h1>hi</h1>" }],
    ["file:", { url: "file:///etc/hosts" }],
    ["intent:", { url: "intent://scan/#Intent;scheme=zxing;end" }],
    ["blob:", { url: "blob:null/0b6e7c1f" }],
    ["another about: page", { url: "about:srcdoc.evil" }],
    ["tel:", { url: "tel:+19005550100" }],
    ["sms:", { url: "sms:+15550100?body=hi" }],
    ["mailto:", { url: "mailto:someone@example.com" }],
    ["an app deep link", { url: "recall://settings/data-controls" }],
    ["an empty URL", { url: "" }],
    ["no request", {}],
  ])("refuses %s without opening it anywhere", (_label, request) => {
    expect(allowHtmlRunNavigation(request)).toBe(false);
  });
});
