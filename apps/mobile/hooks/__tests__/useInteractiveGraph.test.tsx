import { drawGraphSeries, seedGraphSeries } from "@/hooks/useInteractiveGraph";

describe("seedGraphSeries", () => {
  it("locks every verified seed curve", () => {
    const rows = seedGraphSeries(["x^2", "x^2/3"]);
    expect(rows).toHaveLength(2);
    expect(rows[0].locked).toBe(true);
    expect(rows[0].expr).toBe("y = x^2");
    expect(rows[1].locked).toBe(true);
    expect(rows[1].expr).toBe("y = x^2/3");
  });
});

describe("drawGraphSeries", () => {
  const view = { xMin: -4, xMax: 4, yMin: -4, yMax: 4 };
  // The server's own samples, dense enough to be a curve rather than scatter points.
  const serverSamples = {
    points: Array.from({ length: 48 }, (_, i): [number, number] => [i / 8 - 3, 0]),
  };

  it.each(["sin(x)", "cos(2x)", "sqrt(x)", "log(x)", "abs(x)", "x*e^x", "ceil(x)"])(
    "resamples the graph fence's %s in view",
    (expr) => {
      const [row] = seedGraphSeries([expr], [serverSamples]);
      const drawn = drawGraphSeries(row, "#000", "x", view);
      expect(drawn.invalid).toBe(false);
      expect(drawn.points).not.toBe(serverSamples.points);
      expect(drawn.points.length).toBeGreaterThan(0);
    },
  );

  it("keeps the server's samples for text it cannot read", () => {
    const [row] = seedGraphSeries(["|x|"], [serverSamples]);
    expect(drawGraphSeries(row, "#000", "x", view).points).toBe(serverSamples.points);
  });
});
