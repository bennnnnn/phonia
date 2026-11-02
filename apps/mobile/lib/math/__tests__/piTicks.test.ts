import { formatPiTickW, piTicksW } from "@/lib/math/graphWorklets";

describe("π ticks", () => {
  it.each([
    [0, 2 * Math.PI, ["0", "π/2", "π", "3π/2", "2π"]],
    [-Math.PI, Math.PI, ["-π", "-π/2", "0", "π/2", "π"]],
    [0, Math.PI, ["0", "π/4", "π/2", "3π/4", "π"]],
    [-2 * Math.PI, 2 * Math.PI, ["-2π", "-π", "0", "π", "2π"]],
    [0, 4 * Math.PI, ["0", "π", "2π", "3π", "4π"]],
  ])("labels %f…%f in π", (min, max, labels) => {
    expect(piTicksW(min, max).map(formatPiTickW)).toEqual(labels);
  });

  it("falls back to even ticks in a window narrower than π/2", () => {
    expect(piTicksW(0, 1).map(formatPiTickW)).toEqual(["0", "0.2", "0.4", "0.6", "0.8", "1"]);
  });
});
