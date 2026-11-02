import { render } from "@testing-library/react-native";

import { Icon } from "../Icon";
import { GLYPHS } from "../glyphs.generated";
import { lightTheme as mockLightTheme } from "@/lib/theme";

jest.mock("@/lib/theme", () => ({
  ...jest.requireActual("@/lib/theme"),
  useTheme: () => mockLightTheme,
}));

describe("Icon", () => {
  it("exposes which glyph it drew", async () => {
    const { getByTestId } = await render(<Icon name="trash" testID="i" />);
    expect(getByTestId("i").props.name).toBe("trash");
  });

  it("defaults size to 20", async () => {
    const { getByTestId } = await render(<Icon name="copy" testID="i" />);
    expect(getByTestId("i").props.size).toBe(20);
  });

  it("uses the ink color by default (theme text)", async () => {
    const { getByTestId } = await render(<Icon name="copy" testID="i" />);
    expect(getByTestId("i").props.color).toBe(mockLightTheme.text);
  });

  it("uses the danger ink when danger is set", async () => {
    const { getByTestId } = await render(<Icon name="trash" danger testID="i" />);
    expect(getByTestId("i").props.color).toBe(mockLightTheme.danger);
  });

  it("respects an explicit color", async () => {
    const { getByTestId } = await render(<Icon name="copy" color="#ff0000" testID="i" />);
    expect(getByTestId("i").props.color).toBe("#ff0000");
  });

  it("draws every Lucide node of the glyph", async () => {
    const view = await render(<Icon name="share" testID="i" />);
    const svg = view.toJSON() as { children: { children: unknown[] }[] };
    // View > RNSVGSvgView > RNSVGGroup > shapes
    const group = (svg.children[0] as { children: { children: unknown[] }[] }).children[0];
    expect(group.children).toHaveLength(GLYPHS.share.length);
  });

  it("keeps the same on-screen line weight at every row size", async () => {
    const small = await render(<Icon name="check" size={20} testID="a" />);
    const large = await render(<Icon name="check" size={24} testID="b" />);
    const stroke = (tree: unknown) =>
      (tree as { children: { props: { strokeWidth: number } }[] }).children[0].props.strokeWidth;
    // 1.5pt on screen: 1.5 * 24 / size in the 24-unit drawing.
    expect(stroke(small.toJSON())).toBeCloseTo(1.8);
    expect(stroke(large.toJSON())).toBeCloseTo(1.5);
  });

  it("renders the app-only glyphs", async () => {
    const { getByTestId } = await render(<Icon name="menu" testID="menu" />);
    expect(getByTestId("menu").props.name).toBe("menu");
  });
});
