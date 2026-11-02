import { cellCenter, dotGridLayout, dotHolesPath } from "@/features/images/model/dotGrid";
import { waveBandLayout, waveBandStops } from "@/features/images/model/dotWaveBand";

describe("dotHolesPath", () => {
  const width = 148;
  const height = 189;
  const radius = 1.25;
  const grid = dotGridLayout(width, height, 13);
  const path = dotHolesPath(grid, width, height, radius);

  it("starts with a cover that overhangs the card by a point", () => {
    expect(path.startsWith("M-1 -1H149V190H-1Z")).toBe(true);
  });

  it("cuts one round hole per dot, centered on the shared grid", () => {
    const holes = [...path.matchAll(/M(-?[\d.]+) (-?[\d.]+)a([\d.]+) ([\d.]+) 0 1 0 ([\d.]+) 0a/g)];
    expect(holes).toHaveLength(grid.cols * grid.rows);
    expect(holes).toHaveLength(11 * 14);
    holes.forEach((hole, index) => {
      const [, left, y, rx, ry, across] = hole.map(Number);
      const expected = cellCenter(grid, { x: index % grid.cols, y: Math.floor(index / grid.cols) });
      expect(rx).toBe(radius);
      expect(ry).toBe(radius);
      expect(across).toBe(radius * 2);
      expect(left + radius).toBeCloseTo(expected.x, 2);
      expect(y).toBeCloseTo(expected.y, 2);
    });
  });

  it("closes every hole with a second half circle", () => {
    expect(path.split("a1.25 1.25 0 1 0 -2.5 0Z")).toHaveLength(11 * 14 + 1);
  });
});

describe("waveBandLayout", () => {
  const band = waveBandLayout(148, 189);
  const diagonal = Math.hypot(148, 189);

  it("centers a strip one period longer than the card's diagonal", () => {
    expect(band.height).toBeGreaterThanOrEqual(diagonal);
    expect(band.width).toBe(band.height + band.period);
    expect(band.left + band.width / 2).toBeCloseTo(74);
    expect(band.top + band.height / 2).toBeCloseTo(94.5);
  });

  it("covers the card at every point of the loop", () => {
    for (const progress of [0, 0.25, 0.5, 0.75, 1]) {
      const slide = -band.period / 2 + progress * band.period;
      expect(-band.width / 2 + slide).toBeLessThanOrEqual(-diagonal / 2);
      expect(band.width / 2 + slide).toBeGreaterThanOrEqual(diagonal / 2);
    }
  });
});

describe("waveBandStops", () => {
  const band = waveBandLayout(148, 189);
  const stops = waveBandStops(band, 0.85);

  it("stays inside the strip, in order, peaking at the given opacity", () => {
    for (let i = 0; i < stops.length; i += 1) {
      expect(stops[i].offset).toBeGreaterThanOrEqual(0);
      expect(stops[i].offset).toBeLessThanOrEqual(1);
      if (i > 0) expect(stops[i].offset).toBeGreaterThan(stops[i - 1].offset);
    }
    expect(Math.max(...stops.map((stop) => stop.opacity))).toBe(0.85);
    expect(stops[0].opacity).toBe(0);
    expect(stops[stops.length - 1].opacity).toBe(0);
  });

  it("repeats every period, so sliding one period and starting over has no seam", () => {
    const shift = band.period / band.width;
    const firstPeriod = stops.filter((stop) => stop.offset < shift);
    expect(firstPeriod.length).toBeGreaterThan(0);
    for (const stop of firstPeriod) {
      const twin = stops.find((other) => Math.abs(other.offset - (stop.offset + shift)) < 1e-9);
      expect(twin?.opacity).toBe(stop.opacity);
    }
  });
});
