/**
 * The chart card's page, drawn for real: a body goes through the card's reading and
 * layout and the page's own script, and the vendored Vega and Vega-Lite draw it in a
 * vm sandbox. Vega-Embed is stood in for by a few lines that do what it does with the
 * page's options (compile, set the view's width, run).
 */
import { buildVegaPageHtml, chartPreviewConfig } from "@/lib/chartPreviewHtml";

import { previewPageSandbox, settle } from "./previewPageSandbox";

// The lib test project has Jest types but no Node type package.
declare const __dirname: string;
const { readFileSync } = jest.requireActual<{
  readFileSync(path: string, encoding: "utf8"): string;
}>("node:fs");
const { join } = jest.requireActual<{ join(...parts: string[]): string }>("node:path");
const vm = jest.requireActual<{
  createContext(scope: Record<string, unknown>): Record<string, unknown>;
  runInContext(source: string, context: Record<string, unknown>): unknown;
}>("node:vm");

export type VegaView = {
  runAsync(): Promise<unknown>;
  scenegraph(): unknown;
  width(): number;
  width(value: number): VegaView;
  scale(name: string): { domain(): unknown[] } | undefined;
  toSVG(): Promise<string>;
};
type Vega = {
  View: new (runtime: unknown, options: Record<string, unknown>) => VegaView;
  parse(spec: unknown): unknown;
  loader(): unknown;
};
type VegaLite = { compile(spec: unknown): { spec: unknown } };

const VENDOR = join(__dirname, "../../vendor");
const theme = { bg: "#fff", text: "#111", textSecondary: "#666", border: "#ddd", danger: "#c00", isDark: false };

/** The card width the page is handed. */
export const CARD_WIDTH = 320;

// Vega-Lite clones specs with structuredClone, which the test realm may not have; specs are JSON.
const clone = (value: unknown): unknown => JSON.parse(JSON.stringify(value));
let libraries: { vega: Vega; vegaLite: VegaLite } | null = null;

function loadVega(): { vega: Vega; vegaLite: VegaLite } {
  if (libraries) return libraries;
  const scope: Record<string, unknown> = {
    console,
    setTimeout,
    clearTimeout,
    URL,
    TextEncoder,
    TextDecoder,
    structuredClone: clone,
  };
  scope.window = scope;
  scope.self = scope;
  const context = vm.createContext(scope);
  for (const file of ["vega.min.js.txt", "vega-lite.min.js.txt"]) {
    vm.runInContext(readFileSync(join(VENDOR, file), "utf8"), context);
  }
  libraries = { vega: context.vega as Vega, vegaLite: context.vegaLite as VegaLite };
  return libraries;
}

export type Drawn = {
  /** What the page posted: `[{kind: "chart-size", height}]` once it drew. */
  posted: unknown[];
  /** The view Vega drew, or null when the page never embedded one. */
  view: VegaView | null;
};

/** What the chart page posts once it has drawn `body`, and the view it drew. */
export async function drawChart(body: string, width = CARD_WIDTH): Promise<Drawn> {
  const { vega, vegaLite } = loadVega();
  let drawn: VegaView | null = null;
  // Vega-Embed as the page calls it: Vega-Lite compiled, the page's width set on the view.
  async function vegaEmbed(
    _target: string,
    spec: Record<string, unknown>,
    options: { loader: unknown; width?: number },
  ) {
    const schema = typeof spec.$schema === "string" ? spec.$schema : "";
    const runtime = schema.includes("/vega/") ? spec : vegaLite.compile(spec).spec;
    const view = new vega.View(vega.parse(runtime), { renderer: "none", loader: options.loader });
    if (options.width != null) view.width(options.width);
    await view.runAsync();
    drawn = view;
    return { view };
  }
  const page = previewPageSandbox({ vega, vegaEmbed });
  page.loadPage(buildVegaPageHtml({ vega: "", vegaLite: "", vegaEmbed: "" }));
  page.hand(chartPreviewConfig(body, theme, width));
  for (let tick = 0; tick < 50 && page.posted.length === 0; tick += 1) {
    await settle();
    page.runFrames();
  }
  return { posted: page.posted, view: drawn };
}

/** The text Vega wrote into the drawn chart (axis labels, legend, titles), in order. */
export async function drawnLabels(view: VegaView): Promise<string[]> {
  const svg = await view.toSVG();
  return [...svg.matchAll(/<text[^>]*>([^<]*)<\/text>/g)].map((match) => match[1]);
}
