import {
  normalizeMoleculeFormulaToSmiles,
  parseChemistryFence,
  retagMoleculeMathToSmiles,
} from "@/lib/chemistry/fence";
import { isStructuredFenceLang } from "@/lib/richBlocks";

describe("parseChemistryFence", () => {
  it("parses a bare SMILES line", () => {
    expect(parseChemistryFence("O=O")).toEqual({ smiles: "O=O", caption: null });
  });

  it("parses caption + SMILES", () => {
    expect(parseChemistryFence("Oxygen (O2)\nO=O")).toEqual({
      smiles: "O=O",
      caption: "Oxygen (O2)",
    });
  });

  it("parses nitrogen triple bond", () => {
    expect(parseChemistryFence("Nitrogen (N2)\nN#N")).toEqual({
      smiles: "N#N",
      caption: "Nitrogen (N2)",
    });
  });

  it("maps diatomic formulas to SMILES", () => {
    expect(parseChemistryFence("H2")).toEqual({ smiles: "[H][H]", caption: null });
    expect(parseChemistryFence("O2")).toEqual({ smiles: "O=O", caption: null });
    expect(parseChemistryFence("N2")).toEqual({ smiles: "N#N", caption: null });
  });

  it("strips smiles: prefix", () => {
    expect(parseChemistryFence("smiles: CCO")).toEqual({
      smiles: "CCO",
      caption: null,
    });
  });

  it("returns null for empty content", () => {
    expect(parseChemistryFence("")).toBeNull();
    expect(parseChemistryFence("   \n  ")).toBeNull();
  });

  it("rejects oversized SMILES", () => {
    expect(parseChemistryFence("C".repeat(501))).toBeNull();
  });
});

describe("chemistry fence langs", () => {
  it("registers smiles and chemistry as structured langs", () => {
    expect(isStructuredFenceLang("smiles")).toBe(true);
    expect(isStructuredFenceLang("chemistry")).toBe(true);
  });
});

describe("normalizeMoleculeFormulaToSmiles", () => {
  it("accepts bonded structure formulas", () => {
    expect(normalizeMoleculeFormulaToSmiles("O=O")).toBe("O=O");
    expect(normalizeMoleculeFormulaToSmiles("N#N")).toBe("N#N");
    expect(normalizeMoleculeFormulaToSmiles("O=C=O")).toBe("O=C=O");
    expect(normalizeMoleculeFormulaToSmiles("N \\equiv N")).toBe("N#N");
    expect(normalizeMoleculeFormulaToSmiles("N ≡ N")).toBe("N#N");
    expect(normalizeMoleculeFormulaToSmiles("$O=O$")).toBe("O=O");
    expect(normalizeMoleculeFormulaToSmiles("H-H")).toBe("[H][H]");
  });

  it("rejects real math", () => {
    expect(normalizeMoleculeFormulaToSmiles("E=mc^2")).toBeNull();
    expect(normalizeMoleculeFormulaToSmiles("x=2")).toBeNull();
    expect(normalizeMoleculeFormulaToSmiles("\\frac{1}{2}")).toBeNull();
    expect(normalizeMoleculeFormulaToSmiles("CO")).toBeNull();
  });
});

describe("retagMoleculeMathToSmiles", () => {
  it("retags math fence O=O to smiles", () => {
    const out = retagMoleculeMathToSmiles("```math\nO=O\n```");
    expect(out).toContain("```smiles");
    expect(out).toContain("O=O");
    expect(out).not.toContain("```math");
  });

  it("retags latex triple-bond nitrogen", () => {
    const out = retagMoleculeMathToSmiles("```math\nN \\equiv N\n```");
    expect(out).toBe("```smiles\nN#N\n```");
  });

  it("retags whole-line inline math", () => {
    const out = retagMoleculeMathToSmiles("Here is oxygen:\n\n$O=O$\n\nDone.");
    expect(out).toContain("```smiles\nO=O\n```");
    expect(out).not.toContain("$O=O$");
  });

  it("leaves algebra math alone", () => {
    const input = "```math\nE=mc^2\n```";
    expect(retagMoleculeMathToSmiles(input)).toBe(input);
  });

  it("preserves caption + formula math fences", () => {
    const out = retagMoleculeMathToSmiles("```math\nOxygen (O2)\nO=O\n```");
    expect(out).toBe("```smiles\nOxygen (O2)\nO=O\n```");
  });
});

describe("retagMoleculeMathToSmiles leaves code alone", () => {
  it("does not retag a formula inside a code fence", () => {
    const python = "```python\nprint(\"\"\"\n$O=O$\n\"\"\")\n```";
    expect(retagMoleculeMathToSmiles(python)).toBe(python);
  });

  it("does not pair one fence's closer with the next fence's opener", () => {
    // A fence between two math fences must not be rewritten because the regex once
    // matched from the first closer to the second opener.
    const input = "```js\nconst a = 1;\n```\n\n```math\nO=O\n```\n\n```js\nconst b = 2;\n```";
    expect(retagMoleculeMathToSmiles(input)).toBe(
      "```js\nconst a = 1;\n```\n\n```smiles\nO=O\n```\n\n```js\nconst b = 2;\n```",
    );
  });

  it("does not retag a math fence quoted inside a longer fence", () => {
    const quoted = "````md\n```math\nO=O\n```\n````";
    expect(retagMoleculeMathToSmiles(quoted)).toBe(quoted);
  });

  it("does not retag a tilde-fenced formula", () => {
    const input = "~~~text\n$O=O$\n~~~";
    expect(retagMoleculeMathToSmiles(input)).toBe(input);
  });
});

describe("a physics formula is not a molecule", () => {
  // Found in the app: "How much work did the student do on the box?" rendered
  // a **Molecule** card reading "Could not render that structure" where the
  // formula should have been. The model wrote `$W = F d$`; the retagger
  // collapsed it to `W=Fd`, read W and "Fd" as elements, and shipped it to
  // RDKit — which failed, because a bare `W` was never valid SMILES in the
  // first place. That is the rule this now enforces: an unbracketed atom is
  // restricted to the organic subset.
  const PHYSICS = [
    "$W = F d$",
    "$W = Fd$",
    "$$W = F d$$",
    "$W = F \\times d$",
    "$P = F v$",
    "$F = m a$",
    "$T = m g$",
    // Letters that *are* in the organic subset, so only the spacing separates
    // these from a double bond.
    "$N = W$",
    "$F = P$",
    "$H = P$",
  ];

  it.each(PHYSICS)("leaves %s alone", (formula) => {
    expect(retagMoleculeMathToSmiles(formula)).toBe(formula);
  });

  it("rejects a bare element outside the organic subset", () => {
    // Tungsten must be written [W] in SMILES, so `W=W` was never renderable.
    expect(normalizeMoleculeFormulaToSmiles("W=W")).toBeNull();
    expect(normalizeMoleculeFormulaToSmiles("Fe=Fe")).toBeNull();
  });

  it("still accepts the diatomics written the way chemists write them", () => {
    expect(normalizeMoleculeFormulaToSmiles("O=O")).toBe("O=O");
    expect(normalizeMoleculeFormulaToSmiles("N#N")).toBe("N#N");
    expect(normalizeMoleculeFormulaToSmiles("H-H")).toBe("[H][H]");
    // The LaTeX triple bond needs its spaces, so spacing is only read off the
    // ASCII bonds.
    expect(normalizeMoleculeFormulaToSmiles("N \\equiv N")).toBe("N#N");
  });

  it("rejects a spaced ASCII bond, which is algebra", () => {
    expect(normalizeMoleculeFormulaToSmiles("O = O")).toBeNull();
  });
});
