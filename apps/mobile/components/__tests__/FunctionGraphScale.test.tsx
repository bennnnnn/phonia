import { render } from "@testing-library/react-native";

import { FunctionGraphBlock } from "@/components/rich/FunctionGraphBlock";

jest.mock("@/lib/skiaAvailability", () => ({ isSkiaAvailable: () => false }));

const mockPolyline = jest.fn((_props: Record<string, unknown>) => null);
jest.mock("react-native-svg", () => ({
  ...jest.requireActual("react-native-svg"),
  __esModule: true,
  Polyline: (props: Record<string, unknown>) => mockPolyline(props),
}));

describe("sampled conic graph rendering", () => {
  it.each([
    ["x**2 + y**2 = 1", 1, 1],
    ["x**2/9 + y**2/4 = 1", 3, 2],
  ] as const)("preserves the actual axis ratio for %s", async (expr, radiusX, radiusY) => {
    mockPolyline.mockClear();
    const points = Array.from({ length: 97 }, (_, i) => {
      const angle = i * Math.PI / 48;
      return [radiusX * Math.cos(angle), radiusY * Math.sin(angle)];
    });
    const content = JSON.stringify({
      type: "function", expr, title: expr, points,
      x_min: -2 * radiusX, x_max: 2 * radiusX,
      y_min: -2 * radiusY, y_max: 2 * radiusY,
    });
    const { toJSON } = await render(<FunctionGraphBlock content={content} />);
    const drawn = String(mockPolyline.mock.calls[0][0].points).split(" ").map((point) => point.split(",").map(Number));
    expect(drawn).toHaveLength(97);
    const width = Math.max(...drawn.map(([x]) => x)) - Math.min(...drawn.map(([x]) => x));
    const height = Math.max(...drawn.map(([, y]) => y)) - Math.min(...drawn.map(([, y]) => y));
    expect(width / height).toBeCloseTo(radiusX / radiusY, 3);
    if (radiusX === 1) {
      const tree = JSON.stringify(toJSON());
      expect(tree).toContain('"content":"-3"');
      expect(tree).toContain('"content":"3"');
    }
  });
});

describe("what the card opens on", () => {
  const plotted = () =>
    mockPolyline.mock.calls.flatMap(([props]) =>
      String(props.points).split(" ").map((point) => point.split(",").map(Number)),
    );
  const inPlot = ([px, py]: number[]) => px >= 16 && px <= 336 - 16 && py >= 16 && py <= 220 - 16;

  it.each([
    ["x = 8", { type: "vertical", expr: "x = 8", x: 8, y_min: -10, y_max: 10, x_min: 0, x_max: 16 }],
    ["y = 7", {
      type: "function",
      expr: "7",
      points: Array.from({ length: 96 }, (_, i) => [-10 + (20 * i) / 95, 7]),
    }],
  ])("draws %s inside the plot, not past its edge", async (_name, fence) => {
    mockPolyline.mockClear();
    await render(<FunctionGraphBlock content={JSON.stringify(fence)} />);
    const points = plotted();
    expect(points.length).toBeGreaterThan(1);
    expect(points.some(inPlot)).toBe(true);
  });
});

describe("an x-range given in π", () => {
  const sine = Array.from({ length: 96 }, (_, i) => {
    const x = (2 * Math.PI * i) / 95;
    return [x, Math.sin(x)];
  });

  it("labels the x axis π/2, π, 3π/2, 2π for sin x from 0 to 2π", async () => {
    const content = JSON.stringify({
      type: "function", expr: "sin(x)", points: sine,
      x_min: 0, x_max: 2 * Math.PI, domain_explicit: true,
    });
    const tree = JSON.stringify((await render(<FunctionGraphBlock content={content} />)).toJSON());
    for (const label of ["π/2", "π", "3π/2", "2π"]) expect(tree).toContain(`"content":"${label}"`);
    expect(tree).not.toContain('"content":"6"');
  });

  it("keeps numbers for a range not given in π", async () => {
    const content = JSON.stringify({
      type: "function", expr: "sin(x)", points: sine,
      x_min: 0, x_max: 6, domain_explicit: true,
    });
    const tree = JSON.stringify((await render(<FunctionGraphBlock content={content} />)).toJSON());
    expect(tree).not.toContain("π");
  });
});
