/**
 * The chart page for the preview WebView (vendored Vega / Vega-Lite /
 * Vega-Embed): built once and loaded from a file (lib/preview/previewPageFile.ts);
 * each block hands it its spec with `chartPreviewConfig`, laid out for a phone
 * (lib/chartPresentation.ts). The page themes it and fits it to the card.
 *
 * Extracted so CSP injection and spec layout are unit-testable without ChartBlock.
 */
import { previewPageStartScript, type PreviewPage } from "@/lib/preview/previewPage";
import { CHART_PREVIEW_CSP, injectPreviewCsp, inlineScript } from "@/lib/preview/previewSandbox";
import type { Theme } from "@/lib/theme";
import { presentChartSpec } from "@/lib/chartPresentation";
import { parseChartBody } from "@/lib/chartSeriesSpec";
import { isJsonRecord as isRecord } from "@/lib/jsonFence";
import { asVegaSpec } from "@/lib/chartSpec";

type ChartPreviewTheme = Pick<
  Theme,
  "bg" | "text" | "textSecondary" | "border" | "danger" | "isDark"
>;

function specPayloadForEmbed(raw: string, width: number): string {
  const parsed = parseChartBody(raw);
  if (parsed === null) return raw;
  if (!isRecord(parsed)) return JSON.stringify(parsed);
  return JSON.stringify(presentChartSpec(asVegaSpec(parsed), width));
}

type VegaLibrary = "vega" | "vegaLite" | "vegaEmbed";

/** Runs in the WebView with one chart's config. */
const START = `function (config) {
  var colors = config.colors;
  var style = document.documentElement.style;
  style.setProperty('--bg', colors.bg);
  style.setProperty('--danger', colors.danger);
  function reportError(msg) {
    try { window.ReactNativeWebView && window.ReactNativeWebView.postMessage(JSON.stringify({ kind: 'chart-error', message: msg })); } catch (e) {}
    var el = document.getElementById('error');
    el.textContent = 'Chart error: ' + msg;
    el.style.display = 'block';
  }
  // Data marks (not axes, legends or titles) with a position on the plot.
  function drawnMarks(mark) {
    var n = 0;
    var items = (mark && mark.items) || [];
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      if (mark.role === 'mark' && mark.marktype !== 'group') {
        if (typeof item.x === 'number' && isFinite(item.x) && typeof item.y === 'number' && isFinite(item.y)) n++;
      }
      var kids = item.items || [];
      for (var k = 0; k < kids.length; k++) n += drawnMarks(kids[k]);
    }
    return n;
  }
  function reportSize() {
    var svg = document.querySelector('#chart svg');
    var h = 0;
    if (svg) {
      var box = svg.getBoundingClientRect();
      h = box.height;
    }
    if (!h) h = document.body.scrollHeight;
    try { window.ReactNativeWebView && window.ReactNativeWebView.postMessage(JSON.stringify({ kind: 'chart-size', height: Math.ceil(h + 16) })); } catch (e) {}
  }
  try {
    // Vega follows a mark's href itself: its loader hands the link to the app instead.
    var loader = vega.loader();
    var sanitize = loader.sanitize;
    loader.sanitize = function(uri, options) {
      if (options && options.context === 'href') {
        postLink(uri);
        return Promise.reject(new Error('The app opens links.'));
      }
      return sanitize.call(loader, uri, options);
    };
    var parsed = JSON.parse(config.spec);
    // A spec's own embed options would override these (actions, editor URL, loader).
    if (parsed && parsed.usermeta) delete parsed.usermeta.embedOptions;
    // Legends sit under the plot, in as many columns as the card has room for: on the
    // right a legend squeezed a 320 px plot to a 60 px strip.
    var legendColumns = Math.max(1, Math.floor(config.width / 150));
    var themedConfig = {
      background: colors.bg,
      axis: { domainColor: colors.axis, labelColor: colors.text, titleColor: colors.text, tickColor: colors.axis, gridColor: colors.grid },
      legend: { labelColor: colors.text, titleColor: colors.text, orient: 'bottom', columns: legendColumns, labelLimit: Math.floor(config.width / legendColumns) - 36 },
      title: { color: colors.text, limit: config.width - 10 },
      view: { stroke: colors.axis },
    };
    // The spec's own config wins, key by key inside each block it sets.
    var own = parsed.config || {};
    var merged = Object.assign({}, themedConfig, own);
    for (var key in themedConfig) {
      if (own[key] && typeof own[key] === 'object' && !Array.isArray(own[key])) merged[key] = Object.assign({}, themedConfig[key], own[key]);
    }
    parsed.config = merged;
    // The width is the card's, axes and labels included: a plain width sized only the
    // plot, and the y axis pushed its right edge out of the card.
    if (!parsed.autosize) parsed.autosize = { type: 'fit-x', contains: 'padding' };
    // A plot with no x axis, or named categories along x, took its width from a 20 px
    // step per category and drew as a sliver; a unit or layered plot fills the card.
    var enc = parsed.encoding || {};
    if (parsed.width == null && (parsed.mark || parsed.layer) && !enc.row && !enc.column && !enc.facet) parsed.width = config.width;
    vegaEmbed('#chart', parsed, {
      actions: false,
      tooltip: false,
      renderer: 'svg',
      width: config.width,
      theme: config.vegaTheme,
      config: themedConfig,
      loader: loader,
    }).then(function(result) {
      // A spec Vega accepts can still draw nothing (bars with no x, a dataflow that
      // threw): the card shows its data instead of an empty plot.
      if (result && result.view && !drawnMarks(result.view.scenegraph().root)) {
        reportError('No data marks were drawn.');
        return;
      }
      requestAnimationFrame(reportSize);
    }).catch(function(err) { reportError(err && err.message ? err.message : String(err)); });
  } catch (e) {
    reportError(e && e.message ? e.message : String(e));
  }
}`;

/** The page that renders a Vega / Vega-Lite spec via vendored Vega-Embed. */
export function buildVegaPageHtml(sources: Readonly<Record<VegaLibrary, string>>): string {
  return injectPreviewCsp(
    `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<script>${inlineScript(sources.vega)}</script>
<script>${inlineScript(sources.vegaLite)}</script>
<script>${inlineScript(sources.vegaEmbed)}</script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { overflow: hidden; }
  body { padding: 8px; font-family: -apple-system, sans-serif; background: var(--bg); }
  #chart { width: 100%; max-width: 100%; overflow: hidden; }
  #error { color: var(--danger); padding: 16px; font-size: 13px; display: none; white-space: pre-wrap; word-break: break-word; }
</style>
</head>
<body>
<div id="chart"></div>
<div id="error"></div>
<script>${previewPageStartScript(START)}</script>
</body>
</html>`,
    CHART_PREVIEW_CSP,
  );
}

export const CHART_PAGE: PreviewPage<VegaLibrary> = {
  name: "chart",
  libraries: ["vega", "vegaLite", "vegaEmbed"],
  build: buildVegaPageHtml,
};

/** What one chart's WebView hands the page: the spec laid out for a phone, and the theme. */
type ChartPreviewConfig = {
  /** JSON text; the page parses it, so a body it cannot read shows as a chart error. */
  spec: string;
  width: number;
  vegaTheme: "dark" | "vox";
  colors: { bg: string; text: string; axis: string; grid: string; danger: string };
};

export function chartPreviewConfig(
  spec: string,
  theme: ChartPreviewTheme,
  plotWidth = 320,
): ChartPreviewConfig {
  const width = Math.max(120, Math.floor(plotWidth));
  return {
    spec: specPayloadForEmbed(spec, width),
    width,
    vegaTheme: theme.isDark ? "dark" : "vox",
    colors: {
      bg: theme.bg,
      text: theme.text,
      axis: theme.textSecondary,
      grid: theme.border,
      danger: theme.danger,
    },
  };
}
