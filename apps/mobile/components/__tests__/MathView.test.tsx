import { render } from "@testing-library/react-native";

import { MathBlock } from "@/components/rich/MathView";

// Capture what MathBlock hands to the MathJax-SVG renderer; the renderer
// itself (incl. its native-fallback branch) is covered in MathSvgView tests.
const mockSvgView = jest.fn((_props: { latex: string }) => null);
jest.mock("@/components/rich/MathSvgView", () => ({
  MathSvgView: (props: { latex: string }) => mockSvgView(props),
}));

describe("MathBlock", () => {
  beforeEach(() => mockSvgView.mockClear());

  it("renders a single equation through MathSvgView", async () => {
    await render(<MathBlock latex="x + 1 = 2" />);
    expect(mockSvgView).toHaveBeenCalledWith(
      expect.objectContaining({ latex: "x + 1 = 2" }),
    );
  });

  it("renders nothing for an empty/redundant-dollar-wrapped-to-empty body", async () => {
    const { toJSON } = await render(<MathBlock latex="   " />);
    expect(toJSON()).toBeNull();
    expect(mockSvgView).not.toHaveBeenCalled();
  });

  it("splits a multi-line fence body into one MathSvgView per line", async () => {
    await render(<MathBlock latex={"x = 1\ny = 2"} />);
    expect(mockSvgView.mock.calls.map((c) => c[0].latex)).toEqual(["x = 1", "y = 2"]);
  });

  it("BUG FIX regression: strips a scattered $...$ wrap around one command, not just a whole-body wrap", async () => {
    // Reported live (screenshot): "n! = n $\times$ (n-1)!" rendered in red.
    // The model wrapped only \times in $...$, leaving the rest of the fence
    // body bare — stripRedundantDollarWrap only catches a wrap around the
    // ENTIRE body, so the literal "$" must be stripped before rendering.
    await render(<MathBlock latex={String.raw`n! = n $\times$ (n-1)!`} />);
    expect(mockSvgView).toHaveBeenCalledWith(
      expect.objectContaining({ latex: String.raw`n! = n \times (n-1)!` }),
    );
  });
});
