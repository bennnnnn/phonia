import { graphAxisTicks } from "@/lib/math/graphBlock";
import { defaultInteractiveBounds } from "@/lib/math/graphViewport";
import {
  axisTicksW,
  clampGraphViewW,
  dockAxisW,
  formatShortW,
  formatTickW,
  mapPointW,
  nearestSampleW,
  nearestTraceSampleW,
  tickCountW,
  unmapPointW,
} from "@/lib/math/graphWorklets";

// The Skia explorer's ticks come from axisTicksW, the SVG chart's from
// graphAxisTicks; on a school window the two explorers must agree.
describe("graphWorklets parity", () => {
  it("clamp falls back to the default window on a degenerate one", () => {
    expect(clampGraphViewW({ xMin: 2, xMax: 2, yMin: 0, yMax: 1 })).toEqual(
      defaultInteractiveBounds(1.7),
    );
  });

  it("ticks match graphAxisTicks on an integer window", () => {
    const view = defaultInteractiveBounds(1.75);
    expect(axisTicksW(view.xMin, view.xMax)).toEqual(
      graphAxisTicks(view.xMin, view.xMax, tickCountW(view.xMin, view.xMax), true),
    );
  });

  it("regenerates visible tick values after a pan and zoom", () => {
    const panned = axisTicksW(14, 26);
    const zoomedOut = axisTicksW(-60, 60);

    expect(panned.every((tick) => tick >= 14 && tick <= 26)).toBe(true);
    expect(panned).not.toContain(0);
    expect(zoomedOut).toEqual(expect.arrayContaining([-60, -30, 0, 30, 60]));
  });

  it("map/unmap round-trips", () => {
    const b = { xMin: -6, xMax: 6, yMin: -4, yMax: 4 };
    const { px, py } = mapPointW(2.5, -1.5, b, 360, 220, 28);
    const back = unmapPointW(px, py, b, 360, 220, 28);
    expect(back.x).toBeCloseTo(2.5);
    expect(back.y).toBeCloseTo(-1.5);
  });
});

describe("nearestSampleW", () => {
  it("snaps to the closest sampled x and skips non-finite points", () => {
    const points: [number, number][] = [
      [0, 0],
      [Number.NaN, 5],
      [1.9, 3.61],
      [2.1, 4.41],
      [4, 16],
    ];
    const snap = nearestSampleW(points, 2.05);
    expect(snap).toEqual({ x: 2.1, y: 4.41, index: 3 });
  });

  it("returns null for an empty series", () => {
    expect(nearestSampleW([], 1)).toBeNull();
  });
});

describe("nearestTraceSampleW", () => {
  const bounds = { xMin: -6, xMax: 6, yMin: -4, yMax: 4 };
  const width = 360;
  const height = 220;
  const pad = 28;

  it("snaps to the touched curve when multiple curves share the same x", () => {
    const greenPoint = mapPointW(1, 2, bounds, width, height, pad);
    const hit = nearestTraceSampleW(
      [
        { visible: true, color: "blue", points: [[1, 1]] as [number, number][] },
        { visible: true, color: "green", points: [[1, 2]] as [number, number][] },
      ],
      greenPoint.px,
      greenPoint.py,
      bounds,
      width,
      height,
      pad,
    );

    expect(hit).toMatchObject({ x: 1, y: 2, seriesIndex: 1, color: "green" });
  });

  it("does not show a trace when the touch is away from every curve", () => {
    expect(
      nearestTraceSampleW(
        [{ visible: true, color: "blue", points: [[1, 1], [2, 4]] }],
        pad,
        pad,
        bounds,
        width,
        height,
        pad,
      ),
    ).toBeNull();
  });
});

describe("worklet tick formatting", () => {
  it("docks off-screen axes to the nearest visible chart edge", () => {
    expect(dockAxisW(-50, 28, 332)).toBe(28);
    expect(dockAxisW(180, 28, 332)).toBe(180);
    expect(dockAxisW(500, 28, 332)).toBe(332);
  });

  it("formatTickW keeps integers short and fractions precise", () => {
    expect(formatTickW(3)).toBe("3");
    expect(formatTickW(-0)).toBe("0");
    expect(formatTickW(0.5)).toBe("0.5");
  });

  it("formatShortW caps at two decimals for the trace callout", () => {
    expect(formatShortW(6.25)).toBe("6.25");
    expect(formatShortW(2.567)).toBe("2.57");
    expect(formatShortW(3)).toBe("3");
    expect(formatShortW(-0)).toBe("0");
  });
});
