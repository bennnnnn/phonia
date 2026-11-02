import {
  sliderFraction,
  sliderValueAt,
  snapSliderValue,
  steppedSliderValue,
} from "@/ui/controls/sliderValue";

describe("snapSliderValue", () => {
  it.each([
    [6.27, 0, 15, 0.05, 6.25],
    [6.28, 0, 15, 0.05, 6.3],
    [0.30000000000000004, 0, 1, 0.1, 0.3],
    [301234, 50000, 1000000, 5000, 300000],
    [-3, 0, 15, 0.05, 0],
    [99, 1, 40, 1, 40],
    [7.5, 1, 10, 0, 7.5],
    [1.234, 1.2, 2, 0.05, 1.25],
  ])("snaps %p in %p…%p by %p to %p", (raw, min, max, step, expected) => {
    expect(snapSliderValue(raw, min, max, step)).toBe(expected);
  });

  it("keeps a range with no width at its minimum", () => {
    expect(snapSliderValue(5, 3, 3, 1)).toBe(3);
  });

  it("reads a step written in exponent form", () => {
    expect(snapSliderValue(0.00000123, 0, 1, 1e-7)).toBe(0.0000012);
  });
});

describe("sliderFraction and sliderValueAt", () => {
  it("places a value on the track and back", () => {
    expect(sliderFraction(7.5, 0, 15)).toBe(0.5);
    expect(sliderFraction(-1, 0, 15)).toBe(0);
    expect(sliderFraction(20, 0, 15)).toBe(1);
    expect(sliderValueAt(0.5, 0, 15, 0.05)).toBe(7.5);
    expect(sliderValueAt(1.4, 1, 40, 1)).toBe(40);
  });
});

describe("steppedSliderValue", () => {
  it("steps by one step and stays in range", () => {
    expect(steppedSliderValue(6.25, 1, 0, 15, 0.05)).toBe(6.3);
    expect(steppedSliderValue(6.25, -1, 0, 15, 0.05)).toBe(6.2);
    expect(steppedSliderValue(15, 1, 0, 15, 0.05)).toBe(15);
    expect(steppedSliderValue(0, -1, 0, 15, 0.05)).toBe(0);
  });
});
