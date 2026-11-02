import { cellAtPoint, cellCenter, dotGridLayout } from "@/features/images/model/dotGrid";
import {
  estimateImageGenPercent,
  IMAGE_GEN_PROGRESS_CAP,
  imageGenStageIndex,
} from "@/features/images/model/imageGenProgress";

describe("estimateImageGenPercent", () => {
  it.each([
    [0, 1],
    [3_000, 21],
    [12_000, 60],
    [24_000, 82],
    [60_000, 94],
  ])("at %i ms shows %i%%", (elapsed, percent) => {
    expect(estimateImageGenPercent(elapsed)).toBe(percent);
  });

  it("only rises and never passes the cap", () => {
    let last = 0;
    for (let ms = 0; ms <= 600_000; ms += 250) {
      const value = estimateImageGenPercent(ms);
      expect(value).toBeGreaterThanOrEqual(last);
      expect(value).toBeLessThanOrEqual(IMAGE_GEN_PROGRESS_CAP);
      last = value;
    }
    expect(last).toBe(IMAGE_GEN_PROGRESS_CAP);
  });

  it("treats a bad clock as the start", () => {
    expect(estimateImageGenPercent(-5_000)).toBe(1);
    expect(estimateImageGenPercent(Number.NaN)).toBe(1);
  });
});

describe("imageGenStageIndex", () => {
  it("walks four stages with the estimate and holds the last", () => {
    expect([1, 23, 24, 47, 48, 71, 72, 95].map((p) => imageGenStageIndex(p, 4))).toEqual([
      0, 0, 1, 1, 2, 2, 3, 3,
    ]);
  });

  it("handles one stage or none", () => {
    expect(imageGenStageIndex(80, 1)).toBe(0);
    expect(imageGenStageIndex(80, 0)).toBe(0);
  });
});

describe("dotGridLayout", () => {
  it("centers as many dots as fit", () => {
    const grid = dotGridLayout(148, 189, 13);
    expect(grid).toMatchObject({ cols: 11, rows: 14, pitch: 13 });
    expect(grid.originX).toBeCloseTo(9);
    expect(grid.originY).toBeCloseTo(10);
    const last = cellCenter(grid, { x: grid.cols - 1, y: grid.rows - 1 });
    expect(148 - last.x).toBeCloseTo(grid.originX);
    expect(189 - last.y).toBeCloseTo(grid.originY);
  });

  it("maps a tap to the nearest cell, clamped to the grid", () => {
    const grid = dotGridLayout(148, 189, 23);
    expect(cellAtPoint(grid, grid.originX + 23 * 2 + 8, grid.originY + 23 - 9)).toEqual({
      x: 2,
      y: 1,
    });
    expect(cellAtPoint(grid, -50, 999)).toEqual({ x: 0, y: grid.rows - 1 });
  });
});
