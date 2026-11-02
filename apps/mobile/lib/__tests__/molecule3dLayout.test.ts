import {
  atomColor,
  atomLabelColor,
  bondStrokeWidth,
  layoutMolecule,
  showsAtomLabel,
  type MoleculeStyle,
} from "@/lib/chemistry/molecule3dLayout";
import type { MolGeometry } from "@/lib/chemistry/molecule3dFence";

const W = 320;
const H = 280;

/** A long thin molecule: the case where re-fitting every frame makes the picture breathe. */
const CHAIN: MolGeometry = {
  atoms: [
    { x: -6, y: 0, z: 0, el: "C" },
    { x: -2, y: 0.5, z: 1, el: "C" },
    { x: 2, y: -0.5, z: -1, el: "C" },
    { x: 6, y: 0, z: 0, el: "O" },
  ],
  bonds: [
    { a: 0, b: 1, order: 1 },
    { a: 1, b: 2, order: 2 },
    { a: 2, b: 3, order: 3 },
  ],
};

const ANGLES = [0, 0.4, 0.9, Math.PI / 2, 2.2, Math.PI, 4.1, 5.5];
const PITCHES = [-1.2, -0.5, 0, 0.35, 1.2];

describe("layoutMolecule camera", () => {
  it("keeps every atom inside the view at any angle", () => {
    for (const style of ["ball-stick", "spacefill", "wireframe"] as MoleculeStyle[]) {
      for (const yaw of ANGLES) {
        for (const pitch of PITCHES) {
          const { atoms } = layoutMolecule(CHAIN, yaw, pitch, W, H, style);
          for (const atom of atoms) {
            expect(atom.x - atom.radius).toBeGreaterThanOrEqual(-0.001);
            expect(atom.x + atom.radius).toBeLessThanOrEqual(W + 0.001);
            expect(atom.y - atom.radius).toBeGreaterThanOrEqual(-0.001);
            expect(atom.y + atom.radius).toBeLessThanOrEqual(H + 0.001);
          }
        }
      }
    }
  });

  it("does not change scale as the molecule turns", () => {
    // Atom size follows the one scale; a camera that re-fits every frame changes it.
    const sizes = ANGLES.map((yaw) => layoutMolecule(CHAIN, yaw, 0.35, W, H, "spacefill").atoms[0]!.radius);
    for (const size of sizes) expect(size).toBeCloseTo(sizes[0]!, 9);
  });

  it("turns the molecule about its middle, so it stays centred", () => {
    const { atoms } = layoutMolecule(CHAIN, 1.1, 0.2, W, H, "ball-stick");
    const x = atoms.map((atom) => atom.x);
    expect((Math.min(...x) + Math.max(...x)) / 2).toBeGreaterThan(W / 2 - 40);
    expect((Math.min(...x) + Math.max(...x)) / 2).toBeLessThan(W / 2 + 40);
  });

  it("does not fail on a single atom or on atoms stacked at one point", () => {
    const one: MolGeometry = { atoms: [{ x: 3, y: 3, z: 3, el: "He" }], bonds: [] };
    const layout = layoutMolecule(one, 0.3, 0.3, W, H, "ball-stick");
    expect(Number.isFinite(layout.atoms[0]!.x)).toBe(true);
    expect(Number.isFinite(layout.atoms[0]!.radius)).toBe(true);
  });
});

describe("layoutMolecule drawing", () => {
  it("gives a double bond two lines and a triple bond three", () => {
    const { bonds } = layoutMolecule(CHAIN, 0.3, 0.3, W, H, "ball-stick");
    expect(bonds).toHaveLength(1 + 2 + 3);
    expect(new Set(bonds.map((bond) => bond.key)).size).toBe(bonds.length);
  });

  it("draws no bonds in the space-filling style", () => {
    const layout = layoutMolecule(CHAIN, 0.3, 0.3, W, H, "spacefill");
    expect(layout.bonds).toEqual([]);
    expect(layout.drawOrder.every((item) => item.kind === "atom")).toBe(true);
  });

  it("draws every atom and bond line exactly once", () => {
    const layout = layoutMolecule(CHAIN, 0.3, 0.3, W, H, "ball-stick");
    expect(layout.drawOrder.filter((item) => item.kind === "atom")).toHaveLength(4);
    expect(layout.drawOrder.filter((item) => item.kind === "bond")).toHaveLength(layout.bonds.length);
  });

  it("puts a bond behind the nearer atom and in front of the farther one", () => {
    const pair: MolGeometry = {
      atoms: [
        { x: 0, y: 0, z: -2, el: "C" },
        { x: 0, y: 0, z: 2, el: "O" },
      ],
      bonds: [{ a: 0, b: 1, order: 1 }],
    };
    // yaw = pitch = 0 leaves z as it is: atom 1 is nearer the viewer.
    const { drawOrder } = layoutMolecule(pair, 0, 0, W, H, "ball-stick");
    expect(drawOrder).toEqual([
      { kind: "atom", index: 0 },
      { kind: "bond", index: 0 },
      { kind: "atom", index: 1 },
    ]);
  });

  it("draws a flat molecule's bonds before its atoms, so atoms cover the bond ends", () => {
    const flat: MolGeometry = {
      atoms: [
        { x: -1, y: 0, z: 0, el: "C" },
        { x: 1, y: 0, z: 0, el: "C" },
      ],
      bonds: [{ a: 0, b: 1, order: 1 }],
    };
    const { drawOrder } = layoutMolecule(flat, 0, 0, W, H, "ball-stick");
    expect(drawOrder[0]).toEqual({ kind: "bond", index: 0 });
  });

  it("skips a bond that names an atom that is not there", () => {
    const broken: MolGeometry = {
      atoms: [{ x: 0, y: 0, z: 0, el: "C" }],
      bonds: [{ a: 0, b: 5, order: 1 }],
    };
    expect(layoutMolecule(broken, 0, 0, W, H, "ball-stick").bonds).toEqual([]);
  });

  it("draws wireframe bonds thinner than ball-and-stick", () => {
    expect(bondStrokeWidth("wireframe")).toBeLessThan(bondStrokeWidth("ball-stick"));
  });

  it("refuses a stage narrower than the 72px padding", () => {
    const narrow = layoutMolecule(CHAIN, 0, 0, 71, H, "ball-stick");
    expect(narrow.atoms).toEqual([]);
    expect(narrow.bonds).toEqual([]);
    expect(narrow.drawOrder).toEqual([]);
    const edge = layoutMolecule(CHAIN, 0, 0, 72, H, "wireframe");
    expect(edge.atoms).toEqual([]);
  });
});

describe("how an element looks", () => {
  it("knows the metals and metalloids that inorganic answers draw", () => {
    const fallback = atomColor("Xx");
    for (const element of ["Li", "B", "Na", "Mg", "Al", "Si", "K", "Ca", "Fe", "Cu", "Zn", "Se"]) {
      expect(atomColor(element)).not.toBe(fallback);
    }
  });

  it("names atoms in ball-and-stick and wire, and leaves the sphere unlabeled", () => {
    expect(showsAtomLabel("ball-stick")).toBe(true);
    expect(showsAtomLabel("wireframe")).toBe(true);
    expect(showsAtomLabel("spacefill")).toBe(false);
  });

  it("uses a dark label on a light atom and a white one on a dark atom", () => {
    expect(atomLabelColor("H")).toBe("#1a1a1a");
    expect(atomLabelColor("Cl")).toBe("#1a1a1a");
    expect(atomLabelColor("C")).toBe("#fff");
    expect(atomLabelColor("O")).toBe("#fff");
  });
});
