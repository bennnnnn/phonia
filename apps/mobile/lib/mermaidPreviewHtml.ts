/**
 * The Mermaid diagram page for the preview WebView: built once with the
 * vendored library and loaded from a file (lib/preview/previewPageFile.ts); each block
 * hands it its diagram with `mermaidPreviewConfig`.
 */
import { previewPageStartScript, type PreviewPage } from "@/lib/preview/previewPage";
import { injectPreviewCsp, inlineScript } from "@/lib/preview/previewSandbox";
import type { Theme } from "@/lib/theme";

type MermaidPreviewTheme = Pick<Theme, "bg" | "danger" | "isDark">;

/** Runs in the WebView with one block's config. */
const START = `function (config) {
  var style = document.documentElement.style;
  style.setProperty('--bg', config.colors.bg);
  style.setProperty('--danger', config.colors.danger);
  function reportError(msg) {
    try { window.ReactNativeWebView && window.ReactNativeWebView.postMessage(JSON.stringify({ kind: 'mermaid-error', message: msg })); } catch (e) {}
    var el = document.getElementById('err');
    el.textContent = 'Diagram error: ' + msg;
    el.style.display = 'block';
  }
  function reportSize() {
    var svg = document.querySelector('#diagram svg');
    var h = 0;
    if (svg) {
      var box = svg.getBoundingClientRect();
      h = box.height;
    }
    if (!h) h = document.body.scrollHeight;
    try { window.ReactNativeWebView && window.ReactNativeWebView.postMessage(JSON.stringify({ kind: 'mermaid-size', height: Math.ceil(h + 16) })); } catch (e) {}
  }
  var el = document.getElementById('diagram');
  el.textContent = config.source;
  // A card fits the diagram to its width; the full-screen view draws it at
  // its own size, to pan and pinch.
  var fit = !config.natural;
  mermaid.initialize({
    startOnLoad: false,
    theme: config.theme,
    securityLevel: 'strict',
    flowchart: { useMaxWidth: fit, htmlLabels: false },
    sequence: { useMaxWidth: fit },
    er: { useMaxWidth: fit },
    class: { useMaxWidth: fit },
    state: { useMaxWidth: fit },
    gantt: { useMaxWidth: fit },
    pie: { useMaxWidth: fit },
    mindmap: { useMaxWidth: fit },
    timeline: { useMaxWidth: fit },
    journey: { useMaxWidth: fit },
  });
  mermaid.run({ nodes: [el] }).then(function() {
    requestAnimationFrame(reportSize);
  }).catch(function(err) { reportError(err && err.message ? err.message : String(err)); });
}`;

/**
 * Mermaid draws every `.mermaid` node on the window's load event unless told
 * not to. The diagram may arrive after that event (Android can run the early
 * injection late), and a node Mermaid already tried is never drawn again, so
 * auto-start is off before load and the diagram node has no `mermaid` class.
 */
const NO_AUTO_START = "mermaid.initialize({ startOnLoad: false });";

export function buildMermaidPageHtml(mermaidJs: string): string {
  return injectPreviewCsp(`<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<script>${inlineScript(mermaidJs)}</script>
<script>${NO_AUTO_START}</script>
<style>
  body { margin: 0; padding: 8px; font-family: -apple-system, sans-serif; background: var(--bg); }
  #err { color: var(--danger); font-size: 12px; display: none; white-space: pre-wrap; padding: 8px; }
  #diagram { display: flex; }
  /* Centred while it fits; a wider diagram starts at its left edge and scrolls. */
  #diagram svg { flex-shrink: 0; margin: 0 auto; }
</style>
</head>
<body>
<pre id="diagram"></pre>
<div id="err"></div>
<script>${previewPageStartScript(START)}</script>
</body>
</html>`);
}

export const MERMAID_PAGE: PreviewPage<"mermaid"> = {
  name: "mermaid",
  libraries: ["mermaid"],
  build: ({ mermaid }) => buildMermaidPageHtml(mermaid),
};

/** What one diagram's WebView hands the page. */
type MermaidPreviewConfig = {
  source: string;
  theme: "dark" | "neutral";
  colors: { bg: string; danger: string };
  /** Draw at the diagram's own size instead of fitting the width (full screen). */
  natural: boolean;
};

export function mermaidPreviewConfig(
  source: string,
  theme: MermaidPreviewTheme,
  { natural = false }: { natural?: boolean } = {},
): MermaidPreviewConfig {
  return {
    source: source.trim(),
    theme: theme.isDark ? "dark" : "neutral",
    colors: { bg: theme.bg, danger: theme.danger },
    natural,
  };
}
