import {
  collapseAdjacentMoleculeFences,
  dropRedundantMolecule3dFences,
  parseMoleculeFence,
} from "@/lib/chemistry/moleculePair";

const SDF = `Ethanol
     RDKit          3D

  3  2  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0  0
    1.5000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0  0
    2.5000    1.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  2  3  1  0
M  END`;

describe("collapseAdjacentMoleculeFences", () => {
  it("replaces a closed smiles + molecule3d pair with one molecule fence", () => {
    const input = "```smiles\nCCO\n```\n\n```molecule3d\n" + SDF + "\n```";
    const out = collapseAdjacentMoleculeFences(input);
    expect(out).toContain("```molecule\n");
    expect(out).not.toContain("```smiles");
    expect(out).not.toContain("```molecule3d");
    const match = /```molecule\n([\s\S]*?)\n```/.exec(out);
    expect(match).not.toBeNull();
    expect(parseMoleculeFence(match![1]!)).toEqual({
      smiles: "CCO",
      caption: null,
      sdf: SDF,
    });
  });

  it("pairs chemistry lang the same way and keeps a SMILES caption", () => {
    const input = "```chemistry\nEthanol\nCCO\n```\n```molecule3d\n" + SDF + "\n```";
    const out = collapseAdjacentMoleculeFences(input);
    const body = out.replace(/^```molecule\n/, "").replace(/\n```$/, "");
    expect(parseMoleculeFence(body)).toEqual({
      smiles: "CCO",
      caption: "Ethanol",
      sdf: SDF,
    });
  });

  it("leaves smiles-only, molecule3d-only, and prose-separated pairs alone", () => {
    expect(collapseAdjacentMoleculeFences("```smiles\nCCO\n```")).toContain("```smiles");
    expect(collapseAdjacentMoleculeFences("```molecule3d\n" + SDF + "\n```")).toContain(
      "```molecule3d",
    );
    const split =
      "```smiles\nCCO\n```\n\nSee the 3D view:\n\n```molecule3d\n" + SDF + "\n```";
    expect(collapseAdjacentMoleculeFences(split)).toBe(split);
  });

  it("does not collapse while the 3D fence is still open (streaming)", () => {
    const input = "```smiles\nCCO\n```\n\n```molecule3d\nEthanol\n     RDKit";
    expect(collapseAdjacentMoleculeFences(input)).toBe(input);
  });
});

describe("dropRedundantMolecule3dFences", () => {
  it("drops a leftover molecule3d after a combined molecule card", () => {
    const combined =
      "```molecule\n" + JSON.stringify({ smiles: "CCO", sdf: SDF }) + "\n```";
    const input = combined + "\n\n## 3D Structure\n\n```molecule3d\nnot a real sdf\n```";
    const out = dropRedundantMolecule3dFences(input);
    expect(out).toContain("```molecule\n");
    expect(out).not.toContain("```molecule3d");
    expect(out).not.toMatch(/3D Structure/i);
  });

  it("keeps standalone molecule3d when there is no combined card", () => {
    const input = "## 3D Structure\n\n```molecule3d\n" + SDF + "\n```";
    expect(dropRedundantMolecule3dFences(input)).toBe(input);
  });
});

describe("parseMoleculeFence", () => {
  it("reads JSON smiles/caption/sdf", () => {
    expect(
      parseMoleculeFence(JSON.stringify({ smiles: "CCO", caption: "Ethanol", sdf: SDF })),
    ).toEqual({ smiles: "CCO", caption: "Ethanol", sdf: SDF });
  });

  it("falls back to a chemistry SMILES body", () => {
    expect(parseMoleculeFence("Ethanol\nCCO")).toEqual({
      smiles: "CCO",
      caption: "Ethanol",
      sdf: null,
    });
  });

  it("returns null for empty or non-SMILES JSON", () => {
    expect(parseMoleculeFence("")).toBeNull();
    expect(parseMoleculeFence(JSON.stringify({ sdf: SDF }))).toBeNull();
  });

  it("holds a JSON SMILES to the same rules as a smiles fence", () => {
    // The string reaches the SmilesDrawer page, so the JSON path may not skip the gate.
    expect(parseMoleculeFence(JSON.stringify({ smiles: "C`C" }))).toBeNull();
    expect(parseMoleculeFence(JSON.stringify({ smiles: "C</script>" }))).toBeNull();
    expect(parseMoleculeFence(JSON.stringify({ smiles: "C".repeat(501) }))).toBeNull();
    expect(parseMoleculeFence(JSON.stringify({ smiles: "smiles: CCO" }))?.smiles).toBe("CCO");
    expect(parseMoleculeFence(JSON.stringify({ smiles: "O2" }))?.smiles).toBe("O=O");
  });
});

describe("fence syntax the pairing has to understand", () => {
  it("pairs fences written with longer backtick runs", () => {
    const input = "````smiles\nCCO\n````\n\n````molecule3d\n" + SDF + "\n````";
    const out = collapseAdjacentMoleculeFences(input);
    expect(out).toContain("```molecule\n");
    expect(out).not.toContain("````");
  });

  it("pairs fences written with tildes", () => {
    const input = "~~~smiles\nCCO\n~~~\n~~~molecule3d\n" + SDF + "\n~~~";
    expect(collapseAdjacentMoleculeFences(input)).toContain("```molecule\n");
  });

  it("does not pair a smiles fence quoted inside another fence", () => {
    const input =
      "````md\n```smiles\nCCO\n```\n\n```molecule3d\n" + SDF + "\n```\n````";
    expect(collapseAdjacentMoleculeFences(input)).toBe(input);
  });

  it("drops a leftover molecule3d written with tildes", () => {
    const combined = "```molecule\n" + JSON.stringify({ smiles: "CCO", sdf: SDF }) + "\n```";
    const out = dropRedundantMolecule3dFences(combined + "\n\n~~~molecule3d\nnot a real sdf\n~~~");
    expect(out).not.toContain("molecule3d");
  });
});
