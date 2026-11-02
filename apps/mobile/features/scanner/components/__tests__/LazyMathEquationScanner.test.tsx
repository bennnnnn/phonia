import { render, screen } from "@testing-library/react-native";

import { LazyMathEquationScanner } from "@/features/scanner/components/LazyMathEquationScanner";

const mockModuleLoads: string[] = [];

jest.mock("@/features/scanner/components/MathEquationScanner", () => {
  const { createElement } = jest.requireActual<typeof import("react")>("react");
  const { Text } = jest.requireActual<typeof import("react-native")>("react-native");
  mockModuleLoads.push("scanner");
  return {
    MathEquationScanner: ({ visible }: { visible: boolean }) =>
      createElement(Text, { testID: "math-scanner" }, visible ? "open" : "closed"),
  };
});

const handlers = {
  onClose: jest.fn(),
  onCaptured: jest.fn(),
};

describe("LazyMathEquationScanner", () => {
  it("loads and mounts the scanner only once it is opened, then keeps it mounted", async () => {
    const view = await render(<LazyMathEquationScanner visible={false} {...handlers} />);
    expect(screen.queryByTestId("math-scanner")).toBeNull();
    expect(mockModuleLoads).toEqual([]);

    await view.rerender(<LazyMathEquationScanner visible {...handlers} />);
    expect(await screen.findByText("open")).toBeOnTheScreen();
    expect(mockModuleLoads).toEqual(["scanner"]);

    // Closing hands visible=false to the scanner, which plays its own dismissal.
    await view.rerender(<LazyMathEquationScanner visible={false} {...handlers} />);
    expect(screen.getByTestId("math-scanner")).toHaveTextContent("closed");
    expect(mockModuleLoads).toEqual(["scanner"]);
  });
});
