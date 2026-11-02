import { HTML_RUN_CDN_CSP } from "@/lib/preview/htmlRunCdn";

/**
 * Content-Security-Policy for the sandboxed HTML/JS preview.
 *
 * The preview runs model/user-generated HTML+JS in an in-app WebView. It has no
 * app tokens (baseUrl about:blank, no cookies), but without a CSP the JS
 * could still make arbitrary network egress. This policy locks down the document:
 *  - default-src 'none': deny everything by default
 *  - script-src / style-src 'unsafe-inline' only — inline code runs (the
 *    preview's purpose). NO https:: a <script src="https://evil/?…"> is a
 *    working GET exfil channel that bypasses connect-src 'none'.
 *  - img/font/media: data/blob only — NO https:. An <img src="https://…"> (or
 *    font/media URL) is the same passive GET exfil class.
 *  - connect-src 'none': JS cannot fetch/XHR/WebSocket anywhere (no exfiltration)
 *  - base-uri 'none' / form-action 'none': no <base> hijack, no form submits
 *
 * Note: a meta CSP `sandbox` directive is NOT equivalent to an iframe `sandbox`
 * attribute (browsers ignore sandbox in meta CSP per the HTML spec). Opaque
 * origin / storage isolation come from the WebView config (`domStorageEnabled`
 * off, no shared cookies) — not from this meta tag. We still list
 * `sandbox allow-scripts` for environments that honor it; do not treat it as
 * a guarantee of iframe-style isolation.
 */
/** Egress-locked CSP without the meta `sandbox` token (mermaid/chemistry/KaTeX). */
export const PREVIEW_CSP_INLINE = [
  "default-src 'none'",
  "style-src 'unsafe-inline'",
  "script-src 'unsafe-inline'",
  "img-src data: blob:",
  "font-src data:",
  "media-src data: blob:",
  "connect-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
].join("; ");

/** Allow pinch-zoom and system text scaling in preview WebViews. Never set maximum-scale. */
export const PREVIEW_VIEWPORT = "width=device-width, initial-scale=1";

/**
 * Default preview CSP for trusted inlined bundles (mermaid/chemistry/KaTeX).
 * Includes a meta `sandbox` token for environments that honor it.
 * Charts use {@link CHART_PREVIEW_CSP} — Vega needs `'unsafe-eval'`.
 */
export const PREVIEW_CSP = `${PREVIEW_CSP_INLINE}; sandbox allow-scripts`;

/**
 * HTML Run tab policy (lib/preview/htmlRunDocument.ts). The wrapper page carries it and
 * the model's page inherits it (a srcdoc frame takes its parent's policy), so
 * page markup cannot drop or misplace it. Scripts, styles, images, fonts and
 * fetches may come from the CDN allowlist (lib/preview/htmlRunCdn.ts) so CSS/JS demos
 * paint; no other host is reachable and no form submits. Every `<meta
 * http-equiv>` in the page is disarmed (lib/preview/htmlMetaPragmas.ts), so none
 * redirects it or adds a policy.
 *
 * frame-src 'none' also stops the page frame navigating itself: Chromium
 * (NavigationRequest::CheckCSPDirectives) and WebKit (PolicyChecker) check the
 * parent's frame-src on every navigation of a child frame and skip about: URLs,
 * so the srcdoc frame itself still loads. Android needs this: its WebView never
 * asks the app about a subframe's http(s) navigation. A CDN script, stylesheet
 * or image is a subresource load, not a navigation, and never reaches the
 * WebView's navigation callback.
 */
export const PREVIEW_CSP_LIVE = [
  "default-src 'none'",
  `style-src 'unsafe-inline' ${HTML_RUN_CDN_CSP}`,
  `script-src 'unsafe-inline' ${HTML_RUN_CDN_CSP}`,
  `img-src data: blob: ${HTML_RUN_CDN_CSP}`,
  `font-src data: ${HTML_RUN_CDN_CSP}`,
  `media-src data: blob: ${HTML_RUN_CDN_CSP}`,
  `connect-src ${HTML_RUN_CDN_CSP}`,
  "frame-src 'none'",
  `worker-src blob: ${HTML_RUN_CDN_CSP}`,
  "base-uri 'none'",
  "form-action 'none'",
].join("; ");

/**
 * CSP for the PDF preview WebView (pdf.js).
 *
 * pdf.js + its worker are vendored and inlined (the worker is built from a
 * Blob URL at runtime, hence `worker-src blob:`). The PDF bytes are inlined
 * as base64 — no fetch, and no file read (features/attachments/model/pdfPreviewHtml.ts). A PDF is
 * untrusted and pdf.js has had script-capable bugs, so the page reaches
 * nothing outside itself: `connect-src 'none'`, and images, fonts and media
 * only from data: and blob:. (CMap/standard-font fetches are not configured,
 * so pdf.js never reaches the network for the previews we render.)
 */
export const PDF_PREVIEW_CSP = [
  "default-src 'none'",
  "style-src 'unsafe-inline'",
  "script-src 'unsafe-inline'",
  "worker-src blob:",
  "img-src data: blob:",
  "font-src data:",
  "media-src data: blob:",
  "connect-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
  "sandbox allow-scripts",
].join("; ");

/**
 * CSP for the chart WebView (vendored Vega / Vega-Lite / Vega-Embed).
 *
 * Vega compiles filter/calculate expressions with `new Function()`, which
 * CSP treats as eval. Without `'unsafe-eval'` the card paints a red
 * "Refused to evaluate a string as JavaScript" instead of bars. The spec
 * is `JSON.parse`'d (not executed as a script). Do **not** add eval to
 * {@link PREVIEW_CSP} — that document runs model HTML.
 */
export const CHART_PREVIEW_CSP = [
  "default-src 'none'",
  "style-src 'unsafe-inline'",
  "script-src 'unsafe-inline' 'unsafe-eval'",
  "img-src data: blob:",
  "font-src data:",
  "media-src data: blob:",
  "connect-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
  "sandbox allow-scripts",
].join("; ");

/**
 * CSP for a reply's HTML handed to the system browser or the share sheet
 * ("Open in browser", Share). That file opens outside the app (a browser tab,
 * Quick Look, another app) where nothing of ours sandboxes it, so its policy
 * travels inside it, and holds even where `stripScripts` missed something:
 *  - default-src 'none': no script of any kind. With no script-src, inline
 *    `<script>`, `on*` handlers and `javascript:` URLs are all refused, and so
 *    are fetch/XHR/WebSocket, frames, objects, embeds, fonts, media, workers
 *    and manifests: every fetch directive falls back to it.
 *  - style-src 'unsafe-inline': the page's own `<style>` and `style=""` paint;
 *    no stylesheet or `@import` loads.
 *  - img-src data: https:: its pictures show. The person chose to open the
 *    page; `http:` and every other scheme stay blocked.
 *  - base-uri 'none' and form-action 'none': no `<base>` retargets its links
 *    and no form submits anywhere. Neither falls back to default-src.
 * Left out: script-src 'none' and object-src 'none' (default-src already says
 * so); frame-ancestors, report-uri and sandbox (ignored in a `<meta>` CSP);
 * upgrade-insecure-requests (no `http:` source to upgrade). A meta refresh is
 * not a CSP matter: `stripScripts` disarms every `<meta http-equiv>`.
 */
export const HTML_EXPORT_CSP = [
  "default-src 'none'",
  "style-src 'unsafe-inline'",
  "img-src data: https:",
  "base-uri 'none'",
  "form-action 'none'",
].join("; ");

/**
 * End-tag pattern that accepts HTML5 junk before `>` (e.g. `</script\t\n bar>`).
 * CodeQL js/bad-tag-filter rejects `</script\s*>` which misses those shapes.
 */
const SCRIPT_END = String.raw`<\/script[^>]*>`;

/** A DOCTYPE at the very start: only HTML whitespace before it, ending at its first `>` as a browser's does. */
const LEADING_DOCTYPE = /^[\t\n\f\r ]*<!doctype[^>]*>/i;
/** A tag that makes the text a document (put the meta in front) rather than a fragment (wrap it). */
const DOCUMENT_TAG = /<(?:html|head|body)[\s/>]/i;

/**
 * Inject a CSP meta into an HTML document, or wrap a bare fragment in one.
 *
 * The meta becomes the document's first element (after a leading DOCTYPE), not
 * the first child of the document's own `<head>` tag. A browser ignores a CSP
 * meta outside `<head>` (HTML §4.2.5.3), and a `<head>` tag that comes after
 * body content (`<html>x<head>`) is itself ignored, so a meta spliced after it
 * lands in `<body>` and the page runs with no policy. The first element of a
 * document always goes into the head the parser opens, and nothing before it
 * can run or load. Nothing is searched for, so a decoy `<head` inside a
 * script, comment, `<textarea>` or attribute cannot misplace it. A well-formed
 * document gets the same DOM as before: the CSP is its head's first child.
 */
export function injectPreviewCsp(html: string, csp: string = PREVIEW_CSP): string {
  return injectAtHeadStart(html, cspMetaTag(csp));
}

/** The `<meta>` that delivers `csp`. */
export function cspMetaTag(csp: string): string {
  return `<meta http-equiv="Content-Security-Policy" content="${csp}">`;
}

/** Put `markup` first in the document, as {@link injectPreviewCsp} does its meta. */
export function injectAtHeadStart(html: string, markup: string): string {
  const doctype = LEADING_DOCTYPE.exec(html)?.[0];
  if (doctype) return doctype + markup + html.slice(doctype.length);
  if (DOCUMENT_TAG.test(html)) return markup + html;
  return `<!DOCTYPE html><html><head>${markup}</head><body>${html}</body></html>`;
}

/**
 * Make a raw JS source safe to inline inside a <script>...</script> block.
 * Preview page files embed their libraries with this: a change here needs a
 * new PAGE_FORMAT in lib/preview/previewPageFile.ts, or old pages stay in use.
 */
export function inlineScript(source: string): string {
  return source.replace(new RegExp(SCRIPT_END, "gi"), "<\\/script>");
}
