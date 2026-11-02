import { expandBoundsForAxes, graphBounds } from "@/lib/math/graphBlock";
import {
  trajectoryAxisCaptionPosition,
  trajectoryAxisLayout,
} from "@/lib/math/trajectory";

const WIDTH = 342;
const HEIGHT = 220;
const PAD = 40;

describe("native physics trajectory time labels", () => {
  it.each([
    { end: 2.1, points: [[0, 20], [1, 15], [2, 0], [2.1, 0]], labels: ["0.5", "1", "1.5", "2"] },
    { end: 1.05, points: [[0, 20], [0.5, 18.75], [1, 15], [1.05, 14.4875]], labels: ["0.2", "0.4", "0.6", "0.8", "1"] },
  ])("places accurate time labels on the 0–$end second viewport", ({ end, points, labels }) => {
    const bounds = expandBoundsForAxes(graphBounds(points as [number, number][]), { pad: false });
    const layout = trajectoryAxisLayout(bounds, WIDTH, HEIGHT, PAD);

    expect(layout.xTicks.map((tick) => tick.text)).toEqual(labels);
    for (const tick of layout.xTicks) {
      expect(tick.py).toBe(196);
      const timeAtCoordinate = (tick.px - PAD) * end / (WIDTH - PAD * 2);
      expect(timeAtCoordinate).toBeCloseTo(Number(tick.text), 10);
    }
  });

  it("reserves a separate safe band for the full axis label", () => {
    const label = trajectoryAxisCaptionPosition(80, WIDTH, HEIGHT, PAD);
    const plotBottom = HEIGHT - PAD;

    expect(label.px).toBeGreaterThanOrEqual(4);
    expect(label.px + 80).toBeLessThanOrEqual(WIDTH - PAD);
    expect(label.py - 11).toBeGreaterThan(plotBottom);
  });
});
