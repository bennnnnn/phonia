/**
 * MoleculeCard — one header, 2D default, optional 3D toggle; copy SMILES.
 */
import React from "react";
import { fireEvent, render } from "@testing-library/react-native";

import { MoleculeCard } from "@/components/rich/MoleculeCard";

jest.mock("@/ui/icons/Icon", () => ({
  Icon: () => null,
}));

jest.mock("@/components/CopyButton", () => {
  const { Text } = jest.requireActual("react-native");
  return {
    CopyButton: ({ text }: { text: string }) => <Text testID="copy-payload">{text}</Text>,
  };
});

jest.mock("@/lib/theme", () => {
  const actual = jest.requireActual("@/lib/theme");
  return { ...actual, useTheme: () => actual.lightTheme };
});

// The 2D structure page is a file read through expo-file-system, whose native
// module cannot load here; with no preview WebView it is never written.
jest.mock("expo-file-system/legacy", () => ({}));

const VALID_SDF = `Ethanol
     RDKit          3D

  3  2  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0  0
    1.5000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0  0
    2.5000    1.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  2  3  1  0
M  END`;

// A view that is switched off is display: none, which the queries skip unless told otherwise.
const HIDDEN_TOO = { includeHiddenElements: true };

describe("MoleculeCard", () => {
  it("shows one header, 2D by default, and copies SMILES not SDF", async () => {
    const content = JSON.stringify({
      smiles: "CCO",
      caption: "Ethanol",
      sdf: VALID_SDF,
    });
    const { getByText, getAllByText, getByTestId, queryByText } = await render(
      <MoleculeCard content={content} />,
    );
    expect(getAllByText("rich.chemistry_structure")).toHaveLength(1);
    expect(getByText("Ethanol")).toBeTruthy();
    expect(getByText("rich.chemistry_dev_build")).toBeTruthy();
    expect(getByText("rich.chemistry_2d")).toBeTruthy();
    expect(getByText("rich.chemistry_3d")).toBeTruthy();
    expect(queryByText("rich.chemistry_style_ball")).toBeNull();
    expect(getByTestId("copy-payload").props.children).toBe("CCO");
    expect(String(getByTestId("copy-payload").props.children)).not.toContain("V2000");
  });

  it("shows a 3D toggle when SDF is present and stays on 2D until chosen", async () => {
    const content = JSON.stringify({ smiles: "CCO", sdf: VALID_SDF });
    const { getByText, getAllByText, getByTestId, queryByText } = await render(
      <MoleculeCard content={content} />,
    );
    expect(getAllByText("rich.chemistry_structure")).toHaveLength(1);
    expect(getByTestId("molecule-mode-2d").props.accessibilityState).toEqual({ checked: true });
    expect(getByTestId("molecule-mode-3d").props.accessibilityState).toEqual({ checked: false });
    expect(getByText("rich.chemistry_dev_build")).toBeTruthy();
    expect(queryByText("rich.chemistry_style_ball")).toBeNull();
    expect(getByTestId("copy-payload").props.children).toBe("CCO");
  });

  it("hides the 3D toggle when there is no SDF", async () => {
    const { getAllByText, queryByText } = await render(
      <MoleculeCard content={JSON.stringify({ smiles: "CCO" })} />,
    );
    expect(getAllByText("CCO").length).toBeGreaterThan(0);
    expect(queryByText("rich.chemistry_3d")).toBeNull();
    expect(queryByText("rich.chemistry_style_ball")).toBeNull();
  });

  it("renders an invalid-structure hint when SMILES is missing", async () => {
    const { getByText } = await render(<MoleculeCard content="not a molecule" />);
    expect(getByText("rich.chemistry_invalid")).toBeTruthy();
  });

  it("keeps the 2D view mounted while 3D is shown, and 3D mounted when flipping back", async () => {
    const content = JSON.stringify({ smiles: "CCO", sdf: VALID_SDF });
    const { getByText, getByTestId, queryByTestId } = await render(
      <MoleculeCard content={content} />,
    );
    // 3D is not built until it is asked for.
    expect(queryByTestId("molecule-style-spacefill")).toBeNull();

    await fireEvent.press(getByTestId("molecule-mode-3d"));
    expect(getByTestId("molecule-mode-3d").props.accessibilityState).toEqual({ checked: true });
    expect(getByTestId("molecule-style-spacefill")).toBeTruthy();
    // The 2D view is hidden, not torn down: its WebView would reload on the way back.
    expect(getByText("rich.chemistry_dev_build", HIDDEN_TOO)).toBeTruthy();

    await fireEvent.press(getByTestId("molecule-style-spacefill"));
    await fireEvent.press(getByTestId("molecule-mode-2d"));
    expect(getByTestId("molecule-mode-2d").props.accessibilityState).toEqual({ checked: true });
    // Back on 2D, the 3D view and the style chosen in it are still there.
    expect(getByTestId("molecule-style-spacefill", HIDDEN_TOO).props.accessibilityState).toEqual({
      checked: true,
    });
  });

  it("names the copy button for what it copies", async () => {
    const { getByTestId } = await render(
      <MoleculeCard content={JSON.stringify({ smiles: "CCO" })} />,
    );
    expect(getByTestId("copy-payload").props.children).toBe("CCO");
  });
});
