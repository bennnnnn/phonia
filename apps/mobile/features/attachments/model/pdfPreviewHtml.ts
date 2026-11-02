import { PDF_PREVIEW_CSP, PREVIEW_VIEWPORT, inlineScript } from "@/lib/preview/previewSandbox";
import type { Theme } from "@/lib/theme";

/** pdf.js and its worker, which the page inlines (lib/vendorAssets.ts). */
export const PDF_LIBRARIES = ["pdf", "pdfWorker"] as const;
export type PdfSources = Readonly<Record<(typeof PDF_LIBRARIES)[number], string>>;

/** How one preview draws; the page reads it as `window.RECALL_PDF`. */
type PdfPreviewConfig = {
  /** Every page, drawn as it scrolls near; otherwise page 1 only. */
  allPages: boolean;
  colors: { bg: string; text: string; danger: string };
};

/**
 * Anything but base64 and the whitespace atob skips. The page holds its PDF in
 * the markup as is, so a character like this (`<`, say) must never reach it.
 */
const NOT_BASE64 = /[^A-Za-z0-9+/=\t\n\f\r ]/;

export function pdfPreviewColors(theme: Theme): PdfPreviewConfig["colors"] {
  return { bg: theme.bg, text: theme.text, danger: theme.danger };
}

// Runs inside the WebView. Pages are drawn when they come near the viewport and
// cleared when they move far away, so a long PDF never holds every page's pixels.
const PAGE_SCRIPT = `(function () {
  var cfg = window.RECALL_PDF || {};
  var colors = cfg.colors || {};
  var style = document.documentElement.style;
  if (colors.bg) style.setProperty('--bg', colors.bg);
  if (colors.text) style.setProperty('--text', colors.text);
  if (colors.danger) style.setProperty('--danger', colors.danger);
  var errBox = document.getElementById('err');
  var pages = document.getElementById('pages');
  function fail(err) {
    errBox.textContent = 'PDF preview: ' + (err && err.message ? err.message : String(err));
    errBox.style.display = 'block';
  }
  // The worker source sits in a non-executable tag; a Blob URL spawns it with no fetch.
  var workerText = document.getElementById('pdf-worker-src').textContent;
  pdfjsLib.GlobalWorkerOptions.workerSrc = URL.createObjectURL(new Blob([workerText], { type: 'application/javascript' }));
  // The PDF is this page's own text, in a tag that never runs: nothing is fetched or read.
  // The tag goes once decoded, so the page keeps no second copy of the file.
  function readBytes() {
    var tag = document.getElementById('pdf-data');
    var raw = atob(tag.textContent);
    tag.parentNode.removeChild(tag);
    var bytes = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
    return bytes;
  }
  var ratio = Math.min(2, window.devicePixelRatio || 1);
  function fit(page) { return (window.innerWidth - 16) / page.getViewport({ scale: 1 }).width; }
  function slot(page) {
    var canvas = document.createElement('canvas');
    var size = page.getViewport({ scale: fit(page) });
    canvas.style.width = size.width + 'px';
    canvas.style.height = size.height + 'px';
    pages.appendChild(canvas);
    return canvas;
  }
  function draw(page, canvas) {
    var css = page.getViewport({ scale: fit(page) });
    var viewport = page.getViewport({ scale: fit(page) * ratio });
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    canvas.style.width = css.width + 'px';
    canvas.style.height = css.height + 'px';
    return page.render({ canvasContext: canvas.getContext('2d'), viewport: viewport });
  }
  function lazyPages(pdf, first) {
    var turns = {};
    var tasks = {};
    function show(n, canvas) {
      if (turns[n]) return;
      var turn = turns[n] = {};
      pdf.getPage(n).then(function (page) {
        if (turns[n] !== turn) return;
        tasks[n] = draw(page, canvas);
        return tasks[n].promise;
      }).catch(function (err) {
        if (!err || err.name !== 'RenderingCancelledException') fail(err);
      });
    }
    function hide(n, canvas) {
      if (!turns[n]) return;
      turns[n] = null;
      if (tasks[n]) tasks[n].cancel();
      tasks[n] = null;
      canvas.width = 0;
      canvas.height = 0;
    }
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        var n = Number(entry.target.getAttribute('data-page'));
        if (entry.isIntersecting) show(n, entry.target);
        else hide(n, entry.target);
      });
    }, { rootMargin: '150% 0px' });
    for (var n = 1; n <= pdf.numPages; n++) {
      // Page 1's size stands in for the rest until each is drawn.
      var canvas = slot(first);
      canvas.setAttribute('data-page', String(n));
      observer.observe(canvas);
    }
  }
  new Promise(function (resolve) { resolve(readBytes()); }).then(function (bytes) {
    // No eval-compiled font paths: pdf.js 3.x runs a crafted font as script (CVE-2024-4367),
    // and a PDF is untrusted content.
    return pdfjsLib.getDocument({ data: bytes, isEvalSupported: false }).promise;
  }).then(function (pdf) {
    return pdf.getPage(1).then(function (first) {
      if (cfg.allPages) return lazyPages(pdf, first);
      return draw(first, slot(first)).promise;
    });
  }).catch(fail);
})();`;

/**
 * The PDF's page, handed to the WebView whole (`source: { html }`): pdf.js, its
 * worker and the PDF itself all ride in it, so it fetches and reads nothing and
 * needs no file access. `base64` is the PDF; the page holds it as text and
 * decodes it once (an attachment is at most MAX_ATTACHMENT_BYTES, so at most
 * about 13.4 MB of base64). The template is ours, so its CSP is written in
 * place rather than found by scanning the whole document (injectPreviewCsp).
 */
export function buildPdfPreviewHtml(
  base64: string,
  theme: Theme,
  allPages: boolean,
  sources: PdfSources,
): string {
  if (NOT_BASE64.test(base64)) throw new Error("The PDF is not base64.");
  const config: PdfPreviewConfig = { allPages, colors: pdfPreviewColors(theme) };
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta http-equiv="Content-Security-Policy" content="${PDF_PREVIEW_CSP}">
<meta charset="UTF-8">
<meta name="viewport" content="${PREVIEW_VIEWPORT}">
<script>${inlineScript(`window.RECALL_PDF = ${JSON.stringify(config)};`)}</script>
<script>${inlineScript(sources.pdf)}</script>
<script type="text/pdf-worker" id="pdf-worker-src">${inlineScript(sources.pdfWorker)}</script>
<script type="application/pdf" id="pdf-data">${base64}</script>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; padding: 8px; background: var(--bg, #fff); color: var(--text, #111); font-family: -apple-system, sans-serif; }
  #err { color: var(--danger, #d92d20); font-size: 12px; display: none; white-space: pre-wrap; padding: 8px; }
  canvas { display: block; margin: 0 auto 8px; max-width: 100%; background: #fff; }
</style>
</head>
<body>
<div id="pages"></div>
<div id="err"></div>
<script>${PAGE_SCRIPT}</script>
</body>
</html>`;
}
