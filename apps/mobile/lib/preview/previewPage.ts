/**
 * A preview WebView page (a Mermaid diagram, a chart, a SMILES drawing) is
 * built once from its vendored libraries and loaded from a file
 * (lib/preview/previewPageFile.ts). The page holds no block's data: each WebView hands
 * its own (the diagram source, the chart spec, the SMILES) to the page script.
 */

/** A page built from named libraries; `build` gets each library's source. */
export type PreviewPage<L extends string = string> = {
  /** Names the page's file, so one name per page. */
  name: string;
  libraries: readonly L[];
  build: (sources: Readonly<Record<L, string>>) => string;
  /** A file an earlier app version wrote in the cache directory for this page, removed once this one is in place. */
  formerFile?: string;
};

/** One block's data, as the page script reads it. */
export type PreviewPageConfig = Record<string, unknown>;

/** Where the page finds its block's data, and the function that starts it. */
const CONFIG_GLOBAL = "RECALL_PREVIEW";
const START_GLOBAL = "RECALL_PREVIEW_START";

/**
 * What a page posts for a link the user tapped: `{ kind, url }`. Any script in the page can post
 * one, so the app opens it only right after a touch on the WebView (lib/preview/previewTap.ts).
 */
export const PREVIEW_PAGE_LINK_KIND = "preview-link";

/**
 * The script that hands a block's data to its page. The WebView runs it before
 * the page loads and again once it has (`injectedJavaScriptBeforeContentLoaded`
 * and `injectedJavaScript`): Android may run the first one too late, or on the
 * document being replaced. The data is a JSON literal, so it cannot end the script.
 */
export function previewPageConfigScript(config: PreviewPageConfig): string {
  const json = JSON.stringify(config).replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
  return (
    `window.${CONFIG_GLOBAL} = ${json}; ` +
    `if (typeof window.${START_GLOBAL} === "function") window.${START_GLOBAL}(window.${CONFIG_GLOBAL}); true;`
  );
}

/** The URL a page posted for a tapped link, or null for any other message. */
export function previewPageLink(data: string | undefined): string | null {
  if (!data) return null;
  try {
    const message: unknown = JSON.parse(data);
    if (typeof message !== "object" || message === null) return null;
    const { kind, url } = message as { kind?: unknown; url?: unknown };
    return kind === PREVIEW_PAGE_LINK_KIND && typeof url === "string" ? url : null;
  } catch {
    return null;
  }
}

/**
 * The page's own script: `start` (a function expression) runs once, with the
 * first data to arrive, whether that came before this script ran or after.
 *
 * Links never navigate the page. A tapped link, or a window the page opens,
 * becomes a `PREVIEW_PAGE_LINK_KIND` message (`start` can call `postLink` for
 * links a library follows itself), so nothing depends on the WebView's own
 * navigation check, which Android lets through when the app is slow to answer.
 */
export function previewPageStartScript(start: string): string {
  return `(function () {
  function postLink(href) {
    var url = String(href);
    try { url = new URL(url, document.baseURI).href; } catch (e) {}
    try { window.ReactNativeWebView && window.ReactNativeWebView.postMessage(JSON.stringify({ kind: '${PREVIEW_PAGE_LINK_KIND}', url: url })); } catch (e) {}
  }
  document.addEventListener('click', function (event) {
    var node = event.target;
    while (node && !(node.nodeName && String(node.nodeName).toLowerCase() === 'a')) node = node.parentNode;
    if (!node) return;
    event.preventDefault();
    event.stopPropagation();
    var href = node.getAttribute('href') || node.getAttributeNS('http://www.w3.org/1999/xlink', 'href');
    // A tap, not a click the page dispatched itself.
    if (href && event.isTrusted) postLink(href);
  }, true);
  window.open = function (href) {
    if (href) postLink(href);
    return null;
  };
  var start = ${start};
  var started = false;
  function begin(config) {
    if (started || !config) return;
    started = true;
    start(config);
  }
  window.${START_GLOBAL} = begin;
  begin(window.${CONFIG_GLOBAL});
})();`;
}
