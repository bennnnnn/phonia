/**
 * A chart written as category labels and series of numbers, however a model spelled it:
 * `{"type": "bar", "labels": […], "series": [{"name", "values": […]}]}`, Chart.js's
 * `labels` + `datasets: [{"label", "data"}]` without its `data` wrapper, or axis blocks
 * (`"xAxis": {"title", "categories" | "labels" | "values" | "data"}`, `"yAxis": {"title",
 * "min", "max"}`) the way Highcharts writes them. Each of these drew "Could not render
 * that chart." Read as Vega-Lite: bars (laid out horizontally on the phone, series side
 * by side), lines, areas, points, or a pie. A value list as long as the labels is the only
 * reading: one of another length is not guessed at, and the chart is not drawn.
 */
import {
  axisBlock,
  axisTitle,
  pieValuesToVegaLite,
  readPoint,
  seriesMark,
  seriesValuesToVegaLite,
  text,
  titleText,
  type JsonRecord,
  type SeriesValue,
} from "@/lib/chartSeriesSpec";
import { isJsonRecord as isRecord } from "@/lib/jsonFence";

const LABEL_KEYS = ["labels", "categories", "x"];
const AXIS_LABEL_KEYS = ["labels", "categories", "values", "data"];
const SERIES_KEYS = ["series", "datasets"];
const VALUE_KEYS = ["values", "data", "y"];
const PIE_TYPES = new Set(["pie", "donut", "doughnut"]);
// A Vega-Lite or Vega spec, or a Chart.js config (`data: {labels, datasets}`): read elsewhere.
const SPEC_KEYS = ["mark", "layer", "$schema", "marks", "encoding"];
const CSS_COLOR = /^(#[0-9a-f]{3,8}|[a-z]{3,20}|(rgb|hsl)a?\([^()]{1,40}\))$/i;

type Label = string | number;
type Point = { x: Label; y: number };
type Series = { name: string; values: unknown[]; type?: unknown; color?: string };

function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function firstArray(block: JsonRecord | undefined, keys: string[]): unknown[] | undefined {
  if (!block) return undefined;
  for (const key of keys) {
    const value = block[key];
    if (Array.isArray(value)) return value;
  }
  return undefined;
}

/** The category labels from the chart or its x axis block; undefined when it has none, null when unreadable. */
function categoryLabels(spec: JsonRecord): Label[] | null | undefined {
  const labels = firstArray(spec, LABEL_KEYS) ?? firstArray(axisBlock(spec, "x"), AXIS_LABEL_KEYS);
  if (!labels) return undefined;
  return labels.every((label) => typeof label === "string" || finite(label)) ? (labels as Label[]) : null;
}

/** `series` / `datasets` items with `values` / `data` / `y`, or one series written at the top level. */
function seriesList(spec: JsonRecord): Series[] | null {
  for (const key of SERIES_KEYS) {
    const list = spec[key];
    if (!Array.isArray(list) || list.length === 0) continue;
    // `"series": [12, 18, 9]`: one unnamed series.
    if (!list.some(isRecord)) return [{ name: axisTitle(spec, "y") ?? "Value", values: list }];
    const read: Series[] = [];
    for (const [index, item] of list.entries()) {
      const values = isRecord(item) ? firstArray(item, VALUE_KEYS) : undefined;
      if (!isRecord(item) || !values) return null;
      const color = text(item.color);
      read.push({
        name: text(item.name) ?? text(item.label) ?? `Series ${index + 1}`,
        values,
        type: item.type,
        color: color && CSS_COLOR.test(color) ? color : undefined,
      });
    }
    return read;
  }
  const values = firstArray(spec, VALUE_KEYS);
  const name = axisTitle(spec, "y") ?? text(spec.name) ?? text(spec.label) ?? "Value";
  return values ? [{ name, values }] : null;
}

/** `[x, y]`, `{x, y}`, `["Rent", 1200]` or a labelled value (`{"name", "y"}`, `{"label", "value"}`). */
function labelledPoint(value: unknown): Point | null {
  const pair = readPoint(value);
  if (pair) return { x: pair[0], y: pair[1] };
  if (Array.isArray(value) && value.length === 2 && typeof value[0] === "string" && finite(value[1])) {
    return { x: value[0], y: value[1] };
  }
  if (!isRecord(value)) return null;
  const x = value.x ?? value.name ?? value.label ?? value.category;
  const y = value.y ?? value.value;
  return (typeof x === "string" || finite(x)) && finite(y) ? { x, y } : null;
}

/**
 * One series' values against the labels. A bare number takes the label at its place, so the
 * labels must be exactly as many as the values; a null is a gap. `asCategory` keeps a numeric
 * label as written text: years on a bar or line axis are names, not quantities.
 */
function readValues(values: unknown[], labels: Label[] | undefined, asCategory: boolean): Point[] | null {
  const numbers = values.some((value) => typeof value === "number");
  if (numbers && (!labels || labels.length !== values.length)) return null;
  const points: Point[] = [];
  for (const [at, value] of values.entries()) {
    if (value === null) continue;
    if (typeof value === "number") {
      if (!finite(value) || !labels) return null;
      points.push({ x: asCategory ? String(labels[at]) : labels[at], y: value });
      continue;
    }
    const point = labelledPoint(value);
    if (!point) return null;
    points.push(point);
  }
  return points;
}

/**
 * The y axis block's `min` / `max`, kept only when the data sits inside them. A stack (areas,
 * or bars that are not side by side) can rise past every single value, so its max goes.
 */
function withValueRange(
  spec: JsonRecord,
  yAxis: JsonRecord | undefined,
  values: SeriesValue[],
  stacks: boolean,
): JsonRecord {
  if (!yAxis) return spec;
  const ys = values.map((row) => row.y);
  const scale: JsonRecord = {};
  if (finite(yAxis.min) && yAxis.min <= Math.min(...ys)) scale.domainMin = yAxis.min;
  if (finite(yAxis.max) && !stacks && yAxis.max >= Math.max(...ys)) scale.domainMax = yAxis.max;
  if (Object.keys(scale).length === 0) return spec;
  const encoding = spec.encoding as JsonRecord;
  return { ...spec, encoding: { ...encoding, y: { ...(encoding.y as JsonRecord), scale } } };
}

/**
 * Every label on the category axis, in the order given: a null value is a gap at its label.
 * Left to the rows, "Tue" with no value vanished and the line joined Mon to Wed.
 */
function withCategoryDomain(spec: JsonRecord, labels: Label[] | undefined): JsonRecord {
  const encoding = spec.encoding as JsonRecord;
  if (!labels || !isRecord(encoding.x) || encoding.x.type !== "ordinal") return spec;
  const scale = isRecord(encoding.x.scale) ? encoding.x.scale : {};
  const x = { ...encoding.x, scale: { ...scale, domain: labels.map(String) } };
  return { ...spec, encoding: { ...encoding, x } };
}

/** The colours the series asked for, when every one of them named one. */
function withColors(spec: JsonRecord, series: Series[]): JsonRecord {
  const colors = series.map((line) => line.color);
  if (!colors.every(Boolean)) return spec;
  if (series.length === 1) {
    return typeof spec.mark === "string" ? { ...spec, mark: { type: spec.mark, color: colors[0] } } : spec;
  }
  const encoding = spec.encoding as JsonRecord;
  if (!isRecord(encoding.color)) return spec;
  const scale = { domain: series.map((line) => line.name), range: colors };
  return { ...spec, encoding: { ...encoding, color: { ...encoding.color, scale } } };
}

/** The chart as Vega-Lite, or null when `spec` is not a categories-and-series chart. */
export function categoryChartToVegaLite(spec: JsonRecord): JsonRecord | null {
  if (SPEC_KEYS.some((key) => key in spec) || isRecord(spec.data)) return null;
  const labels = categoryLabels(spec);
  const series = labels === null ? null : seriesList(spec);
  if (labels === null || !series) return null;
  const chartType = String(spec.type ?? (isRecord(spec.chart) ? spec.chart.type : undefined) ?? "").toLowerCase();
  const title = titleText(spec.title);
  if (PIE_TYPES.has(chartType)) {
    // One pie: the first series' slices.
    const slices = readValues(series[0].values, labels, true);
    if (!slices || slices.length === 0) return null;
    const values = slices.map((slice) => ({ ...slice, series: series[0].name }));
    return pieValuesToVegaLite(values, title, chartType !== "pie");
  }
  const chartMark = seriesMark(chartType, labels ? "bar" : "line");
  const values: SeriesValue[] = [];
  const marks = new Map<string, string>();
  for (const line of series) {
    const mark = seriesMark(line.type, chartMark);
    const points = readValues(line.values, labels, mark !== "point");
    if (!points) return null;
    marks.set(line.name, mark);
    for (const point of points) values.push({ ...point, series: line.name });
  }
  if (values.length === 0) return null;
  const drawn = seriesValuesToVegaLite({
    values,
    marks,
    title,
    xTitle: axisTitle(spec, "x"),
    // One series names its own axis; several are named by the legend.
    yTitle: axisTitle(spec, "y") ?? (marks.size === 1 ? [...marks.keys()][0] : null),
  });
  // Areas stack, and so do bars of several series unless they stand side by side.
  const kinds = [...marks.values()];
  const count = (mark: string) => kinds.filter((kind) => kind === mark).length;
  const sideBySide = isRecord(drawn.encoding) && "xOffset" in drawn.encoding;
  const stacks = count("area") > 1 || (count("bar") > 1 && !sideBySide);
  const ranged = withValueRange(drawn, axisBlock(spec, "y"), values, stacks);
  return withColors(withCategoryDomain(ranged, labels), series);
}
