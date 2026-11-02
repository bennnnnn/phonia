import { compactLabelExpr, presentChartSpec, withoutTemplateLiterals } from "@/lib/chartPresentation";

type Spec = Record<string, unknown>;
const enc = (spec: Spec): Record<string, Record<string, unknown>> =>
  spec.encoding as Record<string, Record<string, unknown>>;

const line = (y: Record<string, unknown> = {}): Spec => ({
  mark: "line",
  encoding: {
    x: { field: "week", type: "quantitative" },
    y: { field: "kg", type: "quantitative", ...y },
  },
});

describe("presentChartSpec", () => {
  it("lays out a copy and leaves the spec it was given alone", () => {
    const spec = line();
    const before = JSON.stringify(spec);
    expect(presentChartSpec(spec)).not.toBe(spec);
    expect(JSON.stringify(spec)).toBe(before);
  });

  it("leaves a Vega spec as written", () => {
    const vega = { $schema: "https://vega.github.io/schema/vega/v5.json", title: "x".repeat(80), marks: [] };
    expect(presentChartSpec(vega)).toEqual(vega);
  });

  describe("colour order", () => {
    it("keeps the data's order for a nominal colour, fill or stroke", () => {
      const spec = presentChartSpec({
        mark: "arc",
        encoding: {
          theta: { field: "amount", type: "quantitative" },
          color: { field: "item", type: "nominal" },
          stroke: { field: "item" },
        },
      });
      expect(enc(spec).color.sort).toBeNull();
      expect(enc(spec).stroke.sort).toBeNull();
    });

    it("keeps an explicit sort, and leaves a quantitative colour alone", () => {
      const spec = presentChartSpec({
        mark: "point",
        encoding: {
          color: { field: "item", type: "nominal", sort: "descending" },
          fill: { field: "n", type: "quantitative" },
        },
      });
      expect(enc(spec).color.sort).toBe("descending");
      expect(enc(spec).fill).not.toHaveProperty("sort");
    });
  });

  describe("zero on a line's axes", () => {
    it.each([
      ["a line", "line"],
      ["a scatter", "point"],
      ["a line with points", { type: "line", point: true }],
    ])("does not pin %s to zero", (_name, mark) => {
      const spec = presentChartSpec({ ...line(), mark });
      expect(enc(spec).y.scale).toEqual({ zero: false });
      expect(enc(spec).x.scale).toEqual({ zero: false });
    });

    it.each([
      ["bars", "bar"],
      ["an area", "area"],
    ])("keeps %s on zero", (_name, mark) => {
      const spec = presentChartSpec({ ...line(), mark });
      expect(enc(spec).y).not.toHaveProperty("scale");
    });

    it.each([
      ["zero", { scale: { zero: true } }],
      ["domain", { scale: { domain: [0, 100] } }],
      ["lower bound", { scale: { domainMin: 0 } }],
    ])("keeps the %s a line's scale sets", (_name, y) => {
      const spec = presentChartSpec(line(y));
      expect(enc(spec).y.scale).toEqual(y.scale);
    });

    it("unpins a scatter with a best-fit line, but not a line over bars", () => {
      const scatter = presentChartSpec({
        encoding: { x: { field: "x", type: "quantitative" }, y: { field: "y", type: "quantitative" } },
        layer: [{ mark: "point" }, { mark: "line", transform: [{ regression: "y", on: "x" }] }],
      });
      expect(enc(scatter).y.scale).toEqual({ zero: false });
      const mixed = presentChartSpec({
        layer: [
          { mark: "bar", encoding: { y: { field: "n", type: "quantitative" } } },
          { mark: "line", encoding: { y: { field: "n", type: "quantitative" } } },
        ],
      });
      const layers = mixed.layer as Spec[];
      expect(enc(layers[1]).y).not.toHaveProperty("scale");
    });
  });

  describe("large numbers on an axis", () => {
    it("writes a value axis's labels short, sized by its own scale", () => {
      const spec = presentChartSpec(line());
      expect(enc(spec).y.axis).toEqual({ labelExpr: compactLabelExpr("y") });
      expect(compactLabelExpr("y")).toContain("domain('y')");
    });

    it("sizes each label alone where a scale's name is not the channel's", () => {
      const spec = presentChartSpec({ hconcat: [line(), line()] });
      const [first] = spec.hconcat as Spec[];
      expect(enc(first).y.axis).toEqual({ labelExpr: compactLabelExpr(null) });
      expect(compactLabelExpr(null)).not.toContain("domain(");
    });

    it("sizes each label alone on a log scale, whose ticks span powers of ten", () => {
      // One unit for the whole axis drew "0.001k, 0.01k … 100k" for 1, 10 … 100000.
      for (const type of ["log", "symlog"]) {
        const spec = presentChartSpec(line({ scale: { type } }));
        expect(enc(spec).y.axis).toEqual({ labelExpr: compactLabelExpr(null) });
      }
    });

    it("covers a count and a bin Vega-Lite reads as numbers", () => {
      const spec = presentChartSpec({
        mark: "bar",
        encoding: { x: { field: "score", bin: { maxbins: 10 } }, y: { aggregate: "count" } },
      });
      expect(enc(spec).x.axis).toEqual({ labelExpr: compactLabelExpr("x") });
      expect(enc(spec).y.axis).toEqual({ labelExpr: compactLabelExpr("y") });
    });

    it.each([
      ["an axis format", line({ axis: { format: "$,.0f" } }), { format: "$,.0f" }],
      ["a label expression", line({ axis: { labelExpr: "datum.label + ' kg'" } }), { labelExpr: "datum.label + ' kg'" }],
      ["a hidden axis", line({ axis: null }), null],
    ])("keeps %s the spec set", (_name, spec, axis) => {
      expect(enc(presentChartSpec(spec)).y.axis).toEqual(axis);
    });

    it.each([
      ["a number format", { numberFormat: ".2f" }],
      ["an axis format", { axisY: { format: "%" } }],
    ])("leaves every axis alone when the config sets %s", (_name, config) => {
      expect(enc(presentChartSpec({ ...line(), config })).y).not.toHaveProperty("axis");
    });

    it("leaves category and time axes alone", () => {
      const spec = presentChartSpec({
        mark: "line",
        encoding: { x: { field: "day", type: "temporal" }, y: { field: "name", type: "ordinal" } },
      });
      expect(enc(spec).x).not.toHaveProperty("axis");
      expect(enc(spec).y).not.toHaveProperty("axis");
    });
  });

  describe("titles", () => {
    it("wraps a title wider than the card", () => {
      const title = "Average Monthly Temperature in Addis Ababa (°C)";
      expect(presentChartSpec({ mark: "bar", title }, 320).title).toEqual([
        "Average Monthly Temperature in Addis",
        "Ababa (°C)",
      ]);
      expect(presentChartSpec({ mark: "bar", title: { text: title, anchor: "start" } }, 320).title).toEqual({
        text: ["Average Monthly Temperature in Addis", "Ababa (°C)"],
        anchor: "start",
      });
    });

    it("keeps a title that fits", () => {
      expect(presentChartSpec({ mark: "bar", title: "Rainfall" }).title).toBe("Rainfall");
    });
  });

  describe("pie slices", () => {
    const pie = (mark: unknown = "arc", theta: Record<string, unknown> = {}): Spec => ({
      data: { values: [{ item: "Rent", amount: 1200 }, { item: "Food", amount: 400 }] },
      mark,
      encoding: {
        theta: { field: "amount", type: "quantitative", ...theta },
        color: { field: "item", type: "nominal" },
      },
    });

    it("writes each slice's share on it, mid-slice", () => {
      const spec = presentChartSpec(pie());
      expect(spec).not.toHaveProperty("mark");
      expect(enc(spec).theta).toMatchObject({ field: "amount", stack: true });
      const [arc, label] = spec.layer as Spec[];
      expect(arc.mark).toBe("arc");
      expect(label).toMatchObject({
        mark: { type: "text", radius: { expr: "min(width, height) / 2 * 0.62" } },
        encoding: { text: { field: "__share" } },
      });
      expect(spec.transform).toEqual([
        { joinaggregate: [{ op: "sum", field: "amount", as: "__total" }] },
        {
          calculate:
            "datum[\"amount\"] / datum.__total >= 0.05 ? format(datum[\"amount\"] / datum.__total, '.0%') : ''",
          as: "__share",
        },
      ]);
    });

    it("puts a donut's labels in its ring", () => {
      const [, label] = presentChartSpec(pie({ type: "arc", innerRadius: 50 })).layer as Spec[];
      expect(label.mark).toMatchObject({ radius: { expr: "(min(width, height) / 2 + 50) / 2" } });
    });

    it.each([
      ["a share it adds up itself", pie("arc", { aggregate: "sum" })],
      ["a nested field", pie("arc", { field: "cost.amount" })],
      ["labels of its own", { ...pie(), encoding: { ...(pie().encoding as Spec), text: { field: "item" } } }],
    ])("leaves %s as written", (_name, spec) => {
      expect(presentChartSpec(spec)).not.toHaveProperty("layer");
    });
  });

  describe("transforms a model wrote that cannot run", () => {
    it.each([
      ["`Grade ${datum.grade} - ${datum.gender}`", "('Grade ' + (datum.grade) + ' - ' + (datum.gender))"],
      // Text first: "${a}${b}" joins, and a lone "${n}" stays text.
      ["`${datum.a}${datum.b}`", "('' + (datum.a) + (datum.b))"],
      ["`${datum.n}` != ''", "('' + (datum.n)) != ''"],
      ["datum.m - `x${datum.y}`", "datum.m - ('x' + (datum.y))"],
      ["`it's ${datum.a}`", "('it\\'s ' + (datum.a))"],
      ["``", "('')"],
      // A backtick inside a quoted string is that string's text.
      ["datum.s == '`' || datum.t == \"`\"", "datum.s == '`' || datum.t == \"`\""],
      ["replace(datum.s, '`', '')", "replace(datum.s, '`', '')"],
      ["datum.a > 3", "datum.a > 3"],
    ])("writes %s as a Vega expression", (expr, written) => {
      expect(withoutTemplateLiterals(expr)).toBe(written);
    });

    it("rewrites a calculation and a filter, and leaves the rest", () => {
      const spec = presentChartSpec({
        data: { values: [{ grade: 1, n: 2 }] },
        transform: [{ calculate: "`G${datum.grade}`", as: "label" }, { filter: "`${datum.n}` != ''" }, { fold: ["n"] }],
        mark: "bar",
        encoding: { x: { field: "label", type: "nominal" }, y: { field: "n", type: "quantitative" } },
      });
      expect(spec.transform).toEqual([
        { calculate: "('G' + (datum.grade))", as: "label" },
        { filter: "('' + (datum.n)) != ''" },
        { fold: ["n"] },
      ]);
    });

    it("reaches a faceted chart's inner spec", () => {
      const spec = presentChartSpec({
        data: { values: [{ g: "a", n: 1 }] },
        facet: { field: "g", type: "nominal" },
        spec: { transform: [{ calculate: "`n${datum.n}`", as: "l" }], mark: "bar" },
      });
      expect((spec.spec as Spec).transform).toEqual([{ calculate: "('n' + (datum.n))", as: "l" }]);
    });

    const fit = (step: Spec, layer: Spec = {}): Spec => ({
      data: { values: [{ hours: 1, score: 50, day: "2026-10-01" }, { hours: 2, score: 55, day: "2026-10-02" }] },
      encoding: { x: { field: "hours", type: "quantitative" }, y: { field: "score", type: "quantitative" } },
      layer: [{ mark: "point" }, { mark: "line", ...layer, transform: [...((layer.transform as Spec[]) ?? []), step] }],
    });
    const fitted = (spec: Spec): Spec[] => ((spec.layer as Spec[])[1].transform as Spec[]);

    it.each(["regression", "loess"])("fits a %s on the plot's own fields when it named others", (key) => {
      expect(fitted(presentChartSpec(fit({ [key]: "y", on: "x" }))).at(-1)).toEqual({ [key]: "score", on: "hours" });
    });

    it("leaves a fit on fields the rows have", () => {
      const step = { regression: "score", on: "hours", method: "poly" };
      expect(fitted(presentChartSpec(fit(step))).at(-1)).toEqual(step);
    });

    it("fixes only the field the rows lack", () => {
      expect(fitted(presentChartSpec(fit({ regression: "zz", on: "day" }))).at(-1)).toEqual({ regression: "score", on: "day" });
    });

    it("counts a field an earlier step makes as known", () => {
      const made = { timeUnit: "year", field: "day", as: "yr" };
      const step = { regression: "score", on: "yr" };
      expect(fitted(presentChartSpec(fit(step, { transform: [made] }))).at(-1)).toEqual(step);
    });

    it("leaves a view with data of its own kind as written", () => {
      const step = { regression: "b", on: "a" };
      expect(fitted(presentChartSpec(fit(step, { data: { name: "other" } }))).at(-1)).toEqual(step);
    });
  });
});
