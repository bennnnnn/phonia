import { parseChemistryScene } from "@/lib/chemistry/scene";

describe("parseChemistryScene", () => {
  it("reads a VSEPR scene with the molecular angle kept separate", () => {
    const scene = parseChemistryScene(
      JSON.stringify({
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
    expect(scene).toMatchObject({
      kind: "vsepr",
      bond_angle: "104.5°",
      ideal_angle: "109.5°",
      lone_pairs: 2,
    });
  });

  it("rejects a scene the server did not describe", () => {
    expect(parseChemistryScene("not json")).toBeNull();
    expect(parseChemistryScene(JSON.stringify({ kind: "orbital", title: "H2O" }))).toBeNull();
  });

  it("reads balance, stoichiometry, titration, and ICE rows", () => {
    const balance = parseChemistryScene(
      JSON.stringify({
        kind: "balance",
        title: "Atom tally",
        rows: [{ element: "H", left: 4, right: 4 }],
        charge: { left: 0, right: 0 },
      }),
    );
    const stoich = parseChemistryScene(
      JSON.stringify({
        kind: "stoich",
        title: "Stoichiometry chain",
        steps: [
          { label: "moles", value: "5 mol" },
          { label: "mass", value: "10 g" },
        ],
      }),
    );
    const titration = parseChemistryScene(
      JSON.stringify({
        kind: "titration",
        title: "Titration",
        region: "half-equivalence: pH = pKa",
        anchors: [{ label: "half-equivalence", ph: "4.74" }, { label: "solved", value: "4.74" }],
      }),
    );
    const ice = parseChemistryScene(
      JSON.stringify({
        kind: "equilibrium",
        title: "ICE table",
        rows: [{ species: "N2O4", initial: "1", change: "−x", equilibrium: "" }],
      }),
    );
    expect(balance).toMatchObject({ kind: "balance", charge: { left: 0, right: 0 } });
    expect(stoich).toMatchObject({ kind: "stoich" });
    expect(titration).toMatchObject({ kind: "titration", region: "half-equivalence: pH = pKa" });
    expect(ice).toMatchObject({ kind: "equilibrium" });
  });

  it("reads a galvanic cell direction", () => {
    const scene = parseChemistryScene(
      JSON.stringify({
        kind: "cell",
        title: "Galvanic cell",
        anode: "Zn",
        cathode: "Cu",
        potential: "1.1 V",
        electrons: "anode to cathode",
      }),
    );
    expect(scene).toMatchObject({ anode: "Zn", cathode: "Cu", electrons: "anode to cathode" });
  });
});
