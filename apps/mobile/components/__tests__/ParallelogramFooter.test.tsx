import { render } from "@testing-library/react-native";

import { GeometryBlock } from "@/components/rich/GeometryBlock";
import { parseGeometrySpec } from "@/lib/math/geometryBlock";

const mockSvgText = jest.fn((_props: Record<string, unknown>) => null);
jest.mock("react-native-svg", () => ({
  ...jest.requireActual("react-native-svg"),
  __esModule: true,
  Text: (props: Record<string, unknown>) => mockSvgText(props),
}));

const dimensions = { type: "parallelogram", base: 8, height: 4, side: 5, unit: "units" };

describe("parallelogram requested quantity footer", () => {
  beforeEach(() => mockSvgText.mockClear());

  it("renders perimeter for the H17 request instead of its unrelated area", async () => {
    const content = JSON.stringify({ ...dimensions, area: 32, perimeter: 26, show_perimeter: true });
    expect(parseGeometrySpec(content)).toMatchObject({ show_perimeter: true, area: 32, perimeter: 26 });
    await render(<GeometryBlock content={content} />);
    const labels = mockSvgText.mock.calls.map(([props]) => props.children);
    expect(labels).toContain("Perimeter:\u00A026 units");
    expect(labels.some((label) => String(label).startsWith("Area"))).toBe(false);
  });

  it.each([undefined, false, "true"])("preserves the area footer unless the canonical boolean is true (%s)", async (flag) => {
    const content = JSON.stringify({ ...dimensions, area: 32, show_perimeter: flag });
    await render(<GeometryBlock content={content} />);
    const labels = mockSvgText.mock.calls.map(([props]) => props.children);
    expect(labels).toContain("Area:\u00A032 units²");
    expect(labels.some((label) => String(label).startsWith("Perimeter"))).toBe(false);
  });

  it("keeps the canonical formatted perimeter and explicit unit", async () => {
    await render(<GeometryBlock content={JSON.stringify({
      ...dimensions, unit: "cm", show_perimeter: true, labels: { perimeter: "26 cm" },
    })} />);
    expect(mockSvgText.mock.calls.map(([props]) => props.children)).toContain("Perimeter:\u00A026 cm");
  });
});
