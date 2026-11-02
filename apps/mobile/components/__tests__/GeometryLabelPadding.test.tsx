import { render } from "@testing-library/react-native";
import { Dimensions } from "react-native";

import { GeometryBlock } from "@/components/rich/GeometryBlock";

type RenderNode = { type?: string; props?: Record<string, unknown>; children?: unknown[] };
function nodesIn(value: unknown): RenderNode[] {
  if (Array.isArray(value)) return value.flatMap(nodesIn);
  if (!value || typeof value !== "object") return [];
  const node = value as RenderNode;
  return [node, ...(node.children ?? []).flatMap(nodesIn)];
}

const cases = [
  { type: "rectangle", width: 3, height: 4, show_area: true },
  { type: "square", side: 3, show_diagonal: true },
  { type: "triangle", base: 3, height: 4 },
  { type: "right_triangle", base: 3, height: 4 },
  { type: "triangle_sides", a: 3, b: 4, c: 5 },
  { type: "trapezoid", top: 4, bottom: 8, height: 5 },
  { type: "parallelogram", base: 8, height: 4, side: 5 },
  { type: "circle", radius: 3 },
  { type: "sector", radius: 4, angle_deg: 90 },
];

describe("geometry dimension label space", () => {
  beforeEach(() => {
    jest.spyOn(Dimensions, "get").mockReturnValue({ width: 390, height: 844, scale: 3, fontScale: 1 });
  });
  afterEach(() => jest.restoreAllMocks());

  it.each(cases)("keeps full generic-unit dimension labels inside a phone-width $type diagram", async (spec) => {
    const { toJSON } = await render(<GeometryBlock content={JSON.stringify({ ...spec, unit: "units" })} />);
    const nodes = nodesIn(toJSON());
    const svg = nodes.find((node) => node.type === "RNSVGSvgView")!;
    const width = Number(svg.props?.width);
    expect(width).toBeLessThanOrEqual(390 - 28);
    let dimensions = 0;
    for (const node of nodes.filter((item) => item.type === "RNSVGText")) {
      const label = nodesIn(node).filter((item) => item.type === "RNSVGTSpan").map((item) => item.props?.content ?? "").join("");
      if (!/^\d+(?:\.\d+)? units$/.test(label)) continue;
      dimensions += 1;
      const font = node.props?.font as { fontSize: number; textAnchor?: string };
      expect([12, 13]).toContain(font.fontSize);
      const labelWidth = Math.ceil(Array.from(label).length * font.fontSize * 0.65);
      const x = Number((node.props?.x as number[])[0]);
      const left = x - (font.textAnchor === "end" ? labelWidth : font.textAnchor === "middle" ? labelWidth / 2 : 0);
      expect(left).toBeGreaterThanOrEqual(0);
      expect(left + labelWidth).toBeLessThanOrEqual(width);
    }
    expect(dimensions).toBeGreaterThan(0);
  });
});
