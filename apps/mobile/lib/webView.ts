import { NativeModules, Platform, TurboModuleRegistry } from "react-native";
import type { ComponentType } from "react";

import { isAllowedLinkUrl } from "@/lib/linkSchemePolicy";
import type { PreviewTapGate } from "@/lib/preview/previewTap";

type PreviewWebViewMode = "rnc" | "expo-dom";

type PreviewWebViewResult = {
  Component: ComponentType<Record<string, unknown>>;
  mode: PreviewWebViewMode;
};

let cachedPreviewWebView: PreviewWebViewResult | null | undefined;

function isRncWebViewLinked(): boolean {
  try {
    if (TurboModuleRegistry.get("RNCWebViewModule") != null) {
      return true;
    }
  } catch {
    /* ignore */
  }
  return Boolean(
    NativeModules.RNCWebViewModule ??
      (NativeModules as Record<string, unknown>).RNCWebView,
  );
}

/** Prefer react-native-webview, then (development builds only) @expo/dom-webview. */
export function getPreviewWebView(): PreviewWebViewResult | null {
  if (cachedPreviewWebView !== undefined) return cachedPreviewWebView;

  if (isRncWebViewLinked()) {
    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports -- only once the native module is linked; Expo Go has none
      const Component = require("react-native-webview").WebView as ComponentType<
        Record<string, unknown>
      >;
      cachedPreviewWebView = { Component, mode: "rnc" };
      return cachedPreviewWebView;
    } catch {
      /* fall through */
    }
  }

  // Expo Go lacks react-native-webview; every build of the app links it, so a
  // production bundle leaves this fallback out (code-health audit DEAD-08). Plain
  // Node (the lib tests) has no __DEV__.
  if (typeof __DEV__ !== "undefined" && __DEV__) {
    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports -- development only, so production bundles leave it out
      const Component = require("@expo/dom-webview").WebView as ComponentType<
        Record<string, unknown>
      >;
      if (Component) {
        cachedPreviewWebView = { Component, mode: "expo-dom" };
        return cachedPreviewWebView;
      }
    } catch {
      /* not available */
    }
  }

  cachedPreviewWebView = null;
  return null;
}

/**
 * HTML Run passes every navigation to {@link allowHtmlRunNavigation}.
 *
 * react-native-webview hands any URL that misses `originWhitelist` to
 * `Linking.openURL` — Safari, the dialer, Messages, or a deep link into
 * Recall — with no tap from the user. The Run tab executes model-written
 * JavaScript, so `location = "https://…"` in a reply opened a page outside
 * the app. Matching everything here leaves the decision to the guard, which
 * blocks without opening anything.
 */
export const HTML_RUN_ORIGIN_WHITELIST: string[] = ["*"];

/**
 * The Run tab's own documents (lib/preview/htmlRunDocument.ts): the wrapper, which
 * `source={{ html }}` with no baseUrl loads at about:blank (RNCWebViewImpl.m
 * visitSource on iOS; Android loads it without asking), and the page's
 * sandboxed frame.
 */
const HTML_RUN_DOCUMENTS = new Set(["about:blank", "about:srcdoc"]);

/**
 * The Run tab may navigate only within its own documents (a `#` link
 * included). Everything else, CDN pages included (anyone can publish one), is
 * refused in place and opened nowhere.
 *
 * Which navigations come here differs by platform. iOS asks about every frame
 * (decidePolicyForNavigationAction). Android asks only about GET navigations,
 * and of a subframe's only those to other schemes than http, https and about
 * (AwContentBrowserClient::ShouldOverrideUrlLoading); the page frame's own
 * web navigations are stopped by the wrapper's frame-src instead
 * (lib/preview/htmlRunDocument.ts). Neither platform asks about subresources: CDN
 * scripts, styles, images, fonts and fetches follow PREVIEW_CSP_LIVE alone.
 * The frame flag is not read: iOS derives isTopFrame by comparing the URL with
 * the main document's, and Android does not send it.
 */
export function allowHtmlRunNavigation(request?: unknown): boolean {
  const url = navigationRequestUrl(request).trim().toLowerCase();
  // WebKit's name for a page loaded from a string without a base URL.
  if (url.startsWith("applewebdata:")) return true;
  const hash = url.indexOf("#");
  return HTML_RUN_DOCUMENTS.has(hash === -1 ? url : url.slice(0, hash));
}

/**
 * A preview page loaded from its file (lib/preview/previewPageFile.ts). Every URL
 * reaches {@link allowPreviewPageNavigation}, so react-native-webview never
 * hands one to the OS by itself; {@link previewPageLinkToOpen} decides that.
 */
export const PREVIEW_PAGE_ORIGIN_WHITELIST: string[] = ["*"];

/** The page may load itself and nothing else: no other file, no web page. */
export function allowPreviewPageNavigation(pageUri: string, request?: unknown): boolean {
  const url = navigationRequestUrl(request).trim();
  // A subframe's blank document, never the card itself.
  if (url.toLowerCase() === "about:blank") return !navigationRequestIsTopFrame(request);
  const page = filePath(pageUri);
  return page !== null && filePath(url) === page;
}

/**
 * A navigation the page may not make that should still open, as links in
 * these cards did before they were files: a top-frame link the chat would open
 * too (lib/linkSchemePolicy.ts), right after the user touched the WebView
 * (lib/preview/previewTap.ts). Script in the page can navigate on its own; without
 * that touch nothing opens.
 */
export function previewPageLinkToOpen(request: unknown, tap: PreviewTapGate): string | null {
  if (!navigationRequestIsTopFrame(request)) return null;
  if (!navigationRequestMayBeTap(request)) return null;
  return previewPagePostedLinkToOpen(navigationRequestUrl(request), tap);
}

/**
 * A link the page posted (lib/preview/previewPage.ts) opens on the same terms: a link
 * the chat would open, right after a touch. The page posts what it likes.
 */
export function previewPagePostedLinkToOpen(url: string, tap: PreviewTapGate): string | null {
  const link = url.trim();
  return isAllowedLinkUrl(link) && tap.claim() ? link : null;
}

/**
 * What the WebView itself says started a navigation. iOS reports the type,
 * and only a link activation may open (script can click a link too, so the
 * touch still decides). Android (react-native-webview 14) reports nothing
 * there, so the touch alone decides; a request that does say it had no
 * gesture, or was a redirect, never opens.
 */
function navigationRequestMayBeTap(request: unknown): boolean {
  if (Platform.OS === "ios") return navigationRequestType(request) === "click";
  return (
    navigationRequestField(request, "hasGesture") !== false &&
    navigationRequestField(request, "isRedirect") !== true
  );
}

/**
 * A PDF preview's page (features/attachments/hooks/usePdfPreview.ts) is an
 * HTML string. Every URL reaches {@link allowPdfPageNavigation}, so
 * react-native-webview never hands one to the OS: a PDF is untrusted, and its
 * page has no links of its own to follow.
 */
export const PDF_PAGE_ORIGIN_WHITELIST: string[] = ["*"];

/** The page may load itself (iOS reports the string's document as about:blank) and nothing else. */
export function allowPdfPageNavigation(request?: unknown): boolean {
  return navigationRequestUrl(request).trim().toLowerCase() === "about:blank";
}

/** A file URL's whole path, decoded, with iOS's /private/var spelled /var. */
function filePath(url: string): string | null {
  const match = /^file:\/\/(?:localhost)?(\/[^?#]*)/i.exec(url);
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]).replace(/^\/private\/var\//, "/var/");
  } catch {
    return null;
  }
}

/** One field of RN WebView's request, from the request or its nativeEvent (a test stub is plain). */
function navigationRequestField(request: unknown, name: string): unknown {
  if (request == null || typeof request !== "object") return undefined;
  const rec = request as Record<string, unknown> & { nativeEvent?: Record<string, unknown> };
  return rec[name] ?? rec.nativeEvent?.[name];
}

function navigationRequestUrl(request: unknown): string {
  const url = navigationRequestField(request, "url");
  return typeof url === "string" ? url : "";
}

/** Top-frame flag from RN WebView request (defaults true when unknown: Android sends none). */
function navigationRequestIsTopFrame(request: unknown): boolean {
  const isTopFrame = navigationRequestField(request, "isTopFrame");
  return typeof isTopFrame === "boolean" ? isTopFrame : true;
}

function navigationRequestType(request: unknown): string {
  const navigationType = navigationRequestField(request, "navigationType");
  return typeof navigationType === "string" ? navigationType : "other";
}
