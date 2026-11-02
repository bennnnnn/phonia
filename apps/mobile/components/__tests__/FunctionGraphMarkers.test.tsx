import { render } from "@testing-library/react-native";

import { FunctionGraphBlock } from "@/components/rich/FunctionGraphBlock";

jest.mock("@/lib/skiaAvailability", () => ({ isSkiaAvailable: () => false }));

const mockCircle = jest.fn((_props: Record<string, unknown>) => null);
jest.mock("react-native-svg", () => ({
  ...jest.requireActual("react-native-svg"),
  __esModule: true,
  Circle: (props: Record<string, unknown>) => mockCircle(props),
}));

describe("function graph point markers", () => {
  beforeEach(() => mockCircle.mockClear());

  it.each([
    ["sin(x)", Math.sin],
    ["x + 0.1", (x: number) => x + 0.1],
  ] as const)("does not invent a hollow origin on the dense %s curve", async (expr, evaluate) => {
    const points = Array.from({ length: 97 }, (_, i) => {
      const x = -3.14 + i * 6.28 / 96;
      return [x, evaluate(x)];
    });
    const content = JSON.stringify({ type: "function", expr, points, x_min: -3.14, x_max: 3.14 });
    const { toJSON } = await render(<FunctionGraphBlock content={content} />);
    expect(mockCircle).not.toHaveBeenCalled();
    expect(JSON.stringify(toJSON())).toContain("RNSVGPath");
  });

  it("retains filled markers for each explicit sample, including the origin", async () => {
    const content = JSON.stringify({ type: "function", expr: "x", points: [[0, 0], [1, 1]] });
    await render(<FunctionGraphBlock content={content} />);
    expect(mockCircle).toHaveBeenCalledTimes(2);
    const markers = mockCircle.mock.calls.map(([props]) => props);
    for (const marker of markers) {
      expect(marker.fill).toBeTruthy();
      expect(marker.fill).not.toBe("none");
      expect(marker.stroke).toBeUndefined();
    }
    expect(markers[0].cx).toBeLessThan(markers[1].cx as number);
    expect(markers[0].cy).toBeGreaterThan(markers[1].cy as number);
  });

  it("marks the two roots of a shifted quadratic on the x-axis", async () => {
    const points = Array.from({ length: 97 }, (_, i) => {
      const x = -10 + (20 * i) / 96;
      return [x, 4 * x * x - 5 * x - 12];
    });
    const content = JSON.stringify({
      type: "function",
      expr: "4*x**2-5*x-12",
      points,
      x_min: -10,
      x_max: 10,
    });
    await render(<FunctionGraphBlock content={content} />);
    const roots = mockCircle.mock.calls.map(([props]) => props);
    expect(roots).toHaveLength(2);
    const xs = roots.map((m) => m.cx as number).sort((a, b) => a - b);
    expect(xs[1] - xs[0]).toBeGreaterThan(20);
  });
});
