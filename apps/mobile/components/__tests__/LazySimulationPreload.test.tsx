import { StyleSheet } from "react-native";
import { act, render, screen } from "@testing-library/react-native";

import { LazySimulationBlock, preloadSimulationSizing } from "@/components/rich/LazyHeavyRich";

const mockSizingLoads: string[] = [];
jest.mock("@/components/rich/simulationPlaceholder", () => {
  mockSizingLoads.push("sizing");
  return { simulationFencePlaceholderHeight: jest.fn(() => 321) };
});
// The scene's renderer never arrives here, so its placeholder stays on screen.
jest.mock("@/components/rich/SimulationBlock", () => ({
  SimulationBlock: () => {
    throw new Promise(() => {});
  },
}));

describe("preloadSimulationSizing", () => {
  it("loads the sizing parsers ahead of the first scene, once", async () => {
    expect(mockSizingLoads).toEqual([]);
    await act(async () => {
      preloadSimulationSizing();
      preloadSimulationSizing();
    });
    expect(mockSizingLoads).toEqual(["sizing"]);

    await render(<LazySimulationBlock content={'{"type":"projectile_motion"}'} />);
    const placeholder = screen.getByTestId("rich-load-placeholder");
    expect(StyleSheet.flatten(placeholder.props.style).height).toBe(321);
    expect(mockSizingLoads).toEqual(["sizing"]);
  });
});
