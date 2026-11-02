/**
 * How a chart spec is laid out for a phone card, decided on the phone each time a chart
 * draws, so a reply stored before a fix draws with it too. Every rule fills in only what
 * the spec left unset; an explicit sort, scale, axis format or legend stays as written.
 *
 * - Bars stand as columns for months, weekdays, quarters, years or a few short names, and lie
 *   across the card for many or long names; categories keep the order the data gives them.
 * - Colour, fill and stroke categories keep the order the data gives them (legend, slices).
 * - Lines and points are not pinned to zero: 80 → 75 kg was a flat line along the top.
 * - Large numbers on a value axis are written short (12.5k, 4.1M, 7.8B): a 300 px card cut
 *   "4,000,000,000" to "4,000,000,0".
 * - A title longer than the card wraps: a wide title shrank the plot under it to fit beside it.
 * - Tooltips are dropped (the card shows none), and pre-binned bars get their bin end.
 */
import { type JsonRecord } from "@/lib/chartSeriesSpec";
import { isJsonRecord as isRecord } from "@/lib/jsonFence";

const COMPOSITE_KEYS = ["layer", "hconcat", "vconcat", "concat"] as const;
const BAND_PX = 28;
const BAND_HEIGHT_MIN = 120;
const BAND_HEIGHT_MAX = 280;
// Marks that read from where the data is, not from zero; rules and text ride along.
const UNPINNED_MARKS = new Set(["line", "point", "circle", "square", "trail"]);
const NEUTRAL_MARKS = new Set(["rule", "text", "tick"]);
const COLOR_CHANNELS = ["color", "fill", "stroke"] as const;
const LABEL_FORMAT_KEYS = ["format", "formatType", "labelExpr"];
// A bold 13 px title runs about 8 px a character.
const TITLE_PX_PER_CHAR = 8;

/**
 * An axis label written short: 12.5k from 1e4, 12.5M from 1e6, 4B from 1e9; smaller values as
 * Vega formats them. Given the axis's scale, the size of its largest end picks one unit for
 * every label on it (0, 5k, 10k, 15k rather than 0, 5,000, 10k, 15k).
 */
export function compactLabelExpr(scale: string | null): string {
  const size = scale ? `max(abs(domain('${scale}')[0]), abs(peek(domain('${scale}'))))` : "abs(datum.value)";
  return (
    `${size} >= 1e4 ? (datum.value === 0 ? '0' : ` +
    `${size} >= 1e9 ? format(datum.value / 1e9, '.4~r') + 'B' : ` +
    `${size} >= 1e6 ? format(datum.value / 1e6, '.4~r') + 'M' : ` +
    `format(datum.value / 1e3, '.4~r') + 'k') : datum.label`
  );
}

function markType(mark: unknown): string | undefined {
  if (typeof mark === "string") return mark;
  return isRecord(mark) && typeof mark.type === "string" ? mark.type : undefined;
}

function channelType(ch: unknown): string | undefined {
  return isRecord(ch) && typeof ch.type === "string" ? ch.type : undefined;
}

function isCategoryType(t: string | undefined): boolean {
  return t === "nominal" || t === "ordinal";
}

function applyNominalSort(encoding: JsonRecord, key: string): void {
  const chan = encoding[key];
  if (!isRecord(chan) || "sort" in chan) return;
  if (chan.type === "quantitative" || chan.type === "temporal") return;
  chan.sort = null;
}

// A 10 px axis label runs about 6 px a character and needs a little air beside it; the value
// axis's numbers and title take about 56 px of the card's width.
const LABEL_PX_PER_CHAR = 6;
const LABEL_GAP_PX = 6;
const VALUE_AXIS_PX = 56;
// Time labels stand as columns up to this many; crowded ones show every other label.
const TIME_COLUMN_MAX = 16;
const TIME_LABEL =
  /^(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:r(?:s(?:day)?)?)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?|q[1-4](?:\s+\d{4})?|(?:19|20)\d\d(?:\/\d{2})?|(?:week|month|day|year|wk)\s*\d{1,2}|\d{4}-\d{2}(?:-\d{2})?)$/i;

/** The category labels a bar chart's rows give, in order; null when it cannot tell. */
function categoryLabels(spec: JsonRecord, field: unknown): string[] | null {
  const values = isRecord(spec.data) ? spec.data.values : undefined;
  if (typeof field !== "string" || !Array.isArray(values)) return null;
  const labels: string[] = [];
  for (const row of values) {
    if (!isRecord(row) || row[field] == null) continue;
    const label = String(row[field]).trim();
    if (!labels.includes(label)) labels.push(label);
  }
  return labels.length ? labels : null;
}

const isTimeLabels = (labels: string[]): boolean => labels.every((label) => TIME_LABEL.test(label));

/** Whether these labels stand as columns on a card `width` px wide: in time order, or upright. */
function fitsAsColumns(labels: string[], width: number): boolean {
  if (isTimeLabels(labels)) return labels.length <= TIME_COLUMN_MAX;
  const band = (width - VALUE_AXIS_PX) / labels.length;
  const longest = Math.max(...labels.map((label) => label.length));
  return longest * LABEL_PX_PER_CHAR + LABEL_GAP_PX <= band;
}

/** Column labels read upright; crowded time labels drop every other one, never overlap. */
function uprightLabels(ch: unknown, labels: string[]): void {
  if (!isRecord(ch) || ch.axis === null) return;
  const axis = isRecord(ch.axis) ? ch.axis : {};
  const upright: JsonRecord = { labelAngle: 0 };
  if (isTimeLabels(labels)) upright.labelOverlap = "parity";
  ch.axis = { ...upright, ...axis };
}

/** A sort that names a channel ("-x", {"encoding": "y"}) names the other one once bars turn. */
function turnedSort(sort: unknown): unknown {
  const other = (key: unknown) => (key === "x" ? "y" : key === "y" ? "x" : key);
  if (typeof sort === "string") return sort.startsWith("-") ? `-${other(sort.slice(1))}` : other(sort);
  return isRecord(sort) && "encoding" in sort ? { ...sort, encoding: other(sort.encoding) } : sort;
}

/** Bars turned a quarter: every x channel trades places with its y twin, sorts follow. */
function turnBars(enc: JsonRecord): void {
  for (const [a, b] of [["x", "y"], ["x2", "y2"], ["xOffset", "yOffset"]] as const) {
    const [first, second] = [enc[a], enc[b]];
    if (second === undefined) delete enc[a];
    else enc[a] = second;
    if (first === undefined) delete enc[b];
    else enc[b] = first;
  }
  for (const key of ["x", "y"] as const) {
    const ch = enc[key];
    if (isRecord(ch) && "sort" in ch) ch.sort = turnedSort(ch.sort);
  }
}

/**
 * A bar chart's direction, chosen for its labels and the card's width whichever way the model
 * wrote it: months, weekdays, quarters and years stand as columns, as do names that fit
 * upright under their columns; other names lie across the card, where they stay readable.
 * A plot that does not fill the card (a facet's or concat's panel) keeps the written direction.
 */
function orientBars(spec: JsonRecord, width: number | null): void {
  if (width === null || markType(spec.mark) !== "bar" || !isRecord(spec.encoding)) return;
  const enc = spec.encoding;
  const across = isCategoryType(channelType(enc.y)) && channelType(enc.x) === "quantitative";
  const standing = isCategoryType(channelType(enc.x)) && channelType(enc.y) === "quantitative";
  if (!across && !standing) return;
  const category = across ? enc.y : enc.x;
  const labels = categoryLabels(spec, isRecord(category) ? category.field : undefined);
  const columns = labels ? fitsAsColumns(labels, width) : standing;
  if (columns && labels) uprightLabels(category, labels);
  if (columns === standing) return;
  // An angle written for labels under columns tilted them once they lay down the side.
  if (!columns && isRecord(category) && isRecord(category.axis)) delete category.axis.labelAngle;
  turnBars(enc);
}

function setHorizontalBandHeight(spec: JsonRecord): void {
  if (markType(spec.mark) !== "bar" || spec.height != null || !isRecord(spec.encoding)) return;
  if (!isCategoryType(channelType(spec.encoding.y))) return;
  const values = isRecord(spec.data) ? spec.data.values : undefined;
  const n = Array.isArray(values) ? values.length : 6;
  spec.height = Math.min(BAND_HEIGHT_MAX, Math.max(BAND_HEIGHT_MIN, n * BAND_PX));
}

/** The end field a spec's `bin` transform writes beside `start`, if it has one. */
function binEndField(spec: JsonRecord, start: unknown): string | undefined {
  const steps = Array.isArray(spec.transform) ? spec.transform : [];
  for (const step of steps) {
    if (!isRecord(step) || !("bin" in step)) continue;
    const as = step.as;
    if (Array.isArray(as) && as[0] === start && typeof as[1] === "string") return as[1];
    if (typeof as === "string" && as === start) return `${as}_end`;
  }
  return undefined;
}

/**
 * Bars a model pre-binned (`"bin": "binned"`) need the bin's end on x2 / y2; without
 * it Vega-Lite drew no bars at all. The end comes from the spec's own bin transform,
 * or the channel draws plain bars at each bin's start.
 */
function pairBinnedEdges(spec: JsonRecord, enc: JsonRecord): void {
  for (const axis of ["x", "y"] as const) {
    const ch = enc[axis];
    if (!isRecord(ch) || ch.bin !== "binned" || enc[`${axis}2`] !== undefined) continue;
    const end = binEndField(spec, ch.field);
    if (end) enc[`${axis}2`] = { field: end };
    else delete ch.bin;
  }
}

function normalizeUnit(spec: JsonRecord, width: number | null): void {
  orientBars(spec, width);
  if (isRecord(spec.encoding)) {
    const enc = spec.encoding;
    applyNominalSort(enc, "x");
    applyNominalSort(enc, "y");
    // The card shows no tooltips, and a tooltip's bad format string threw inside
    // Vega's dataflow and left the chart blank.
    delete enc.tooltip;
    pairBinnedEdges(spec, enc);
  }
  setHorizontalBandHeight(spec);
}

type ViewVisit = (view: JsonRecord, inLayer: boolean, fillsCard: boolean) => void;

function isFaceted(view: JsonRecord): boolean {
  const enc = view.encoding;
  return isRecord(enc) && ["row", "column", "facet"].some((key) => key in enc);
}

/**
 * Every view in a spec, with whether it is one layer of a layered plot and whether it is
 * drawn the card's width: the page widens only a top-level plot (layers included) that is
 * not faceted; a facet's, repeat's or concat's panels keep Vega-Lite's 20 px step.
 */
function eachView(spec: JsonRecord, visit: ViewVisit, inLayer = false, fillsCard = true): void {
  const fills = fillsCard && !isFaceted(spec);
  visit(spec, inLayer, fills);
  for (const key of COMPOSITE_KEYS) {
    const kids = spec[key];
    if (!Array.isArray(kids)) continue;
    const layer = key === "layer";
    for (const kid of kids) if (isRecord(kid)) eachView(kid, visit, inLayer || layer, fills && layer);
  }
  if (isRecord(spec.spec)) eachView(spec.spec, visit, false, false);
}

/** Layout + category order for a Vega-Lite spec on a card `width` px wide (mutates). */
export function normalizeChartSpec(spec: JsonRecord, width = 320): void {
  eachView(spec, (view, _inLayer, fillsCard) => normalizeUnit(view, fillsCard ? width : null));
}

/** Whether a channel holds categories: said so, or a plain field Vega-Lite reads as nominal. */
function holdsCategories(ch: JsonRecord): boolean {
  const type = channelType(ch);
  if (type !== undefined) return isCategoryType(type);
  return "field" in ch && !["aggregate", "bin", "timeUnit"].some((key) => key in ch);
}

/** A nominal colour, fill or stroke with no sort keeps the data's order. */
function keepColorOrder(view: JsonRecord): void {
  if (!isRecord(view.encoding)) return;
  for (const key of COLOR_CHANNELS) {
    const ch = view.encoding[key];
    if (isRecord(ch) && holdsCategories(ch) && !("sort" in ch)) ch.sort = null;
  }
}

/** The marks a plot draws: its own, or every layer's. */
function plotMarks(view: JsonRecord): string[] {
  if (Array.isArray(view.layer)) return view.layer.flatMap((kid) => (isRecord(kid) ? plotMarks(kid) : []));
  const mark = markType(view.mark);
  return mark ? [mark] : [];
}

function plotEncodings(view: JsonRecord): JsonRecord[] {
  const own = isRecord(view.encoding) ? [view.encoding] : [];
  const kids = Array.isArray(view.layer) ? view.layer.filter(isRecord) : [];
  return [...own, ...kids.flatMap(plotEncodings)];
}

/** Said to be quantitative, or a count, sum or bin Vega-Lite reads as one. */
function isQuantitative(ch: JsonRecord): boolean {
  if (ch.type !== undefined) return ch.type === "quantitative";
  return typeof ch.aggregate === "string" || Boolean(ch.bin);
}

function unpinFromZero(ch: unknown): void {
  if (!isRecord(ch) || ch.bin || ch.scale === null || !isQuantitative(ch)) return;
  const scale = isRecord(ch.scale) ? ch.scale : {};
  if (["zero", "domain", "domainMin", "domainMax"].some((key) => key in scale)) return;
  ch.scale = { ...scale, zero: false };
}

/** A line or scatter plot's quantitative axes start where the data does, not at zero. */
function unpinLines(view: JsonRecord, inLayer: boolean): void {
  if (inLayer) return;
  const marks = plotMarks(view);
  if (!marks.some((mark) => UNPINNED_MARKS.has(mark))) return;
  if (!marks.every((mark) => UNPINNED_MARKS.has(mark) || NEUTRAL_MARKS.has(mark))) return;
  for (const encoding of plotEncodings(view)) {
    unpinFromZero(encoding.x);
    unpinFromZero(encoding.y);
  }
}

function setsLabelFormat(block: unknown): boolean {
  return isRecord(block) && LABEL_FORMAT_KEYS.some((key) => key in block);
}

/** Whether the spec's config formats axis labels for every axis. */
function configFormatsLabels(spec: JsonRecord): boolean {
  const config = isRecord(spec.config) ? spec.config : {};
  if ("numberFormat" in config) return true;
  return Object.entries(config).some(([key, block]) => key.startsWith("axis") && setsLabelFormat(block));
}

/**
 * Each value axis with no format of its own writes large numbers short. In one plot (a unit
 * or layered spec) an axis's scale is named after its channel; elsewhere each label is sized alone.
 */
function compactAxisLabels(spec: JsonRecord): void {
  if (configFormatsLabels(spec)) return;
  const encoding = isRecord(spec.encoding) ? spec.encoding : {};
  const faceted = ["row", "column", "facet"].some((key) => key in encoding);
  const onePlot = ("mark" in spec || "layer" in spec) && !("resolve" in spec) && !faceted;
  eachView(spec, (view) => {
    if (!isRecord(view.encoding)) return;
    for (const key of ["x", "y"] as const) {
      const ch = view.encoding[key];
      if (!isRecord(ch) || !isQuantitative(ch) || ch.axis === null) continue;
      const axis = isRecord(ch.axis) ? ch.axis : {};
      // A log scale's ticks span powers of ten: one unit for the axis drew "0.001k … 100k".
      const logScale = isRecord(ch.scale) && ["log", "symlog"].includes(String(ch.scale.type));
      const sized = onePlot && !logScale ? key : null;
      if (!setsLabelFormat(axis)) ch.axis = { ...axis, labelExpr: compactLabelExpr(sized) };
    }
  });
}

/** Words as lines of at most `chars` characters (a longer word keeps a line to itself). */
function wrapWords(text: string, chars: number): string[] {
  const lines: string[] = [];
  for (const word of text.split(/\s+/).filter(Boolean)) {
    const last = lines[lines.length - 1];
    if (last !== undefined && last.length + 1 + word.length <= chars) lines[lines.length - 1] = `${last} ${word}`;
    else lines.push(word);
  }
  return lines;
}

/** A title wider than the card as lines that fit it. */
function wrapTitle(spec: JsonRecord, width: number): void {
  const chars = Math.max(16, Math.floor(width / TITLE_PX_PER_CHAR));
  const title = spec.title;
  if (typeof title === "string" && title.length > chars) spec.title = wrapWords(title, chars);
  else if (isRecord(title) && typeof title.text === "string" && title.text.length > chars) {
    title.text = wrapWords(title.text, chars);
  }
}

/** One template literal's body as a Vega string expression, parenthesised and always text. */
function templateToConcat(body: string): string {
  const parts: string[] = [];
  let rest = body;
  while (rest) {
    const open = rest.indexOf("${");
    const close = open < 0 ? -1 : rest.indexOf("}", open);
    const text = close < 0 ? rest : rest.slice(0, open);
    if (text) parts.push(`'${text.replace(/\\/g, "\\\\").replace(/'/g, "\\'")}'`);
    if (close < 0) break;
    parts.push(`(${rest.slice(open + 2, close)})`);
    rest = rest.slice(close + 1);
  }
  // Text first, so "${a}${b}" joins rather than adds, and a lone "${n}" stays text.
  if (parts.length === 0 || !parts[0].startsWith("'")) parts.unshift("''");
  return `(${parts.join(" + ")})`;
}

/**
 * A JavaScript template literal (`` `Grade ${datum.grade}` ``) as Vega's expression
 * language writes it, `('Grade ' + (datum.grade))`: Vega cannot read backticks, and a stacked
 * bar chart with one unused label drew "Unexpected token ILLEGAL" instead of its bars. A
 * backtick inside a quoted string ("'`'") is that string's text and stays as written.
 */
export function withoutTemplateLiterals(expr: string): string {
  let out = "";
  let quote: string | null = null;
  for (let i = 0; i < expr.length; i += 1) {
    const ch = expr[i];
    if (quote) {
      out += ch;
      if (ch === "\\" && i + 1 < expr.length) out += expr[++i];
      else if (ch === quote) quote = null;
    } else if (ch === "'" || ch === '"') {
      quote = ch;
      out += ch;
    } else if (ch === "`") {
      const end = expr.indexOf("`", i + 1);
      if (end < 0) return expr;
      out += templateToConcat(expr.slice(i + 1, end));
      i = end;
    } else {
      out += ch;
    }
  }
  return out;
}

/** The field names a view's own inline rows carry; null when it has data of another kind. */
function rowFields(view: JsonRecord, inherited: Set<string> | null): Set<string> | null {
  if (!("data" in view)) return inherited;
  const data = isRecord(view.data) ? view.data : null;
  const rows = data && Array.isArray(data.values) ? data.values : null;
  const first = rows?.find(isRecord);
  return first ? new Set(Object.keys(first)) : null;
}

/** Every field a transform step names as its output ("as", however nested). */
function outputsOf(step: unknown, into: Set<string>): void {
  if (Array.isArray(step)) for (const item of step) outputsOf(item, into);
  if (!isRecord(step)) return;
  for (const [key, value] of Object.entries(step)) {
    if (key === "as") {
      for (const name of Array.isArray(value) ? value : [value]) if (typeof name === "string") into.add(name);
    } else if (typeof value === "object") {
      outputsOf(value, into);
    }
  }
  if ("fold" in step && !("as" in step)) ["key", "value"].forEach((name) => into.add(name));
}

/**
 * Transforms a model wrote that cannot run: a best-fit line on a field the rows do not have
 * ({"regression": "y", "on": "x"} over hours and score drew nothing at all) takes the plot's
 * own field for it, and a template literal becomes a Vega expression. Fields an earlier step
 * makes ("as") count as known; a view with data of its own kind is left as written.
 */
function repairTransforms(view: JsonRecord, fields: Set<string> | null, encoding: JsonRecord | null): void {
  const rows = rowFields(view, fields);
  const known = rows ? new Set(rows) : null;
  const enc = isRecord(view.encoding) ? view.encoding : encoding;
  for (const step of Array.isArray(view.transform) ? view.transform : []) {
    if (!isRecord(step)) continue;
    for (const key of ["calculate", "filter"]) {
      if (typeof step[key] === "string") step[key] = withoutTemplateLiterals(step[key] as string);
    }
    const fit = ["regression", "loess"].find((key) => typeof step[key] === "string");
    if (fit && known && enc) {
      const x = isRecord(enc.x) ? enc.x.field : undefined;
      const y = isRecord(enc.y) ? enc.y.field : undefined;
      if (!known.has(String(step[fit])) && typeof y === "string" && known.has(y)) step[fit] = y;
      if (!known.has(String(step.on)) && typeof x === "string" && known.has(x)) step.on = x;
    }
    if (known) outputsOf(step, known);
  }
  for (const key of COMPOSITE_KEYS) {
    const kids = view[key];
    if (Array.isArray(kids)) for (const kid of kids) if (isRecord(kid)) repairTransforms(kid, known, enc);
  }
  if (isRecord(view.spec)) repairTransforms(view.spec, known, enc);
}

// A slice too thin to hold its share: no label (the legend still names it).
const SLICE_LABEL_MIN_SHARE = 0.05;

/**
 * A pie or donut with each slice's share written on it: the slices told no numbers, and a
 * budget pie could not be read. The arc and its label share the stacked angle, so each label
 * sits mid-slice. The field reaches the expression only as a JSON string literal.
 */
function labelSlices(spec: JsonRecord): JsonRecord {
  const mark = spec.mark;
  const encoding = isRecord(spec.encoding) ? spec.encoding : null;
  const theta = encoding && isRecord(encoding.theta) ? encoding.theta : null;
  if (markType(mark) !== "arc" || "layer" in spec || !encoding || !theta) return spec;
  const field = theta.field;
  if (typeof field !== "string" || /[.[\]]/.test(field) || "aggregate" in theta || "text" in encoding) return spec;
  const inner = isRecord(mark) && typeof mark.innerRadius === "number" ? mark.innerRadius : 0;
  const radius = inner ? `(min(width, height) / 2 + ${inner}) / 2` : "min(width, height) / 2 * 0.62";
  const value = `datum[${JSON.stringify(field)}]`;
  const share = `${value} / datum.__total`;
  const transform = Array.isArray(spec.transform) ? spec.transform : [];
  return {
    ...spec,
    mark: undefined,
    transform: [
      ...transform,
      { joinaggregate: [{ op: "sum", field, as: "__total" }] },
      { calculate: `${share} >= ${SLICE_LABEL_MIN_SHARE} ? format(${share}, '.0%') : ''`, as: "__share" },
    ],
    encoding: { ...encoding, theta: { ...theta, stack: true } },
    layer: [
      { mark },
      {
        mark: { type: "text", radius: { expr: radius }, fill: "#ffffff", fontWeight: "bold", fontSize: 12 },
        encoding: { text: { field: "__share", type: "nominal" } },
      },
    ],
  };
}

function isVegaSpec(spec: JsonRecord): boolean {
  return typeof spec.$schema === "string" && spec.$schema.includes("/schema/vega/");
}

/** The spec as a card `width` px wide draws it: a laid-out copy, the given spec untouched. */
export function presentChartSpec(spec: JsonRecord, width = 320): JsonRecord {
  const parsed = JSON.parse(JSON.stringify(spec)) as JsonRecord;
  if (isVegaSpec(parsed)) return parsed;
  repairTransforms(parsed, null, null);
  const out = JSON.parse(JSON.stringify(labelSlices(parsed))) as JsonRecord;
  eachView(out, (view, inLayer, fillsCard) => {
    normalizeUnit(view, fillsCard ? width : null);
    keepColorOrder(view);
    unpinLines(view, inLayer);
  });
  compactAxisLabels(out);
  wrapTitle(out, width);
  return out;
}
