import { chartJsToVegaLite } from "@/lib/chartJsSpec";
import { chartTable, readChart } from "@/lib/chartSpec";

// What a reply to "Graph y = sin(x) and y = cos(x) from 0 to 2π" held: a Chart.js config.
const CHART_JS_BODY = JSON.stringify({
  type: "line",
  data: {
    labels: [0, "π/2", "π", "3π/2", "2π"],
    datasets: [
      { label: "y = sin(x)", data: [0, 1, 0, -1, 0], borderColor: "#36a2eb", tension: 0.4 },
      { label: "y = cos(x)", data: [1, 0, -1, 0, 1], borderColor: "#ff6384" },
    ],
  },
  options: { scales: { x: { title: { display: true, text: "x (radians)" } }, y: { min: -1.2 } } },
});

describe("readChart", () => {
  it("draws a Vega-Lite spec with inline data as written", () => {
    const spec = { mark: "bar", data: { values: [{ day: "Mon", n: 12 }] } };
    expect(readChart(JSON.stringify(spec))).toEqual({
      spec,
      table: { columns: ["day", "n"], rows: [["Mon", "12"]] },
    });
  });

  it("draws a Chart.js config as a Vega-Lite line, labels kept in order", () => {
    const { spec } = readChart(CHART_JS_BODY);
    expect(spec).toMatchObject({
      mark: "line",
      encoding: {
        x: { field: "x", type: "ordinal", sort: null, title: "x (radians)" },
        color: { field: "series" },
      },
    });
    expect((spec?.data as { values: unknown[] }).values).toHaveLength(10);
    expect((spec?.data as { values: unknown[] }).values[1]).toEqual({
      x: "π/2",
      y: 1,
      series: "y = sin(x)",
    });
  });

  it("finds the data inside layers and in a Vega spec's data list", () => {
    const layered = { layer: [{ mark: "point", data: { values: [{ x: 1, y: 2 }] } }] };
    const vega = { $schema: "https://vega.github.io/schema/vega/v5.json", data: [{ name: "t", values: [{ a: 1 }] }] };
    expect(readChart(JSON.stringify(layered)).spec).toEqual(layered);
    expect(readChart(JSON.stringify(vega)).spec).toEqual(vega);
  });

  it.each([
    ["no JSON at all", "Rainfall by month"],
    ["no data", '{"mark":"bar","encoding":{"x":{"field":"a"}}}'],
    ["empty data", '{"mark":"bar","data":{"values":[]}}'],
    ["data fetched from a URL", '{"mark":"bar","data":{"url":"https://example.com/d.csv"}}'],
    [
      "a curve the phone would have to compute",
      '{"data":{"sequence":{"start":0,"stop":6.3,"step":0.1,"as":"x"}},' +
        '"transform":[{"calculate":"sin(datum.x)","as":"y"}],"mark":"line"}',
    ],
    ["a series written as a formula", '{"type":"line","series":[{"name":"f","fn":"x^2"}]}'],
  ])("does not draw %s, and has no table for it", (_name, body) => {
    expect(readChart(body)).toEqual({ spec: null, table: null });
  });
});

describe("chartTable", () => {
  it("shows plain values in one column and keeps at most 30 rows and 5 columns", () => {
    expect(chartTable({ data: { values: [55, 62] } })).toEqual({
      columns: ["value"],
      rows: [["55"], ["62"]],
    });
    const wide = Object.fromEntries("abcdefg".split("").map((k, i) => [k, i]));
    const table = chartTable({ data: { values: Array.from({ length: 40 }, () => wide) } });
    expect(table?.columns).toEqual(["a", "b", "c", "d", "e"]);
    expect(table?.rows).toHaveLength(30);
  });

  it("leaves out nested objects and fills a missing cell with nothing", () => {
    expect(chartTable({ data: { values: [{ a: 1, meta: { b: 2 } }, { c: "x" }] } })).toEqual({
      columns: ["a", "c"],
      rows: [["1", ""], ["", "x"]],
    });
  });
});

describe("chartJsToVegaLite", () => {
  it("draws a pie from the first dataset's slices", () => {
    expect(
      chartJsToVegaLite({
        type: "pie",
        data: { labels: ["Rent", "Food"], datasets: [{ data: [1200, 400] }] },
        options: { plugins: { title: { text: "Budget" } } },
      }),
    ).toMatchObject({
      title: "Budget",
      mark: { type: "arc" },
      data: { values: [{ x: "Rent", y: 1200 }, { x: "Food", y: 400 }] },
      encoding: { theta: { field: "y" }, color: { field: "x" } },
    });
  });

  it("puts two bar datasets side by side and reads scatter points", () => {
    expect(
      chartJsToVegaLite({
        type: "bar",
        data: { labels: ["Q1", "Q2"], datasets: [{ label: "2024", data: [1, 2] }, { label: "2025", data: [3, 4] }] },
      }),
    ).toMatchObject({ mark: "bar", encoding: { xOffset: { field: "series" } } });
    expect(
      chartJsToVegaLite({ type: "scatter", data: { datasets: [{ data: [{ x: 1, y: 2 }] }] } }),
    ).toMatchObject({ mark: "point", encoding: { x: { type: "quantitative" } } });
  });

  it.each([
    ["a Vega-Lite spec", { mark: "bar", data: { values: [{ a: 1 }] } }],
    ["a dataset that is not numbers", { data: { datasets: [{ data: ["high"] }] } }],
  ])("is null for %s", (_name, spec) => {
    expect(chartJsToVegaLite(spec)).toBeNull();
  });
});
