import { disarmMetaPragmas } from "@/lib/preview/htmlMetaPragmas";
import {
  PREVIEW_CSP_LIVE,
  PREVIEW_VIEWPORT,
  cspMetaTag,
  injectAtHeadStart,
} from "@/lib/preview/previewSandbox";

/**
 * The HTML Run tab's document: a small wrapper page the app writes, with the
 * model's page inside `<iframe sandbox srcdoc>`. The browser engine enforces
 * the sandbox, so page script cannot switch it off:
 *  - no allow-top-navigation: `top.location = …`, `<a target="_top">` and
 *    the like fail, so the WebView never leaves the wrapper;
 *  - no allow-popups: `window.open` and `target="_blank"` open nothing;
 *  - no allow-same-origin: the page has an opaque origin and cannot reach the
 *    wrapper, cookies or storage.
 * allow-forms lets a demo's submit handler run (Blink drops the submit event
 * in a frame without it); form-action 'none' still stops every submission.
 * allow-modals keeps the alert / confirm that demos use (react-native-webview
 * shows them natively).
 *
 * Page script can still try to navigate its own frame. The wrapper carries
 * PREVIEW_CSP_LIVE, which the frame inherits (page markup cannot drop or move
 * it), and both engines check its frame-src 'none' on each of the frame's
 * navigations, skipping only about: URLs such as the srcdoc itself. That, not
 * allowHtmlRunNavigation, is what stops it on Android, which never asks the app
 * about a subframe's http(s) navigation (AwContentBrowserClient::
 * ShouldOverrideUrlLoading) and lets a navigation through when the JS thread
 * takes over 250 ms to answer (RNCWebViewClient.shouldOverrideUrlLoading).
 */
const HTML_RUN_FRAME_SANDBOX = "allow-scripts allow-forms allow-modals";

/** `kind` of the WebView message the Run tab gets when the page drew nothing. */
export const HTML_RUN_EMPTY_KIND = "preview-empty";

/** What the page frame posts to the wrapper when it drew nothing. */
const EMPTY_SIGNAL = "recall-run:empty";

/**
 * Cancels a tapped link, which would replace the page inside its frame (or,
 * blocked by frame-src, leave an error page there); `#` and `javascript:`
 * links still work for in-page demos. Script that sets `location` is not
 * stopped here (Location cannot be overridden): the sandbox keeps it out of
 * the wrapper and frame-src out of the frame.
 */
const LINK_TRAP_JS = `(function () {
  document.addEventListener("click", function (e) {
    try {
      var t = e.target;
      while (t && t.tagName !== "A") t = t.parentElement;
      if (!t || !t.getAttribute) return;
      var href = t.getAttribute("href") || "";
      if (!href || href.charAt(0) === "#" || href.indexOf("javascript:") === 0) return;
      e.preventDefault();
      e.stopPropagation();
    } catch (err) {}
  }, true);
})();`;

/** Tells the wrapper when the page loaded with nothing to show. */
const EMPTY_CHECK_JS = `(function () {
  function check() {
    var b = document.body;
    if (!b) return;
    var text = (b.innerText || "").trim();
    var media = b.querySelectorAll("img,svg,canvas,video,iframe").length;
    var blocks = b.querySelectorAll(
      "div,section,main,article,p,span,ul,ol,table,pre,code,h1,h2,h3,h4,h5,h6"
    ).length;
    if (!text && !media && blocks <= 1) {
      try { parent.postMessage("${EMPTY_SIGNAL}", "*"); } catch (err) {}
    }
  }
  if (document.readyState === "complete") check();
  else window.addEventListener("load", function () { setTimeout(check, 300); });
})();`;

/**
 * The page frame has no window.ReactNativeWebView on iOS, so the wrapper
 * passes its empty signal on. (Any frame can still post to the app directly:
 * iOS registers the message handler for every frame and Android's listener
 * matches every origin. The Run tab acts on nothing but this signal.)
 */
const RELAY_JS = `(function () {
  window.addEventListener("message", function (event) {
    var frame = document.querySelector("iframe");
    if (!frame || event.source !== frame.contentWindow) return;
    if (event.data !== "${EMPTY_SIGNAL}") return;
    try {
      window.ReactNativeWebView.postMessage(JSON.stringify({ kind: "${HTML_RUN_EMPTY_KIND}" }));
    } catch (err) {}
  });
})();`;

/**
 * The frame fills the WebView and scrolls itself. No background: the page's
 * own (the themed wrapFullDocument body) or the browser's white shows through.
 */
const WRAPPER_CSS =
  "html,body{margin:0;height:100%;overflow:hidden}" +
  "iframe{display:block;width:100%;height:100%;border:0}";

/** The model's page: the live CSP and the link trap first in the document. */
function preparePage(html: string): string {
  const cspTag = cspMetaTag(PREVIEW_CSP_LIVE);
  const page =
    injectAtHeadStart(html, `${cspTag}<script>${LINK_TRAP_JS}</script>`) +
    `<script>${EMPTY_CHECK_JS}</script>`;
  // Last, over the whole page: the CSP written above is the one pragma kept.
  return disarmMetaPragmas(page, cspTag);
}

/** Escape for a double-quoted attribute: the parser decodes it back exactly. */
function escapeAttribute(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
}

/** The whole Run tab document for `source={{ html }}`. */
export function prepareHtmlRunDocument(html: string): string {
  return (
    '<!DOCTYPE html><html><head><meta charset="utf-8">' +
    cspMetaTag(PREVIEW_CSP_LIVE) +
    `<meta name="viewport" content="${PREVIEW_VIEWPORT}">` +
    `<style>${WRAPPER_CSS}</style></head><body>` +
    `<iframe sandbox="${HTML_RUN_FRAME_SANDBOX}" srcdoc="${escapeAttribute(preparePage(html))}"></iframe>` +
    `<script>${RELAY_JS}</script></body></html>`
  );
}
