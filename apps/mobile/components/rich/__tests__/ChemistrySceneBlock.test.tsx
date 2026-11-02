import { render } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import { ChemistrySceneBlock } from "@/components/rich/ChemistrySceneBlock";
import { Space } from "@/lib/space";

// The real English strings, so a key that is missing from en.json shows up as a raw key.
jest.mock("react-i18next", () => {
  const english = jest.requireActual("@/lib/i18n/en.json") as Record<string, string>;
  return {
    useTranslation: () => ({
      t: (key: string, options?: Record<string, unknown>) =>
        String(english[key] ?? key).replace(/\{\{(\w+)\}\}/g, (_, name: string) =>
          String(options?.[name]),
        ),
    }),
  };
});

jest.mock("@/lib/theme", () => {
  const actual = jest.requireActual("@/lib/theme");
  return { ...actual, useTheme: () => actual.lightTheme };
});

jest.mock("@/ui/icons/Icon", () => ({ Icon: () => null }));

function scene(body: Record<string, unknown>) {
  return <ChemistrySceneBlock content={JSON.stringify(body)} />;
}

describe("ChemistrySceneBlock", () => {
  it("draws the verified water angle", async () => {
    const { getByText } = await render(
      scene({
        kind: "vsepr",
        title: "H2O",
        central: "O",
        terminals: ["H", "H"],
        lone_pairs: 2,
        geometry: "bent",
        bond_angle: "104.5°",
        electron_geometry: "tetrahedral",
        ideal_angle: "109.5°",
      }),
    );
    expect(getByText("H2O")).toBeTruthy();
    expect(getByText("104.5°")).toBeTruthy();
    expect(getByText("H · H around O")).toBeTruthy();
    expect(getByText("Lone pairs: 2")).toBeTruthy();
    expect(getByText("tetrahedral, ideal 109.5°")).toBeTruthy();
  });

  it("keeps its text inset from the card's edge, like the header", async () => {
    const { getByTestId } = await render(
      scene({
        kind: "cell",
        title: "Galvanic cell",
        anode: "Zn",
        cathode: "Cu",
        potential: "1.10 V",
        electrons: "anode to cathode",
      }),
    );
    // Flush with the border, the rounded corner cut the first letter off the last line.
    expect(StyleSheet.flatten(getByTestId("chemistry-scene-body").props.style)).toMatchObject({
      paddingHorizontal: Space.sm,
    });
  });

  it("says one lone pair without a plural form", async () => {
    const { getByText } = await render(
      scene({
        kind: "vsepr",
        title: "NH3",
        central: "N",
        terminals: ["H", "H", "H"],
        lone_pairs: 1,
        geometry: "trigonal pyramidal",
        bond_angle: "107°",
        electron_geometry: "tetrahedral",
        ideal_angle: "109.5°",
      }),
    );
    expect(getByText("Lone pairs: 1")).toBeTruthy();
  });

  it("lays an atom tally out as a table with its own header and a charge row", async () => {
    const { getByText, getAllByText } = await render(
      scene({
        kind: "balance",
        title: "Atom tally",
        rows: [
          { element: "N", left: 2, right: 2 },
          { element: "H", left: 6, right: 6 },
        ],
        charge: { left: 0, right: 0 },
      }),
    );
    expect(getByText("Atom tally")).toBeTruthy();
    expect(getByText("Element")).toBeTruthy();
    expect(getByText("Reactants")).toBeTruthy();
    expect(getByText("Products")).toBeTruthy();
    expect(getByText("Charge")).toBeTruthy();
    expect(getByText("H")).toBeTruthy();
    expect(getAllByText("6")).toHaveLength(2);
  });

  it("labels the columns of an ICE table", async () => {
    const { getByText } = await render(
      scene({
        kind: "equilibrium",
        title: "ICE table",
        rows: [
          { species: "N2", initial: "1", change: "−x", equilibrium: "0.9 mol/L" },
          { species: "NH3", initial: "0", change: "+2x", equilibrium: "0.2 mol/L" },
        ],
      }),
    );
    expect(getByText("ICE table")).toBeTruthy();
    for (const heading of ["Species", "Initial", "Change", "Equilibrium"]) {
      expect(getByText(heading)).toBeTruthy();
    }
    expect(getByText("+2x")).toBeTruthy();
  });

  it("names titration anchors and shows the detail the server sent", async () => {
    const { getByText } = await render(
      scene({
        kind: "titration",
        title: "Titration",
        region: "before equivalence",
        anchors: [
          { label: "half-equivalence", ph: "4.74", volume: "0.0125 L" },
          { label: "solved", value: "pH = 5.2", detail: "buffer region" },
        ],
      }),
    );
    expect(getByText("Half-equivalence · pH 4.74 · 0.0125 L")).toBeTruthy();
    expect(getByText("Solved · pH = 5.2 · buffer region")).toBeTruthy();
  });

  it("translates the electron flow of a galvanic cell", async () => {
    const { getByText } = await render(
      scene({
        kind: "cell",
        title: "Galvanic cell",
        anode: "Zn",
        cathode: "Cu",
        potential: "1.10 V",
        electrons: "anode to cathode",
      }),
    );
    expect(getByText("Galvanic cell")).toBeTruthy();
    expect(getByText("Anode: Zn")).toBeTruthy();
    expect(getByText("Cathode: Cu")).toBeTruthy();
    expect(getByText("Electrons: anode to cathode")).toBeTruthy();
  });

  it("shows a diagram error for invalid JSON", async () => {
    const { getByText, queryByText } = await render(<ChemistrySceneBlock content="{" />);
    expect(getByText("Chemistry diagram")).toBeTruthy();
    expect(getByText("Could not render that diagram.")).toBeTruthy();
    expect(queryByText("Molecule")).toBeNull();
  });
});
