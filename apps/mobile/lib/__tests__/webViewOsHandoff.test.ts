/**
 * react-native-webview opens any URL that misses a WebView's `originWhitelist`
 * with `Linking.openURL`, before the app's own navigation guard is asked and
 * with no tap from the user. These run the library's own handler with each
 * preview's whitelist, so a page's script navigation never reaches the OS.
 */
import { allowHtmlRunNavigation, HTML_RUN_ORIGIN_WHITELIST, PREVIEW_PAGE_ORIGIN_WHITELIST } from "@/lib/webView";

const mockLinking = {
  openURL: jest.fn(() => Promise.resolve()),
  canOpenURL: jest.fn(() => Promise.resolve(true)),
};
jest.mock("react-native", () => ({
  NativeModules: {},
  TurboModuleRegistry: { get: () => null },
  Platform: { OS: "android" },
  StyleSheet: { create: <T>(styles: T) => styles },
  View: "View",
  Text: "Text",
  ActivityIndicator: "ActivityIndicator",
  get Linking() {
    return mockLinking;
  },
}));

type ShouldStart = (event: { nativeEvent: { url: string; lockIdentifier: number } }) => void;
type CreateHandler = (
  loadRequest: (shouldStart: boolean, url: string, lockIdentifier: number) => void,
  originWhitelist: readonly string[],
  onShouldStartLoadWithRequest?: (request: { url: string }) => boolean,
) => ShouldStart;

// The library's own handler, the one every WebView's navigations go through.
// eslint-disable-next-line @typescript-eslint/no-require-imports -- the library's compiled CommonJS, loaded after the react-native mock
const { createOnShouldStartLoadWithRequest } = require("react-native-webview/lib/WebViewShared") as {
  createOnShouldStartLoadWithRequest: CreateHandler;
};

/** Each preview WebView: its whitelist and a guard that says no to a page leaving (it opens nothing itself). */
const SURFACES: [string, readonly string[], (request: { url: string }) => boolean][] = [
  ["a diagram, chart or drawing card", PREVIEW_PAGE_ORIGIN_WHITELIST, () => false],
  ["the HTML Run tab", HTML_RUN_ORIGIN_WHITELIST, allowHtmlRunNavigation],
];

const SCRIPT_NAVIGATIONS = [
  "tel:+19005550100",
  "sms:+15550100?body=hi",
  "https://evil.example/phish",
  "intent://scan/#Intent;scheme=zxing;end",
  "recall://settings/data-controls",
  "mailto:someone@example.com",
];

describe("preview WebViews hand no navigation to the OS", () => {
  beforeEach(() => {
    mockLinking.openURL.mockClear();
    mockLinking.canOpenURL.mockClear();
  });

  const cases = SURFACES.flatMap(([name, whitelist, guard]) =>
    SCRIPT_NAVIGATIONS.map((url) => [name, url, whitelist, guard] as const),
  );

  it.each(cases)(
    "%s: a page's script sending it to %s opens nothing",
    (_name, url, whitelist, guard) => {
      const asked: string[] = [];
      const decided: boolean[] = [];
      const handler = createOnShouldStartLoadWithRequest(
        (shouldStart) => decided.push(shouldStart),
        whitelist,
        (request) => {
          asked.push(request.url);
          return guard(request);
        },
      );
      handler({ nativeEvent: { url, lockIdentifier: 1 } });
      expect(mockLinking.canOpenURL).not.toHaveBeenCalled();
      expect(mockLinking.openURL).not.toHaveBeenCalled();
      // The app's guard decided it.
      expect(asked).toEqual([url]);
      expect(decided).toHaveLength(1);
    },
  );
});
