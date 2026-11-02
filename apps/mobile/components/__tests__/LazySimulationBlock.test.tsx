import { Dimensions, StyleSheet } from "react-native";
import { render, screen } from "@testing-library/react-native";

import { LazySimulationBlock } from "@/components/rich/LazyHeavyRich";
import { simulationPlaceholderHeight } from "@/components/rich/simulationPlaceholder";

// The scene's renderer never arrives here, so its placeholder stays on screen.
jest.mock("@/components/rich/SimulationBlock", () => ({
  SimulationBlock: () => {
    throw new Promise(() => {});
  },
}));

const PROJECTILE = JSON.stringify({
  type: "projectile_motion",
  title: "Projectile",
  bodies: [{ radius: 0.5, role: "primary", path: [[0, 0], [10, 7], [20, 10], [30, 7], [40, 0]] }],
  x_min: 0,
  x_max: 42,
  y_min: 0,
  y_max: 14,
  arrows: ["velocity", "gravity"],
  ground: true,
});

function placeholderHeight(index = 0): number {
  const placeholder = screen.getAllByTestId("rich-load-placeholder")[index];
  return StyleSheet.flatten(placeholder.props.style).height as number;
}

describe("LazySimulationBlock", () => {
  it("holds the scene's own height, from the sizing parsers it loads on first use", async () => {
    const screenWidth = Dimensions.get("window").width;
    const exact = simulationPlaceholderHeight(PROJECTILE, screenWidth);

    await render(<LazySimulationBlock content={PROJECTILE} />);
    expect(placeholderHeight()).toBe(exact);

    // Later scenes size from the loaded parsers on their first render.
    await render(<LazySimulationBlock content={PROJECTILE} />);
    expect(placeholderHeight()).toBe(exact);
  });
});
