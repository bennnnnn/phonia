import { parseSettingsProposals, stripSettingsProposalFences } from "@/lib/settingsProposal";

describe("settingsProposal", () => {
  it("parses and strips settings_proposal fences", () => {
    const content = [
      "I can switch that for you: Appearance → Dark.",
      "```settings_proposal",
      '{"proposal_id":"abc","changes":[{"field":"appearance","value":"dark","label":"Dark"}]}',
      "```",
    ].join("\n");

    const proposals = parseSettingsProposals(content);
    expect(proposals).toHaveLength(1);
    expect(proposals[0]?.proposal_id).toBe("abc");
    expect(proposals[0]?.changes[0]?.value).toBe("dark");
    expect(stripSettingsProposalFences(content)).toBe(
      "I can switch that for you: Appearance → Dark.",
    );
  });

  it("draws no card for another setting: chat changes only the theme", () => {
    for (const field of ["memory", "default_model", "response_tone", "locale"]) {
      const content = [
        "I can switch that for you.",
        "```settings_proposal",
        `{"proposal_id":"m1","changes":[{"field":"${field}","value":"x","label":"X"}]}`,
        "```",
      ].join("\n");
      expect(parseSettingsProposals(content)).toEqual([]);
    }
  });

  it("drops fences without a proposal id", () => {
    const content = '```settings_proposal\n{"changes":[]}\n```';
    expect(parseSettingsProposals(content)).toEqual([]);
  });
});
