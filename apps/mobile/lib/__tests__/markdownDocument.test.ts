import { markdownToDocumentText } from "@/lib/markdown/document";

const label = (block: string) => `[${block}]`;

describe("markdownToDocumentText", () => {
  it("keeps prose, code and tables as written", () => {
    const md = "Use `proposal_id` here.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```python\nprint(1)\n```";
    const out = markdownToDocumentText(md, label);
    expect(out).toContain("Use `proposal_id` here.");
    expect(out).toContain("| 1 | 2 |");
    expect(out).toContain("```python\nprint(1)\n```");
  });

  it("drops control cards and sources", () => {
    const md = [
      "Saved.",
      "```reminder_proposal",
      '{"proposal_id":"p1","due_at":"2026-10-23T09:00:00Z"}',
      "```",
      "```sources",
      '[{"url":"https://example.com"}]',
      "```",
    ].join("\n");
    expect(markdownToDocumentText(md, label)).toBe("Saved.");
  });

  it("shows a verified answer as maths, and a chemistry or sentence answer as text", () => {
    expect(markdownToDocumentText("```answer\nverified: true\nx = 2\n```", label)).toBe(
      "```math\nx = 2\n```",
    );
    expect(
      markdownToDocumentText("```answer\nnotation: chemistry\nH₂O\n```", label),
    ).toBe("H₂O");
    expect(
      markdownToDocumentText("```answer\nThe ball lands after $t = 2$ s.\n```", label),
    ).toBe("The ball lands after $t = 2$ s.");
  });

  it("names each card a reader cannot open outside the app", () => {
    const cases: [string, string][] = [
      ["chart", '{"mark":"bar"}'],
      ["graph", '{"curves":[]}'],
      ["mermaid", "flowchart TD\n  A-->B"],
      ["simulation", '{"type":"free_body"}'],
      ["smiles", "CCO"],
      ["calculator", '{"v":1}'],
    ];
    const outs = cases.map(([lang, body]) =>
      markdownToDocumentText(`\`\`\`${lang}\n${body}\n\`\`\``, label),
    );
    expect(outs).toEqual([
      "[chart]",
      "[graph]",
      "[diagram]",
      "[diagram]",
      "[molecule]",
      "[calculator]",
    ]);
    for (const out of outs) expect(out).not.toContain("{");
  });

  it("keeps a maths fence as maths and a drafted email as its text", () => {
    expect(markdownToDocumentText("```math\n\\frac{1}{2}\n```", label)).toBe(
      "```math\n\\frac{1}{2}\n```",
    );
    expect(markdownToDocumentText("```email\nHi Sam,\nThanks.\n```", label)).toBe(
      "Hi Sam,\nThanks.",
    );
  });

  it("shows a clarifying card as its questions, not its JSON", () => {
    const card =
      '{"questions":[{"id":"region","label":"Region","question":"Which region?",' +
      '"options":["🌍 Anywhere","🇪🇺 Europe"],"values":["Anywhere","Europe"]}],' +
      '"request":"Recommend a country.","submit":"Find it"}';
    const out = markdownToDocumentText(`Which do you mean?\n\n\`\`\`clarify\n${card}\n\`\`\``, label);
    expect(out).toBe("Which do you mean?\n\nWhich region? (Anywhere / Europe)");
    expect(out).not.toContain("{");
  });

  it("keeps a clarifying card written as plain text, as the card shows it", () => {
    expect(markdownToDocumentText("Intro\n\n```clarify\nWhich region do you mean?\n```", label)).toBe(
      "Intro\n\nWhich region do you mean?",
    );
  });

  it("keeps each of a card's lines on its own line: plain in Share, a hard break apart in print", () => {
    const card =
      '{"questions":[{"id":"a","label":"A","question":"Which region?","options":["Asia","Europe"],' +
      '"values":["Asia","Europe"]},{"id":"b","label":"B","question":"Budget?","options":["Low","High"],' +
      '"values":["Low","High"]}]}';
    const md = `\`\`\`clarify\n${card}\n\`\`\``;
    expect(markdownToDocumentText(md, label)).toBe("Which region? (Asia / Europe)\nBudget? (Low / High)");
    expect(markdownToDocumentText(md, label, "print")).toBe(
      "Which region? (Asia / Europe)  \nBudget? (Low / High)",
    );
  });

  it("gives code holding backticks a longer fence", () => {
    const out = markdownToDocumentText("````md\n```js\nx\n```\n````", label);
    expect(out.startsWith("````md\n")).toBe(true);
    expect(out.endsWith("\n````")).toBe(true);
  });
});
