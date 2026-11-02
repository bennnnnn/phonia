import { buildVegaPageHtml, CHART_PAGE, chartPreviewConfig } from "@/lib/chartPreviewHtml";
import { normalizeChartSpec } from "@/lib/chartPresentation";
import { PREVIEW_PAGE_LINK_KIND } from "@/lib/preview/previewPage";
import { CHART_PREVIEW_CSP, PREVIEW_CSP } from "@/lib/preview/previewSandbox";

import { previewPageSandbox, settle } from "./fixtures/previewPageSandbox";

const SOURCES = { vega: "/*vega*/", vegaLite: "/*vega-lite*/", vegaEmbed: "/*vega-embed*/" };

const theme = {
  bg: "#fff",
  text: "#111",
  textSecondary: "#666",
  border: "#ddd",
  danger: "#c00",
  isDark: false,
};

describe("normalizeChartSpec", () => {
  it("sets sort null on nominal x so months keep data.values order", () => {
    const spec = {
      encoding: { x: { field: "month", type: "nominal" }, y: { field: "inches", type: "quantitative" } },
    };
    normalizeChartSpec(spec);
    expect((spec.encoding.x as { sort?: unknown }).sort).toBeNull();
  });

  it("does not override an explicit sort", () => {
    const spec = {
      encoding: { x: { field: "month", type: "nominal", sort: "ascending" } },
    };
    normalizeChartSpec(spec);
    expect(spec.encoding.x.sort).toBe("ascending");
  });

  it("leaves quantitative and temporal x alone", () => {
    const quant = { encoding: { x: { field: "n", type: "quantitative" } } };
    const time = { encoding: { x: { field: "t", type: "temporal" } } };
    normalizeChartSpec(quant);
    normalizeChartSpec(time);
    expect("sort" in quant.encoding.x).toBe(false);
    expect("sort" in time.encoding.x).toBe(false);
  });

  it("walks layer children", () => {
    const spec = {
      layer: [{ encoding: { x: { field: "month", type: "nominal" } } }],
    };
    normalizeChartSpec(spec);
    expect((spec.layer[0].encoding.x as { sort?: unknown }).sort).toBeNull();
  });

  const LONG_NAMES = ["United States", "United Kingdom", "Germany", "Japan", "Brazil", "India", "Kenya"];
  const bars = (
    labels: string[],
    x: string,
    y: string,
    extra: Record<string, unknown> = {},
  ): { mark: string; data: unknown; encoding: Record<string, unknown> } => ({
    mark: "bar",
    data: { values: labels.map((name, i) => ({ name, n: i + 1, series: i % 2 ? "a" : "b" })) },
    encoding: {
      x: { field: x, type: x === "n" ? "quantitative" : "nominal" },
      y: { field: y, type: y === "n" ? "quantitative" : "nominal" },
      ...extra,
    },
  });
  const axisFields = (spec: { encoding: Record<string, unknown> }) =>
    ["x", "y"].map((key) => (spec.encoding[key] as { field?: string }).field);

  it.each([
    ["months", ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]],
    ["weekdays", ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]],
    ["quarters", ["Q1", "Q2", "Q3", "Q4"]],
    ["years", ["2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026"]],
    ["a few short names", ["Rent", "Food", "Travel", "Fun"]],
  ])("stands %s as columns, whichever way the model wrote them", (_name, labels) => {
    const standing = bars(labels, "name", "n");
    const across = bars(labels, "n", "name");
    normalizeChartSpec(standing);
    normalizeChartSpec(across);
    expect(axisFields(standing)).toEqual(["name", "n"]);
    expect(axisFields(across)).toEqual(["name", "n"]);
    expect((across.encoding.x as { sort?: unknown }).sort).toBeNull();
  });

  it.each([
    ["many names", LONG_NAMES],
    ["long names", ["Ethiopian Airlines", "Kenya Airways", "EgyptAir"]],
    ["more months than fit", Array.from({ length: 24 }, (_, i) => `${2024 + Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, "0")}`)],
  ])("lays %s across the card, whichever way the model wrote them", (_name, labels) => {
    const standing = bars(labels, "name", "n");
    const across = bars(labels, "n", "name");
    normalizeChartSpec(standing);
    normalizeChartSpec(across);
    expect(axisFields(standing)).toEqual(["n", "name"]);
    expect(axisFields(across)).toEqual(["n", "name"]);
    expect((standing.encoding.y as { sort?: unknown }).sort).toBeNull();
  });

  it("stands names as columns only when they fit upright on the card", () => {
    const languages = ["Python", "JavaScript", "TypeScript", "Java", "C#"];
    const narrow = bars(languages, "name", "n");
    const wide = bars(languages, "name", "n");
    normalizeChartSpec(narrow, 320);
    normalizeChartSpec(wide, 640);
    expect(axisFields(narrow)).toEqual(["n", "name"]);
    expect(axisFields(wide)).toEqual(["name", "n"]);
  });

  it("writes column labels upright, and thins crowded time labels instead of overlapping them", () => {
    const names = bars(["Rent", "Food", "Travel", "Fun"], "n", "name");
    const years = bars(Array.from({ length: 12 }, (_, i) => String(2015 + i)), "name", "n");
    const tilted = bars(["Rent", "Food"], "name", "n");
    (tilted.encoding.x as Record<string, unknown>).axis = { labelAngle: -45 };
    for (const spec of [names, years, tilted]) normalizeChartSpec(spec);
    expect((names.encoding.x as { axis?: unknown }).axis).toEqual({ labelAngle: 0 });
    expect((years.encoding.x as { axis?: unknown }).axis).toEqual({ labelAngle: 0, labelOverlap: "parity" });
    // An angle the model chose for its columns stays.
    expect((tilted.encoding.x as { axis?: unknown }).axis).toEqual({ labelAngle: -45 });
  });

  it("drops a column label angle when the bars lie down", () => {
    const spec = bars(LONG_NAMES, "name", "n");
    (spec.encoding.x as Record<string, unknown>).axis = { labelAngle: -45, title: "Country" };
    normalizeChartSpec(spec);
    expect((spec.encoding.y as { axis?: unknown }).axis).toEqual({ title: "Country" });
  });

  it("turns a channel-named sort and a range's second end with the bars", () => {
    const spec = bars(["Jan", "Feb", "Mar"], "n", "name", { x2: { field: "top" } });
    (spec.encoding.y as Record<string, unknown>).sort = "-x";
    const named = bars(["Jan", "Feb", "Mar"], "n", "name");
    (named.encoding.y as Record<string, unknown>).sort = { encoding: "x", order: "descending" };
    normalizeChartSpec(spec);
    normalizeChartSpec(named);
    expect(spec.encoding.x).toMatchObject({ field: "name", sort: "-y" });
    expect(spec.encoding.y2).toEqual({ field: "top" });
    expect(spec.encoding).not.toHaveProperty("x2");
    expect((named.encoding.x as { sort?: unknown }).sort).toEqual({ encoding: "y", order: "descending" });
  });

  it("leaves bars in a facet's or a concat's panels as written: they do not span the card", () => {
    const faceted = bars(["Male", "Female"], "name", "n", { column: { field: "series" } });
    const panel = bars(LONG_NAMES, "name", "n");
    const concat = { hconcat: [panel] };
    normalizeChartSpec(faceted);
    normalizeChartSpec(concat);
    expect(axisFields(faceted)).toEqual(["name", "n"]);
    expect((faceted.encoding.x as { axis?: unknown }).axis).toBeUndefined();
    expect(axisFields(panel)).toEqual(["name", "n"]);
  });

  it("keeps the direction written when the rows do not say what the labels are", () => {
    const spec = {
      mark: "bar",
      data: { url: "data.json" },
      encoding: { x: { field: "n", type: "quantitative" }, y: { field: "name", type: "nominal" } },
    };
    normalizeChartSpec(spec);
    expect(axisFields(spec)).toEqual(["n", "name"]);
  });

  it("does not swap line charts", () => {
    const spec = {
      mark: "line",
      encoding: {
        x: { field: "month", type: "nominal" },
        y: { field: "inches", type: "quantitative" },
      },
    };
    normalizeChartSpec(spec);
    expect((spec.encoding.x as { field?: string }).field).toBe("month");
  });

  it("moves the group offset with the bars when it turns them", () => {
    const across = bars(LONG_NAMES, "name", "n", { xOffset: { field: "series", type: "nominal" } });
    normalizeChartSpec(across);
    expect(axisFields(across)).toEqual(["n", "name"]);
    expect((across.encoding.yOffset as { field?: string }).field).toBe("series");
    expect(across.encoding).not.toHaveProperty("xOffset");

    const standing = bars(["Q1", "Q2", "Q3", "Q4"], "n", "name", { yOffset: { field: "series", type: "nominal" } });
    normalizeChartSpec(standing);
    expect(axisFields(standing)).toEqual(["name", "n"]);
    expect((standing.encoding.xOffset as { field?: string }).field).toBe("series");
    expect(standing.encoding).not.toHaveProperty("yOffset");
  });

  it("drops tooltips: the card shows none, and a bad format blanked the chart", () => {
    const spec = {
      mark: "bar",
      encoding: { x: { field: "a" }, tooltip: [{ field: "a", format: "[datum.a)" }] },
      layer: [{ mark: "line", encoding: { tooltip: { field: "b" } } }],
    };
    normalizeChartSpec(spec);
    expect(spec.encoding).not.toHaveProperty("tooltip");
    expect(spec.layer[0].encoding).not.toHaveProperty("tooltip");
  });

  it.each([
    ["an [start, end] pair", ["lo", "hi"], "hi"],
    ["one name, whose end Vega-Lite calls <name>_end", "lo", "lo_end"],
  ])("gives pre-binned bars their bin end from the transform's %s", (_name, as, end) => {
    const spec: Record<string, unknown> = {
      transform: [{ bin: true, field: "score", as }],
      mark: "bar",
      encoding: { x: { field: "lo", type: "quantitative", bin: "binned" }, y: { aggregate: "count" } },
    };
    normalizeChartSpec(spec);
    expect(spec.encoding).toMatchObject({ x: { bin: "binned" }, x2: { field: end } });
  });

  it("draws pre-binned bars with no bin end at their starts instead of not at all", () => {
    const spec = {
      mark: "bar",
      encoding: { x: { field: "lo", type: "quantitative", bin: "binned" } as Record<string, unknown> },
    };
    normalizeChartSpec(spec);
    expect(spec.encoding.x).toEqual({ field: "lo", type: "quantitative" });
    expect(spec.encoding).not.toHaveProperty("x2");
  });

  it("leaves already-horizontal grouped bars on yOffset", () => {
    const spec: Record<string, unknown> = {
      mark: "bar",
      encoding: {
        x: { field: "inches", type: "quantitative" },
        y: { field: "month", type: "nominal" },
        yOffset: { field: "series", type: "nominal" },
      },
    };
    normalizeChartSpec(spec);
    const enc = spec.encoding as Record<string, { field?: string } | undefined>;
    expect(enc.yOffset?.field).toBe("series");
    expect(enc.xOffset).toBeUndefined();
  });
});

describe("buildVegaPageHtml", () => {
  it("injects the chart CSP so Vega Function() compile is allowed", () => {
    const html = buildVegaPageHtml(SOURCES);
    expect(html).toContain(`content="${CHART_PREVIEW_CSP}"`);
    expect(html).toContain("unsafe-eval");
    expect(html).not.toContain(`content="${PREVIEW_CSP}"`);
    expect(html).toContain("JSON.parse");
    expect(html).toContain("connect-src 'none'");
  });

  it("inlines Vega, Vega-Lite and Vega-Embed once each, in load order", () => {
    const html = buildVegaPageHtml(SOURCES);
    const at = Object.values(SOURCES).map((source) => html.indexOf(source));
    expect(at.every((index, i) => index > (at[i - 1] ?? 0))).toBe(true);
    for (const source of Object.values(SOURCES)) expect(html.split(source)).toHaveLength(2);
  });

  it("reports SVG size, disables tooltip, and does not use a 100vh body", () => {
    const html = buildVegaPageHtml(SOURCES);
    expect(html).not.toContain("100vh");
    expect(html).toContain("chart-size");
    expect(html).toContain("tooltip: false");
    expect(html).toContain("overflow: hidden");
  });

  it("is one page for every chart: the spec and theme arrive as config", () => {
    expect(CHART_PAGE.libraries).toEqual(["vega", "vegaLite", "vegaEmbed"]);
    const html = CHART_PAGE.build(SOURCES);
    expect(html).toBe(buildVegaPageHtml(SOURCES));
    expect(html).not.toContain(theme.bg);
  });
});

/** Vega's loader as the page gets it from `vega.loader()`, sanitizing as Vega would. */
function fakeVega() {
  const sanitize = jest.fn(async (uri: string) => ({ href: uri }));
  return { vega: { loader: () => ({ sanitize }) }, sanitize };
}

type EmbedOptions = { loader: { sanitize: (uri: string, options: { context: string }) => Promise<unknown> } };

describe("the chart page", () => {
  it("embeds the spec it is handed, themed and fitted to the card", async () => {
    const vegaEmbed = jest.fn((_target: string, _spec: unknown, _options: EmbedOptions) => Promise.resolve());
    const page = previewPageSandbox({ vegaEmbed, ...fakeVega() });
    page.loadPage(buildVegaPageHtml(SOURCES));
    expect(vegaEmbed).not.toHaveBeenCalled();

    page.hand(chartPreviewConfig('{"mark":"bar","config":{"axis":{"grid":false}}}', theme, 296));
    expect(page.css).toEqual({ "--bg": "#fff", "--danger": "#c00" });
    const themed = {
      background: "#fff",
      axis: { domainColor: "#666", labelColor: "#111", titleColor: "#111", tickColor: "#666", gridColor: "#ddd" },
      // Under the plot, in the columns a 296 px card has room for.
      legend: { labelColor: "#111", titleColor: "#111", orient: "bottom", columns: 1, labelLimit: 260 },
      title: { color: "#111", limit: 286 },
      view: { stroke: "#666" },
    };
    expect(vegaEmbed).toHaveBeenCalledWith(
      "#chart",
      {
        mark: "bar",
        // The spec's own config wins over the theme's, key by key inside each block.
        config: { ...themed, axis: { ...themed.axis, grid: false } },
        autosize: { type: "fit-x", contains: "padding" },
        // A plot with no x axis fills the card instead of one 20 px step.
        width: 296,
      },
      {
        actions: false,
        tooltip: false,
        renderer: "svg",
        width: 296,
        theme: "vox",
        config: themed,
        loader: expect.anything(),
      },
    );
    await settle();
    page.runFrames();
    expect(page.posted).toEqual([{ kind: "chart-size", height: 116 }]);
  });

  it("hands a mark's link to the app instead of letting Vega follow it", async () => {
    const vegaEmbed = jest.fn((_target: string, _spec: unknown, _options: EmbedOptions) => Promise.resolve());
    const { vega, sanitize } = fakeVega();
    const page = previewPageSandbox({ vegaEmbed, vega });
    page.loadPage(buildVegaPageHtml(SOURCES));
    page.hand(chartPreviewConfig('{"mark":"bar"}', theme));
    const { loader } = vegaEmbed.mock.calls[0][2];

    await expect(loader.sanitize("https://example.com/?leak=1", { context: "href" })).rejects.toThrow();
    expect(page.posted).toEqual([{ kind: PREVIEW_PAGE_LINK_KIND, url: "https://example.com/?leak=1" }]);
    // Images and data still go through Vega's own checks.
    await expect(loader.sanitize("data:image/png;base64,AA", { context: "image" })).resolves.toEqual({
      href: "data:image/png;base64,AA",
    });
    expect(sanitize).toHaveBeenCalledTimes(1);
  });

  it("ignores a spec's own embed options, which would override the page's", () => {
    const vegaEmbed = jest.fn((_target: string, _spec: unknown, _options: EmbedOptions) => Promise.resolve());
    const page = previewPageSandbox({ vegaEmbed, ...fakeVega() });
    page.loadPage(buildVegaPageHtml(SOURCES));
    const spec = { mark: "bar", usermeta: { embedOptions: { actions: true, editorUrl: "https://evil.test" }, note: "kept" } };
    page.hand(chartPreviewConfig(JSON.stringify(spec), theme));
    expect(vegaEmbed.mock.calls[0][1]).toMatchObject({ usermeta: { note: "kept" } });
    expect(vegaEmbed.mock.calls[0][1]).not.toHaveProperty("usermeta.embedOptions");
  });

  it("reports a spec that is not JSON", () => {
    const page = previewPageSandbox({ vegaEmbed: jest.fn(), ...fakeVega() });
    page.loadPage(buildVegaPageHtml(SOURCES));
    page.hand(chartPreviewConfig("{not json", theme));
    expect(page.posted).toEqual([{ kind: "chart-error", message: expect.stringContaining("JSON") }]);
  });
});

describe("chartPreviewConfig", () => {
  it("lays the spec out for a phone before the page draws it", () => {
    const config = chartPreviewConfig(
      JSON.stringify({
        $schema: "https://vega.github.io/schema/vega-lite/v5.json",
        mark: "bar",
        encoding: { x: { field: "month", type: "nominal" } },
      }),
      theme,
    );
    expect(config.spec).toContain('"sort":null');
  });

  it("carries the theme and the card's width", () => {
    expect(chartPreviewConfig('{"mark":"bar"}', theme, 300.7)).toEqual({
      spec: '{"mark":"bar"}',
      width: 300,
      vegaTheme: "vox",
      colors: { bg: "#fff", text: "#111", axis: "#666", grid: "#ddd", danger: "#c00" },
    });
    expect(chartPreviewConfig('{"mark":"bar"}', { ...theme, isDark: true }).vegaTheme).toBe("dark");
    expect(chartPreviewConfig('{"mark":"bar"}', theme, 40).width).toBe(120);
  });

  it("hands the page a body it cannot read as written, so the page reports the error", () => {
    expect(chartPreviewConfig("{not json", theme).spec).toBe("{not json");
  });
});
