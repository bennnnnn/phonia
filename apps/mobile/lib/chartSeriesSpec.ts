/**
 * A chart fence's body, read the way a model may have written it. A caption line
 * before the JSON (`x^2 over [-5, 5]`) or a `{"type":"line","series":[…]}` chart
 * instead of Vega-Lite drew "JSON Parse error" in the bubble; both now draw.
 */

import { isJsonRecord as isRecord } from "@/lib/jsonFence";

export type JsonRecord = Record<string, unknown>;

/** Where the object opening at `open` closes, or -1. Braces inside strings do not count. */
function closingBrace(raw: string, open: number): number {
  let depth = 0;
  let inString = false;
  for (let i = open; i < raw.length; i += 1) {
    const ch = raw[i];
    if (inString) {
      if (ch === "\\") i += 1;
      else if (ch === '"') inString = false;
    } else if (ch === '"') {
      inString = true;
    } else if (ch === "{") {
      depth += 1;
    } else if (ch === "}") {
      depth -= 1;
      if (depth === 0) return i;
    }
  }
  return -1;
}

function parseOrNull(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/**
 * The JSON in a chart body, or null. Lines of prose around the object are dropped,
 * and so is anything after its closing brace: a stray `}` or a `"config"` written
 * past the end left the whole body unreadable.
 */
export function parseChartBody(raw: string): unknown {
  const whole = parseOrNull(raw);
  if (whole !== null) return whole;
  const open = raw.indexOf("{");
  if (open === -1) return null;
  const close = closingBrace(raw, open);
  const first = close === -1 ? null : parseOrNull(raw.slice(open, close + 1));
  if (first !== null) return first;
  const last = raw.lastIndexOf("}");
  return last > open ? parseOrNull(raw.slice(open, last + 1)) : null;
}

const SERIES_MARKS: Record<string, string> = {
  line: "line",
  bar: "bar",
  column: "bar",
  horizontalbar: "bar",
  area: "area",
  scatter: "point",
  point: "point",
};

/** The Vega-Lite mark for a chart or series `type`, or `fallback`. */
export function seriesMark(type: unknown, fallback: string): string {
  return SERIES_MARKS[String(type ?? "").toLowerCase()] ?? fallback;
}

/** A point as `[x, y]` or `{ "x": …, "y": … }`. */
export function readPoint(point: unknown): [number, number] | null {
  const pair = Array.isArray(point) ? point : isRecord(point) ? [point.x, point.y] : null;
  if (!pair || typeof pair[0] !== "number" || typeof pair[1] !== "number") return null;
  return [pair[0], pair[1]];
}

export function text(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

export type SeriesValue = { x: number | string; y: number; series: string };

/**
 * Rows of `{x, y, series}` as Vega-Lite. Each series keeps its own mark: a scatter
 * with a `"type": "line"` best-fit series drew that line as two stray points.
 */
export function seriesValuesToVegaLite({
  values,
  marks,
  title,
  xTitle,
  yTitle,
}: {
  values: SeriesValue[];
  /** Series name → mark, in the order the series came. */
  marks: Map<string, string>;
  title?: string;
  xTitle?: string;
  /** Null leaves the value axis untitled; undefined calls it "y". */
  yTitle?: string | null;
}): JsonRecord {
  const numericX = values.every((row) => typeof row.x === "number");
  const kinds = [...new Set(marks.values())];
  const grouped = marks.size > 1 && kinds.length === 1 && kinds[0] === "bar" && !numericX;
  const encoding = {
    x: numericX
      ? { field: "x", type: "quantitative", title: xTitle ?? "x" }
      : { field: "x", type: "ordinal", sort: null, title: xTitle ?? null },
    y: { field: "y", type: "quantitative", title: yTitle === undefined ? "y" : yTitle },
    ...(marks.size > 1 ? { color: { field: "series", type: "nominal", sort: null, title: null } } : {}),
    // Bars of two series side by side, not stacked into one.
    ...(grouped ? { xOffset: { field: "series", sort: null } } : {}),
  };
  const layered =
    kinds.length > 1
      ? {
          layer: kinds.map((mark) => ({
            mark,
            transform: [
              {
                filter: {
                  field: "series",
                  oneOf: [...marks].filter(([, m]) => m === mark).map(([name]) => name),
                },
              },
            ],
          })),
        }
      : { mark: kinds[0] ?? "line" };
  return {
    $schema: "https://vega.github.io/schema/vega-lite/v5.json",
    ...(title ? { title } : {}),
    data: { values },
    encoding,
    ...layered,
  };
}

/** A title as a string or as `{"text": …}`, the way Chart.js and Highcharts write one. */
export function titleText(value: unknown): string | undefined {
  return text(value) ?? (isRecord(value) ? text(value.text) : undefined);
}

/** An axis block: `xAxis`, `x_axis` or `xaxis`. */
export function axisBlock(spec: JsonRecord, axis: "x" | "y"): JsonRecord | undefined {
  const block = spec[`${axis}Axis`] ?? spec[`${axis}_axis`] ?? spec[`${axis}axis`];
  return isRecord(block) ? block : undefined;
}

/** An axis title from `xLabel`, `x_label` or the axis block's `label` / `title`. */
export function axisTitle(spec: JsonRecord, axis: "x" | "y"): string | undefined {
  const block = axisBlock(spec, axis);
  return (
    text(spec[`${axis}Label`]) ??
    text(spec[`${axis}_label`]) ??
    (block ? (text(block.label) ?? titleText(block.title)) : undefined)
  );
}

/** Slices of `{x: label, y: value}` as a Vega-Lite pie (or a donut), in the order given. */
export function pieValuesToVegaLite(values: SeriesValue[], title?: string, donut = false): JsonRecord {
  return {
    $schema: "https://vega.github.io/schema/vega-lite/v5.json",
    ...(title ? { title } : {}),
    data: { values },
    mark: donut ? { type: "arc", innerRadius: 50 } : { type: "arc" },
    encoding: {
      theta: { field: "y", type: "quantitative" },
      color: { field: "x", type: "nominal", sort: null, title: null },
    },
  };
}

// A box plot by any of the names models give it.
const BOX_TYPES = new Set(["box", "boxplot", "box plot", "box-plot", "box and whisker", "box-and-whisker"]);

/**
 * `{"type": "boxplot", "series": [{"name", "values": [numbers]}]}` as a Vega-Lite box plot,
 * one box per series. Vega-Lite works out the quartiles and whiskers from the raw values.
 */
function boxSeriesToVegaLite(spec: JsonRecord, series: unknown[]): JsonRecord | null {
  const values: { group: string; value: number }[] = [];
  for (const [index, entry] of series.entries()) {
    const raw = isRecord(entry) ? (entry.values ?? entry.data) : undefined;
    if (!isRecord(entry) || !Array.isArray(raw)) return null;
    const group = text(entry.name) ?? text(entry.label) ?? `Series ${index + 1}`;
    for (const value of raw) {
      if (typeof value !== "number" || !Number.isFinite(value)) return null;
      values.push({ group, value });
    }
  }
  if (values.length === 0) return null;
  const title = titleText(spec.title);
  return {
    $schema: "https://vega.github.io/schema/vega-lite/v5.json",
    ...(title ? { title } : {}),
    data: { values },
    mark: { type: "boxplot", extent: 1.5 },
    encoding: {
      ...(series.length > 1
        ? { x: { field: "group", type: "nominal", sort: null, title: axisTitle(spec, "x") ?? null } }
        : {}),
      y: { field: "value", type: "quantitative", title: axisTitle(spec, "y") ?? "value" },
    },
  };
}

/**
 * `{"type", "title", "xLabel", "yLabel", "series": [{"name", "type"?, "points": [[x, y], …]}]}`
 * (axis labels may also come as `"x_axis": {"label"}`) as Vega-Lite. Null for anything
 * else: a real Vega or Vega-Lite spec is left as written, and a series given as a
 * formula instead of points is not drawn here (the server owns curves).
 */
export function seriesChartToVegaLite(spec: JsonRecord): JsonRecord | null {
  if ("mark" in spec || "layer" in spec || "$schema" in spec || "data" in spec) return null;
  const series = spec.series;
  if (!Array.isArray(series) || series.length === 0) return null;
  if (BOX_TYPES.has(String(spec.type ?? "").toLowerCase())) return boxSeriesToVegaLite(spec, series);
  const chartMark = seriesMark(spec.type, "line");
  const values: SeriesValue[] = [];
  const marks = new Map<string, string>();
  for (const [index, line] of series.entries()) {
    if (!isRecord(line) || !Array.isArray(line.points)) return null;
    const name = text(line.name) ?? `Series ${index + 1}`;
    marks.set(name, seriesMark(line.type, chartMark));
    for (const point of line.points) {
      const read = readPoint(point);
      if (!read) return null;
      values.push({ x: read[0], y: read[1], series: name });
    }
  }
  return seriesValuesToVegaLite({
    values,
    marks,
    title: titleText(spec.title),
    xTitle: axisTitle(spec, "x"),
    yTitle: axisTitle(spec, "y"),
  });
}
