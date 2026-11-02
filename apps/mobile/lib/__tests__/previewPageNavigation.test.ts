import { createPreviewTapGate, PREVIEW_TAP_WINDOW_MS } from "@/lib/preview/previewTap";
import {
  allowPreviewPageNavigation,
  PREVIEW_PAGE_ORIGIN_WHITELIST,
  previewPageLinkToOpen,
  previewPagePostedLinkToOpen,
} from "@/lib/webView";

const mockPlatform = { OS: "ios" };
jest.mock("react-native", () => ({
  NativeModules: {},
  TurboModuleRegistry: { get: () => null },
  Linking: { openURL: jest.fn() },
  get Platform() {
    return mockPlatform;
  },
}));

const CACHES = "file:///var/mobile/Containers/Data/Application/A1/Library/Caches";
const PAGE = `${CACHES}/preview-pages/mermaid-3b2f6a9c41d0e1f2.html`;

describe("preview page navigation", () => {
  it("lets every URL reach the guard so nothing is handed to the OS", () => {
    // A URL that misses originWhitelist goes to Linking.openURL; "*" means
    // the guard below decides, and a refusal opens nothing.
    expect(PREVIEW_PAGE_ORIGIN_WHITELIST).toEqual(["*"]);
  });

  it.each([
    ["the page itself", PAGE],
    ["the page as iOS reports it", PAGE.replace("file:///var/", "file:///private/var/")],
    ["the page with a fragment", `${PAGE}#diagram`],
    ["the page spelled with escapes", PAGE.replace("preview-pages", "preview%2Dpages")],
  ])("loads %s", (_name, url) => {
    expect(allowPreviewPageNavigation(PAGE, { url })).toBe(true);
    expect(allowPreviewPageNavigation(PAGE, { nativeEvent: { url } })).toBe(true);
  });

  it("lets a subframe go blank, never the card itself", () => {
    expect(allowPreviewPageNavigation(PAGE, { url: "about:blank", isTopFrame: false })).toBe(true);
    expect(allowPreviewPageNavigation(PAGE, { url: "about:blank", isTopFrame: true })).toBe(false);
    expect(allowPreviewPageNavigation(PAGE, { url: "about:blank" })).toBe(false);
  });

  it.each([
    // A link in a chart (Vega href), a diagram or page script.
    ["a web page", "https://example.com/track?memory=1"],
    ["plain http", "http://localhost/"],
    ["another cached file", `${CACHES}/att-1-2-doc.pdf`],
    ["another preview page", PAGE.replace("mermaid-3b2f6a9c41d0e1f2", "chart-0123456789abcdef")],
    ["a page of that name elsewhere", PAGE.replace("/A1/", "/B2/")],
    ["app data", "file:///data/user/0/com.recall.app/files/session.json"],
    ["a data document", "data:text/html,<script>alert(1)</script>"],
    ["an app link", "recall://chat/1"],
    ["a script URL", "javascript:alert(1)"],
    ["nothing", ""],
  ])("refuses %s", (_name, url) => {
    expect(allowPreviewPageNavigation(PAGE, { url })).toBe(false);
  });
});

/** A tap gate on a clock the test moves. */
function tapGate() {
  let now = 1_000_000;
  const gate = createPreviewTapGate(() => now);
  return {
    gate,
    /** The finger lands on the WebView (its onTouchStart). */
    touch: () => gate.touched(),
    wait: (ms: number) => {
      now += ms;
    },
  };
}

/** What react-native-webview 14 sends on Android: no navigation type, no frame, no gesture. */
const android = (url: string, extra: Record<string, unknown> = {}) => ({
  url,
  loading: false,
  title: "",
  canGoBack: false,
  canGoForward: false,
  lockIdentifier: 1,
  ...extra,
});

describe("previewPageLinkToOpen", () => {
  beforeEach(() => {
    mockPlatform.OS = "ios";
  });

  it("opens a link the user tapped on iOS, as a chat link would", () => {
    const { gate, touch } = tapGate();
    touch();
    expect(
      previewPageLinkToOpen({ url: "https://example.com/a", navigationType: "click", isTopFrame: true }, gate),
    ).toBe("https://example.com/a");
    touch();
    expect(previewPageLinkToOpen({ nativeEvent: { url: "mailto:a@b.test", navigationType: "click" } }, gate)).toBe(
      "mailto:a@b.test",
    );
  });

  it("opens nothing on iOS that a link activation did not start", () => {
    const { gate, touch } = tapGate();
    touch();
    expect(previewPageLinkToOpen({ url: "https://example.com", navigationType: "other" }, gate)).toBeNull();
    // No navigation type at all: fail closed.
    expect(previewPageLinkToOpen({ url: "https://example.com" }, gate)).toBeNull();
  });

  it("opens nothing on iOS for a link script clicked with no finger on the card", () => {
    // WebKit reports a script's a.click() as "click" too.
    const { gate } = tapGate();
    expect(previewPageLinkToOpen({ url: "tel:+19005550100", navigationType: "click", isTopFrame: true }, gate)).toBeNull();
  });

  it("opens a link on Android right after the user touched the card", () => {
    mockPlatform.OS = "android";
    const { gate, touch, wait } = tapGate();
    touch();
    wait(180);
    expect(previewPageLinkToOpen(android("https://example.com/b"), gate)).toBe("https://example.com/b");
  });

  it.each([
    ["the dialer", "tel:+19005550100"],
    ["Messages", "sms:+15550100?body=hi"],
    ["a web page", "https://example.com/track?memory=1"],
    ["mail", "mailto:someone@example.com"],
  ])("opens nothing on Android when script sends the page to %s with no touch", (_name, url) => {
    // location = "tel:…" from a diagram, chart or drawing's script: Android says nothing about it.
    mockPlatform.OS = "android";
    const { gate } = tapGate();
    expect(previewPageLinkToOpen(android(url), gate)).toBeNull();
    expect(previewPageLinkToOpen({ nativeEvent: android(url) }, gate)).toBeNull();
  });

  it("opens nothing once the touch is old", () => {
    mockPlatform.OS = "android";
    const { gate, touch, wait } = tapGate();
    touch();
    wait(PREVIEW_TAP_WINDOW_MS + 1);
    expect(previewPageLinkToOpen(android("tel:123"), gate)).toBeNull();
  });

  it("opens one link per touch", () => {
    mockPlatform.OS = "android";
    const { gate, touch } = tapGate();
    touch();
    expect(previewPageLinkToOpen(android("https://example.com/one"), gate)).toBe("https://example.com/one");
    expect(previewPageLinkToOpen(android("tel:123"), gate)).toBeNull();
    expect(previewPagePostedLinkToOpen("sms:123", gate)).toBeNull();
  });

  it("opens nothing on Android for a request that says it was a redirect or had no gesture", () => {
    mockPlatform.OS = "android";
    const { gate, touch } = tapGate();
    touch();
    expect(previewPageLinkToOpen(android("https://example.com", { hasGesture: true, isRedirect: true }), gate)).toBeNull();
    expect(previewPageLinkToOpen(android("https://example.com", { hasGesture: false }), gate)).toBeNull();
    // Neither spent the touch.
    expect(previewPageLinkToOpen(android("https://example.com", { hasGesture: true, isRedirect: false }), gate)).toBe(
      "https://example.com",
    );
  });

  it("opens nothing for a subframe", () => {
    const { gate, touch } = tapGate();
    touch();
    expect(
      previewPageLinkToOpen({ url: "https://example.com", navigationType: "click", isTopFrame: false }, gate),
    ).toBeNull();
  });

  it.each([
    ["no request", undefined],
    ["a request with no URL", { navigationType: "click" }],
    ["a URL that is not text", { url: 42, navigationType: "click" }],
  ])("opens nothing for %s", (_name, request) => {
    const { gate, touch } = tapGate();
    touch();
    expect(previewPageLinkToOpen(request, gate)).toBeNull();
    mockPlatform.OS = "android";
    expect(previewPageLinkToOpen(request, gate)).toBeNull();
  });

  it.each([
    ["an Android intent", "intent://scan/#Intent;scheme=zxing;end"],
    ["a cached file", `${CACHES}/att-1-2-doc.pdf`],
    ["app data", "file:///data/user/0/com.recall.app/files/session.json"],
    ["an app link", "recall://chat/1"],
    ["a data document", "data:text/html,hi"],
    ["a script URL", "javascript:alert(1)"],
    ["a relative path", "secrets.json"],
  ])("never opens %s, even right after a tap", (_name, url) => {
    const { gate, touch } = tapGate();
    touch();
    expect(previewPageLinkToOpen({ url, navigationType: "click" }, gate)).toBeNull();
    mockPlatform.OS = "android";
    expect(previewPageLinkToOpen(android(url), gate)).toBeNull();
    expect(previewPagePostedLinkToOpen(url, gate)).toBeNull();
    // A refused URL leaves the touch for the link the user meant.
    expect(previewPagePostedLinkToOpen("https://example.com", gate)).toBe("https://example.com");
  });
});

describe("previewPagePostedLinkToOpen", () => {
  it("opens a link the page posted right after a touch", () => {
    const { gate, touch } = tapGate();
    touch();
    expect(previewPagePostedLinkToOpen(" https://example.com/a ", gate)).toBe("https://example.com/a");
  });

  it.each(["tel:+19005550100", "https://example.com/editor", "sms:+15550100"])(
    "opens nothing the page posts with no touch (window.open, a forged message): %s",
    (url) => {
      const { gate } = tapGate();
      expect(previewPagePostedLinkToOpen(url, gate)).toBeNull();
    },
  );
});

describe("createPreviewTapGate", () => {
  it("claims nothing before a touch", () => {
    const { gate } = tapGate();
    expect(gate.claim()).toBe(false);
  });

  it("claims a touch up to the end of its window, once", () => {
    const { gate, touch, wait } = tapGate();
    touch();
    wait(PREVIEW_TAP_WINDOW_MS);
    expect(gate.claim()).toBe(true);
    expect(gate.claim()).toBe(false);
  });

  it("claims nothing when the clock went back", () => {
    const { gate, touch, wait } = tapGate();
    touch();
    wait(-1);
    expect(gate.claim()).toBe(false);
  });
});
