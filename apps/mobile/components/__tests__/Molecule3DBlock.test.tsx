/**
 * Molecule3DBlock — native-first Skia ball-and-stick with an SVG fallback.
 */
import React from "react";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

import { Molecule3DBlock } from "@/components/rich/Molecule3DBlock";

let mockSkiaAvailable = true;

type RenderNode = {
  type?: string;
  props?: Record<string, unknown>;
  children?: unknown[];
};

function nodesIn(value: unknown): RenderNode[] {
  if (Array.isArray(value)) return value.flatMap(nodesIn);
  if (!value || typeof value !== "object") return [];
  const node = value as RenderNode;
  return [node, ...(node.children ?? []).flatMap(nodesIn)];
}

jest.mock("@/ui/icons/Icon", () => ({
  Icon: () => null,
}));

jest.mock("@/components/CopyButton", () => {
  const { Text } = jest.requireActual("react-native");
  return {
    CopyButton: ({ accessibilityLabel }: { accessibilityLabel?: string }) => (
      <Text>{accessibilityLabel}</Text>
    ),
  };
});

jest.mock("@/lib/theme", () => {
  const actual = jest.requireActual("@/lib/theme");
  return { ...actual, useTheme: () => actual.lightTheme };
});

jest.mock("@/lib/skiaAvailability", () => ({
  isSkiaAvailable: () => mockSkiaAvailable,
}));

const VALID_SDF = `Ethanol
     RDKit          3D

  3  2  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0  0
    1.5000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0  0
    2.5000    1.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  2  3  1  0
M  END`;

describe("Molecule3DBlock", () => {
  afterEach(() => {
    mockSkiaAvailable = true;
  });

  it("uses the native Skia renderer when the module is available", async () => {
    const { getByText, getByTestId, getByLabelText, queryByText, queryByTestId } = await render(
      <Molecule3DBlock content={VALID_SDF} />,
    );
    expect(getByText("rich.chemistry_structure")).toBeTruthy();
    expect(getByText("rich.chemistry_style_ball")).toBeTruthy();
    expect(getByText("rich.chemistry_style_sphere")).toBeTruthy();
    expect(getByText("rich.chemistry_style_wire")).toBeTruthy();
    await waitFor(() => expect(getByTestId("molecule-skia-canvas")).toBeTruthy());
    expect(getByLabelText("rich.chemistry_3d_a11y")).toBeTruthy();
    expect(getByText("rich.chemistry_copy_structure")).toBeTruthy();
    expect(queryByText(/V2000/)).toBeNull();
    expect(queryByTestId("molecule-rotate-close")).toBeNull();
    await fireEvent.press(getByTestId("molecule-expand"));
    expect(getByTestId("molecule-rotate-layer")).toBeTruthy();
    expect(getByTestId("molecule-rotate-close")).toBeTruthy();
  });

  it("uses the SVG renderer when native Skia is unavailable", async () => {
    mockSkiaAvailable = false;
    const { getByTestId, queryByTestId, toJSON } = await render(
      <Molecule3DBlock content={VALID_SDF} />,
    );
    expect(getByTestId("molecule-svg-fallback")).toBeTruthy();
    expect(queryByTestId("molecule-skia-canvas")).toBeNull();
    const atomGroups = nodesIn(toJSON()).filter(
      (node) =>
        node.type === "RNSVGGroup" &&
        (node.children ?? []).filter(
          (child) =>
            child != null &&
            typeof child === "object" &&
            (child as RenderNode).type === "RNSVGCircle",
        ).length === 2,
    );
    expect(atomGroups).toHaveLength(3);
    expect(nodesIn(toJSON()).filter((node) => node.type === "RNSVGText")).toHaveLength(3);
    atomGroups.forEach((group) => {
      expect(nodesIn(group).filter((node) => node.type === "RNSVGCircle")).toHaveLength(2);
    });
  });

  it("renders an invalid-structure hint when there is no SDF", async () => {
    const { getByText } = await render(<Molecule3DBlock content="no sdf here" />);
    expect(getByText("rich.chemistry_invalid")).toBeTruthy();
  });
});
