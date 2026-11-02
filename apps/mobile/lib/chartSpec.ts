/**
 * What a ```chart fence can draw, decided before a WebView mounts.
 *
 * The contract (the server's CHART_FORMAT_HINT names the same shapes): Vega-Lite (or
 * Vega) whose data is written inline as `data.values`. The phone also reads the
 * dialects models write anyway: a `series` chart of points, a Chart.js config, and
 * category labels with series of values in any of their spellings. A body with
 * no inline data (a formula, `data.sequence`, a URL, nothing) or no JSON at all is not
 * drawn: the card says so and shows whatever data it has as a table, never a blank plot.
 * The phone never evaluates a formula; the server turns a formula chart into a
 * verified ```graph.
 */
import { categoryChartToVegaLite } from "@/lib/chartCategorySpec";
import { chartJsToVegaLite } from "@/lib/chartJsSpec";
import {
  parseChartBody,
  seriesChartToVegaLite,
  type JsonRecord,
} from "@/lib/chartSeriesSpec";
import { isJsonRecord as isRecord } from "@/lib/jsonFence";

export type ChartTable = { columns: string[]; rows: string[][] };

type ChartRead = {
  /** The Vega-Lite or Vega spec to draw, or null when the body cannot be drawn. */
  spec: JsonRecord | null;
  /** The chart's inline data as a table, for when it cannot be drawn. */
  table: ChartTable | null;
};

const CHILD_KEYS = ["layer", "hconcat", "vconcat", "concat"] as const;
const MAX_TABLE_ROWS = 30;
const MAX_TABLE_COLUMNS = 5;

/** Every inline `values` array in a spec: its own, its children's, named datasets. */
function inlineValues(spec: JsonRecord): unknown[][] {
  const found: unknown[][] = [];
  const data = spec.data;
  // Vega-Lite: `data: {values}`. Vega: `data: [{name, values}, …]`.
  for (const set of Array.isArray(data) ? data : [data]) {
    if (isRecord(set) && Array.isArray(set.values) && set.values.length > 0) found.push(set.values);
  }
  if (isRecord(spec.datasets)) {
    for (const set of Object.values(spec.datasets)) {
      if (Array.isArray(set) && set.length > 0) found.push(set);
    }
  }
  for (const key of CHILD_KEYS) {
    const kids = spec[key];
    if (!Array.isArray(kids)) continue;
    for (const kid of kids) if (isRecord(kid)) found.push(...inlineValues(kid));
  }
  if (isRecord(spec.spec)) found.push(...inlineValues(spec.spec));
  return found;
}

function cell(value: unknown): string | null {
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : null;
  if (typeof value === "string" || typeof value === "boolean") return String(value);
  return null;
}

/** A spec's first inline data as rows and columns, or null when it has none. */
export function chartTable(spec: JsonRecord): ChartTable | null {
  const values = inlineValues(spec)[0];
  if (!values) return null;
  const records = values.map((row) => (isRecord(row) ? row : { value: row }));
  const columns: string[] = [];
  for (const record of records) {
    for (const [key, value] of Object.entries(record)) {
      if (cell(value) !== null && !columns.includes(key)) columns.push(key);
    }
  }
  if (columns.length === 0) return null;
  const shown = columns.slice(0, MAX_TABLE_COLUMNS);
  return {
    columns: shown,
    rows: records.slice(0, MAX_TABLE_ROWS).map((record) => shown.map((key) => cell(record[key]) ?? "")),
  };
}

/** A chart body's JSON as Vega-Lite when it is in another dialect; as written otherwise. */
export function asVegaSpec(parsed: JsonRecord): JsonRecord {
  return (
    seriesChartToVegaLite(parsed) ??
    chartJsToVegaLite(parsed) ??
    categoryChartToVegaLite(parsed) ??
    parsed
  );
}

/** A chart fence's body: the spec to draw, or null and the data it has. */
export function readChart(raw: string): ChartRead {
  const parsed = parseChartBody(raw);
  if (!isRecord(parsed)) return { spec: null, table: null };
  const spec = asVegaSpec(parsed);
  return { spec: inlineValues(spec).length > 0 ? spec : null, table: chartTable(spec) };
}
