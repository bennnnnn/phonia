/**
 * The chart contract, drawn: every shape the server's chart hint shows the model
 * (apps/api/app/modules/chat/prompt_constants/chart_shapes.json) goes through the
 * card's reading, the page's layout and the page's own script, with the vendored
 * Vega and Vega-Lite doing the drawing, and puts data marks on the plot. Bodies models
 * wrote that once drew a blank card are in docs/fixtures/chart_bodies.json
 * (chartBodies.test.ts). A spec that draws nothing makes the page report an error, so
 * the card shows its data instead.
 */
import { readChart } from "@/lib/chartSpec";

import { CARD_WIDTH, drawChart } from "./fixtures/chartPage";

// The lib test project has Jest types but no Node type package.
declare const __dirname: string;
const { readFileSync } = jest.requireActual<{
  readFileSync(path: string, encoding: "utf8"): string;
}>("node:fs");
const { join } = jest.requireActual<{ join(...parts: string[]): string }>("node:path");

const SHAPES: Record<string, Record<string, unknown>> = JSON.parse(
  readFileSync(
    join(__dirname, "../../../api/app/modules/chat/prompt_constants/chart_shapes.json"),
    "utf8",
  ),
);

/** What the chart page posts once it has drawn `body`. */
async function draw(body: string): Promise<unknown[]> {
  return (await drawChart(body)).posted;
}

const DRAWN = [{ kind: "chart-size", height: expect.any(Number) }];

describe("the chart contract", () => {
  it("shows the model six shapes", () => {
    expect(Object.keys(SHAPES)).toEqual([
      "bar",
      "line",
      "scatter with best-fit line",
      "histogram",
      "pie",
      "box plot",
    ]);
  });

  it.each(Object.entries(SHAPES))("draws the %s shape with data marks, across the card", async (_name, spec) => {
    const body = JSON.stringify(spec);
    expect(readChart(body).spec).not.toBeNull();
    const { posted, view } = await drawChart(body);
    expect(posted).toEqual(DRAWN);
    expect(view?.width()).toBeGreaterThanOrEqual(CARD_WIDTH / 2);
  });

  it("reports a spec that draws no data marks, so the card shows its data instead", async () => {
    const body = JSON.stringify({
      data: { values: [{ a: 1 }, { a: 2 }] },
      transform: [{ filter: { field: "a", gt: 5 } }],
      mark: "bar",
      encoding: { x: { field: "a", type: "quantitative" }, y: { aggregate: "count" } },
    });
    expect(await draw(body)).toEqual([{ kind: "chart-error", message: "No data marks were drawn." }]);
  });
});
