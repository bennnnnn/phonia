/**
 * A Chart.js config in a chart fence (`{"type": "line", "data": {"labels": […],
 * "datasets": [{"label", "data": […]}]}, "options": {…}}`), read as Vega-Lite.
 * Models write it for "line chart of …"; Vega drew it as an empty card.
 */
import {
  pieValuesToVegaLite,
  readPoint,
  seriesMark,
  seriesValuesToVegaLite,
  text,
  type JsonRecord,
  type SeriesValue,
} from "@/lib/chartSeriesSpec";
import { isJsonRecord as isRecord } from "@/lib/jsonFence";

const PIE_TYPES = new Set(["pie", "doughnut", "polararea"]);

/** `options.scales.<axis>.title.text` (Chart.js 3+) or `options.plugins.title.text`. */
function optionText(options: unknown, path: string[]): string | undefined {
  let node: unknown = options;
  for (const key of path) {
    if (!isRecord(node)) return undefined;
    node = node[key];
  }
  return text(node);
}

/** The Chart.js config as Vega-Lite, or null when `spec` is not one. */
export function chartJsToVegaLite(spec: JsonRecord): JsonRecord | null {
  const data = spec.data;
  if (!isRecord(data) || !Array.isArray(data.datasets) || data.datasets.length === 0) return null;
  const labels: unknown[] = Array.isArray(data.labels) ? data.labels : [];
  const chartType = String(spec.type ?? "bar").toLowerCase();
  const values: SeriesValue[] = [];
  const marks = new Map<string, string>();
  for (const [index, set] of data.datasets.entries()) {
    if (!isRecord(set) || !Array.isArray(set.data)) return null;
    const name = text(set.label) ?? `Series ${index + 1}`;
    marks.set(name, seriesMark(set.type ?? chartType, "line"));
    for (const [at, item] of set.data.entries()) {
      if (item === null) continue;
      const point = readPoint(item);
      const label = labels[at];
      const x = typeof label === "number" || typeof label === "string" ? label : at + 1;
      if (point) values.push({ x: point[0], y: point[1], series: name });
      else if (typeof item === "number") values.push({ x, y: item, series: name });
      else return null;
    }
  }
  const options = spec.options;
  const title =
    optionText(options, ["plugins", "title", "text"]) ?? optionText(options, ["title", "text"]);
  if (PIE_TYPES.has(chartType)) {
    // One pie: the first dataset's slices.
    const first = [...marks.keys()][0];
    const slices = values.filter((row) => row.series === first);
    return pieValuesToVegaLite(slices, title, chartType === "doughnut");
  }
  return seriesValuesToVegaLite({
    values,
    marks,
    title,
    xTitle: optionText(options, ["scales", "x", "title", "text"]),
    yTitle: optionText(options, ["scales", "y", "title", "text"]),
  });
}
