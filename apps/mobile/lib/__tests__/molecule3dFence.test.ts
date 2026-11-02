import { parseMolGeometry, parseMolecule3DFence } from "@/lib/chemistry/molecule3dFence";

import { TRISTEARIN_SDF } from "./fixtures/tristearinSdf";

const VALID_SDF = `Ethanol
     RDKit          3D

  3  2  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0  0
    1.5000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0  0
    2.5000    1.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  2  3  1  0
M  END`;

describe("parseMolecule3DFence", () => {
  it("parses a valid SDF block with M  END", () => {
    const result = parseMolecule3DFence(VALID_SDF);
    expect(result).not.toBeNull();
    expect(result!.sdf).toContain("M  END");
    expect(result!.sdf).toContain("V2000");
    expect(result!.caption).toBe("Ethanol");
  });

  it("parses an SDF block with only program line (caption from first non-empty line)", () => {
    const sdf = `
     RDKit          3D

  3  2  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0  0
    1.5000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0  0
    2.5000    1.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  2  3  1  0
M  END`;
    const result = parseMolecule3DFence(sdf);
    expect(result).not.toBeNull();
    expect(result!.sdf).toContain("M  END");
    // Program/timestamp line is not a user-facing caption.
    expect(result!.caption).toBeNull();
  });

  it("returns null when there is no M  END", () => {
    const result = parseMolecule3DFence("just some text without an SDF block");
    expect(result).toBeNull();
  });

  it("returns null for empty content", () => {
    expect(parseMolecule3DFence("")).toBeNull();
    expect(parseMolecule3DFence("   ")).toBeNull();
  });

  it("strips a prepended formula caption so the MOL header stays 3 lines", () => {
    // Production fences were ```molecule3d\nO2\n<RDKit molblock>``` — that extra
    // line shifted the V2000 counts off line 4 and the viewer drew nothing.
    const sdf = `O2

     RDKit          3D

  2  1  0  0  0  0  0  0  0  0999 V2000
    0.5705    0.0000    0.0000 O   0  0  0  0  0  0
   -0.5705    0.0000    0.0000 O   0  0  0  0  0  0
  1  2  2  0
M  END`;
    const result = parseMolecule3DFence(sdf);
    expect(result).not.toBeNull();
    expect(result!.caption).toBe("O2");
    const mol = result!.sdf;
    const lines = mol.split("\n");
    const countsIdx = lines.findIndex((line) => /V2000/.test(line));
    expect(countsIdx).toBe(3);
    expect(mol).toContain("$$$$");
  });

  it("reads a caption after M  END", () => {
    const sdf = `
     RDKit          3D

  2  1  0  0  0  0  0  0  0  0999 V2000
    0.5705    0.0000    0.0000 O   0  0  0  0  0  0
   -0.5705    0.0000    0.0000 O   0  0  0  0  0  0
  1  2  2  0
M  END
O2`;
    const result = parseMolecule3DFence(sdf);
    expect(result!.caption).toBe("O2");
  });

  it("declines a V3000 block the native viewer cannot draw", () => {
    const sdf = `Aspirin
     RDKit          3D

  0  0  0  0  0  0  0  0  0  0999 V3000
M  V30 BEGIN CTAB
M  V30 COUNTS 9 9
M  V30 END CTAB
M  END`;
    expect(parseMolecule3DFence(sdf)).toBeNull();
  });
});

describe("parseMolGeometry", () => {
  it("reads O2 atoms and the double bond", () => {
    const sdf = `
     RDKit          3D

  2  1  0  0  0  0  0  0  0  0999 V2000
    0.5705    0.0000    0.0000 O   0  0  0  0  0  0
   -0.5705    0.0000    0.0000 O   0  0  0  0  0  0
  1  2  2  0
M  END
$$$$`;
    const geom = parseMolGeometry(sdf);
    expect(geom).not.toBeNull();
    expect(geom!.atoms).toHaveLength(2);
    expect(geom!.atoms.map((a) => a.el)).toEqual(["O", "O"]);
    expect(geom!.bonds).toEqual([{ a: 0, b: 1, order: 2 }]);
  });

  it("reads ethanol from parseMolecule3DFence output", () => {
    const parsed = parseMolecule3DFence(VALID_SDF);
    const geom = parseMolGeometry(parsed!.sdf);
    expect(geom!.atoms.map((a) => a.el)).toEqual(["C", "C", "O"]);
    expect(geom!.bonds).toHaveLength(2);
  });
});

describe("a molecule with more than 99 atoms or bonds", () => {
  // MOL counts and bond lines are fixed-width (%3d): "173172" is 173 atoms and 172 bonds,
  // " 100101" is a bond from atom 100 to atom 101. Splitting on whitespace read 173172 atoms.
  it("finds the counts line of an RDKit block whose fields run together", () => {
    const fence = parseMolecule3DFence(TRISTEARIN_SDF);
    expect(fence).not.toBeNull();
    expect(fence!.sdf).toContain("173172");
  });

  it("reads every atom and bond, including atoms numbered above 99", () => {
    const fence = parseMolecule3DFence(TRISTEARIN_SDF);
    const geometry = parseMolGeometry(fence!.sdf);
    expect(geometry).not.toBeNull();
    expect(geometry!.atoms).toHaveLength(173);
    expect(geometry!.bonds).toHaveLength(172);
    expect(geometry!.bonds.some((bond) => bond.a >= 99 || bond.b >= 99)).toBe(true);
    expect(geometry!.bonds.every((bond) => bond.a < 173 && bond.b < 173)).toBe(true);
  });

  it("still reads a hand-typed block whose fields are separated by single spaces", () => {
    const sdf = `x
 RDKit 3D

 3 2 0 0 0 0 0 0 0 0999 V2000
    0.0000    0.0000    0.0000 C   0
    1.5000    0.0000    0.0000 C   0
    2.5000    1.0000    0.0000 O   0
 1 2 1
 2 3 1
M  END`;
    const geometry = parseMolGeometry(`${sdf}\n$$$$`);
    expect(geometry?.atoms).toHaveLength(3);
    expect(geometry?.bonds).toEqual([
      { a: 0, b: 1, order: 1 },
      { a: 1, b: 2, order: 1 },
    ]);
  });
});
