import { graphAxisTicks } from "@/lib/math/graphBlock";
import { defaultInteractiveBounds, expandGraphView } from "@/lib/math/graphViewport";
import { panGraphViewW, tickCountW, zoomGraphViewW } from "@/lib/math/graphWorklets";

describe("interactive graph viewport", () => {
  it("starts with unit ticks including −3…3", () => {
    const view = defaultInteractiveBounds(1.75);
    const xTicks = graphAxisTicks(
      view.xMin,
      view.xMax,
      tickCountW(view.xMin, view.xMax),
      true,
    );
    const yTicks = graphAxisTicks(
      view.yMin,
      view.yMax,
      tickCountW(view.yMin, view.yMax),
      true,
    );
    expect(xTicks).toEqual(expect.arrayContaining([-3, -2, -1, 0, 1, 2, 3]));
    expect(yTicks).toEqual(expect.arrayContaining([-3, -2, -1, 0, 1, 2, 3]));
  });

  it("zooms in around the origin so tick spacing shrinks", () => {
    const start = defaultInteractiveBounds(1.75);
    const zoomed = zoomGraphViewW(start, 4, 0, 0);
    expect(zoomed.xMax - zoomed.xMin).toBeCloseTo((start.xMax - start.xMin) / 4);
    const step = (a: number[]) => {
      const diffs = a.slice(1).map((n, i) => n - a[i]);
      return Math.min(...diffs);
    };
    const startTicks = graphAxisTicks(
      start.xMin,
      start.xMax,
      tickCountW(start.xMin, start.xMax),
      true,
    );
    const zoomTicks = graphAxisTicks(
      zoomed.xMin,
      zoomed.xMax,
      tickCountW(zoomed.xMin, zoomed.xMax),
      true,
    );
    expect(step(zoomTicks)).toBeLessThan(step(startTicks));
  });

  it("zooms out so tick spacing grows", () => {
    const start = defaultInteractiveBounds(1.75);
    const zoomed = zoomGraphViewW(start, 0.25, 0, 0);
    expect(zoomed.xMax - zoomed.xMin).toBeCloseTo((start.xMax - start.xMin) * 4);
    const startTicks = graphAxisTicks(
      start.xMin,
      start.xMax,
      tickCountW(start.xMin, start.xMax),
      true,
    );
    const zoomTicks = graphAxisTicks(
      zoomed.xMin,
      zoomed.xMax,
      tickCountW(zoomed.xMin, zoomed.xMax),
      true,
    );
    const step = (a: number[]) => Math.min(...a.slice(1).map((n, i) => n - a[i]));
    expect(step(zoomTicks)).toBeGreaterThan(step(startTicks));
  });

  it("pans so dragging right reveals more negative x", () => {
    const start = defaultInteractiveBounds(1.75);
    const moved = panGraphViewW(start, 100, 0, 360, 220, 28);
    expect(moved.xMin).toBeLessThan(start.xMin);
    expect(moved.xMax - moved.xMin).toBeCloseTo(start.xMax - start.xMin);
  });

  it("pans vertically with the finger without changing either scale", () => {
    const start = defaultInteractiveBounds(1.75);
    const movedDown = panGraphViewW(start, 0, 80, 360, 220, 28);
    const movedUp = panGraphViewW(start, 0, -80, 360, 220, 28);

    expect(movedDown.yMin).toBeGreaterThan(start.yMin);
    expect(movedUp.yMin).toBeLessThan(start.yMin);
    expect(movedDown.xMax - movedDown.xMin).toBeCloseTo(start.xMax - start.xMin);
    expect(movedDown.yMax - movedDown.yMin).toBeCloseTo(start.yMax - start.yMin);
  });

  it("relabels both axes for panned and zoomed windows", () => {
    const initialX = graphAxisTicks(-6, 6, tickCountW(-6, 6), true);
    const pannedX = graphAxisTicks(14, 26, tickCountW(14, 26), true);
    const zoomedY = graphAxisTicks(-60, 60, tickCountW(-60, 60), true);

    expect(initialX).toContain(0);
    expect(pannedX.every((tick) => tick >= 14 && tick <= 26)).toBe(true);
    expect(pannedX).not.toContain(0);
    expect(zoomedY).toEqual(expect.arrayContaining([-60, -30, 0, 30, 60]));
  });

  it("expandGraphView widens around the center", () => {
    const view = { xMin: -2, xMax: 4, yMin: -1, yMax: 5 };
    const wide = expandGraphView(view, 3);
    expect(wide.xMax - wide.xMin).toBeCloseTo(18);
    expect(wide.yMax - wide.yMin).toBeCloseTo(18);
    expect((wide.xMin + wide.xMax) / 2).toBeCloseTo(1);
    expect((wide.yMin + wide.yMax) / 2).toBeCloseTo(2);
    expect(expandGraphView(view, Number.NaN)).toEqual(view);
  });
});
