import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { prepareAssistantMarkdown } from "./assistantMarkdown.ts";

function chemicalStructureCount(markdown: string): number {
  return markdown.split("Chemical structure").length - 1;
}

describe("prepareAssistantMarkdown molecule pair", () => {
  it("does not emit a second Chemical structure label for paired molecule3d", () => {
    const markdown =
      "```smiles\nCCO\n```\n\n```molecule3d\nEthanol\n     RDKit          3D\n\n  3  2  0  0  0  0  0  0  0  0999 V2000\nM  END\n```";
    const out = prepareAssistantMarkdown(markdown);
    assert.equal(chemicalStructureCount(out), 1);
    assert.equal(out.includes("V2000"), false);
    assert.equal(out.includes("```"), false);
  });

  it("keeps a Chemical structure label for standalone molecule3d", () => {
    const out = prepareAssistantMarkdown(
      "```molecule3d\nEthanol\n     RDKit          3D\n\n  3  2  0  0  0  0  0  0  0  0999 V2000\nM  END\n```",
    );
    assert.equal(chemicalStructureCount(out), 1);
  });

  it("skips a later molecule3d after smiles even when a heading sits between", () => {
    const markdown =
      "```smiles\nCCO\n```\n\n## 3D Structure\n\n```molecule3d\nEthanol\n     RDKit          3D\n\n  3  2  0  0  0  0  0  0  0  0999 V2000\nM  END\n```";
    const out = prepareAssistantMarkdown(markdown);
    assert.equal(chemicalStructureCount(out), 1);
    assert.equal(out.includes("V2000"), false);
  });
});

describe("prepareAssistantMarkdown answers", () => {
  it("shows a chemistry answer without the notation line", () => {
    const out = prepareAssistantMarkdown(
      "```answer\nnotation: chemistry\nM(H2O) = 18.015 g/mol\n```",
    );
    assert.equal(out.includes("notation:"), false);
    assert.equal(out.includes("```"), false);
    assert.match(out, /M\(H2O\) = 18\.015 g\/mol/);
  });

  it("keeps a math answer body", () => {
    const out = prepareAssistantMarkdown("```answer\nx = 2\n```");
    assert.match(out, /x = 2/);
    assert.equal(out.includes("notation:"), false);
  });

  it("never shows the server's verified marker as text", () => {
    const math = prepareAssistantMarkdown("```answer\nverified: true\nx = 2\n```");
    assert.equal(math.includes("verified"), false);
    assert.match(math, /x = 2/);
    const chemistry = prepareAssistantMarkdown(
      "```answer\nverified: true\nnotation: chemistry\npH = 2.00\n```",
    );
    assert.equal(chemistry.includes("verified"), false);
    assert.equal(chemistry.includes("notation:"), false);
    assert.match(chemistry, /pH = 2\.00/);
  });
});

describe("prepareAssistantMarkdown drafts and tables", () => {
  it("renders sms/social fences as sanitized cards not pre", () => {
    const out = prepareAssistantMarkdown(
      "```sms\nHey [Your Name], on my way.\n```",
    );
    assert.equal(out.includes("```"), false);
    assert.equal(out.includes("[Your Name]"), false);
    assert.match(out, /Text message/);
    assert.match(out, /on my way/);
  });

  it("splits a swallowed GFM table out of a python fence", () => {
    const markdown = [
      "```python",
      "print(1)",
      "",
      "| Lang | Use |",
      "| --- | --- |",
      "| Python | Data |",
      "```",
    ].join("\n");
    const out = prepareAssistantMarkdown(markdown);
    assert.match(out, /```python/);
    assert.match(out, /\| Lang \| Use \|/);
  });
});

describe("prepareAssistantMarkdown chemistry scenes", () => {
  const scene = (json: object) => "```chem_scene\n" + JSON.stringify(json) + "\n```";

  it("never shows a chem_scene as JSON", () => {
    const out = prepareAssistantMarkdown(
      scene({
        kind: "balance",
        title: "Atom tally",
        rows: [
          { element: "H", left: 4, right: 4 },
          { element: "O", left: 2, right: 2 },
        ],
        charge: { left: 0, right: 0 },
      }),
    );
    assert.equal(out.includes("{"), false);
    assert.equal(out.includes("```"), false);
    assert.equal(out.includes('"kind"'), false);
    assert.match(out, /Atom tally/);
    assert.match(out, /H: 4 → 4/);
    assert.match(out, /charge: 0 → 0/);
  });

  it("summarises each scene kind as text", () => {
    const vsepr = prepareAssistantMarkdown(
      scene({
        kind: "vsepr",
        title: "H₂O",
        central: "O",
        terminals: ["H", "H"],
        lone_pairs: 2,
        geometry: "bent",
        bond_angle: "104.5°",
        electron_geometry: "tetrahedral",
        ideal_angle: "109.5°",
      }),
    );
    assert.match(vsepr, /bent, 104\.5°, 2 lone pair/);
    const ice = prepareAssistantMarkdown(
      scene({
        kind: "equilibrium",
        title: "ICE table",
        rows: [{ species: "N₂O₄", initial: "1", change: "−x", equilibrium: "0.382 mol/L" }],
      }),
    );
    assert.match(ice, /N₂O₄: 1 −x → 0\.382 mol\/L/);
    const cell = prepareAssistantMarkdown(
      scene({ kind: "cell", title: "Galvanic cell", anode: "Zn", cathode: "Cu", potential: "1.1 V", electrons: "anode to cathode" }),
    );
    assert.match(cell, /anode Zn/);
    assert.match(cell, /1\.1 V/);
  });

  it("falls back to a label for an unreadable scene and never splits it as a table", () => {
    const out = prepareAssistantMarkdown("```chem_scene\nnot json | a | b\n| - | - |\n```");
    assert.equal(out.includes("not json"), false);
    assert.match(out, /Chemistry diagram/);
  });

  it("does not dump arithmetic or simulation specs", () => {
    const out = prepareAssistantMarkdown(
      '```simulation\n{"kind":"projectile","title":"Ball toss"}\n```\n\n```arithmetic\n{"rows":[]}\n```',
    );
    assert.equal(out.includes('"kind"'), false);
    assert.match(out, /Ball toss/);
  });
});

describe("prepareAssistantMarkdown unverified footer", () => {
  it("drops the unverified sentence from a stored reply", () => {
    const out = prepareAssistantMarkdown(
      "The bakery pickup is at 07:00 and the concert is at 19:00.\n\n*I couldn't automatically verify this result.*",
    );
    assert.equal(out.includes("automatically verify"), false);
    assert.match(out, /19:00/);
  });
});
