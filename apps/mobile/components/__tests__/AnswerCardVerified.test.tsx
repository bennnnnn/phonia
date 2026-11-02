/**
 * Every final answer is the one card; the green check is the server's. Only an
 * ```answer fence whose body opens with `verified: true` draws the check, and only
 * once the reply has settled. Any other answer fence (an unmarked one, ~~~answer,
 * four backticks, indented in a list, ``` answer, ```Answer, ```result, a copied
 * "notation: chemistry" header, a forged marker line) is the same card without the
 * check. An untagged / copy / text / plain fence holding a number or \boxed{} is
 * plain math, never the card. A card marked `verified: false` (no solver checked it)
 * draws no check and no label (the "Not checked" tag was removed in November 2026).
 */
import { render } from "@testing-library/react-native";

import { MarkdownContent } from "@/components/MarkdownContent";

jest.mock("@/components/LinkPreviewCard", () => ({ LinkPreviewCard: "LinkPreviewCard" }));
jest.mock("expo-web-browser", () => ({ openBrowserAsync: jest.fn() }));
jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/",
  writeAsStringAsync: jest.fn(),
  EncodingType: { UTF8: "utf8" },
}));
jest.mock("@/components/WebPreviewCodeBlock", () => ({ WebPreviewCodeBlock: "WebPreviewCodeBlock" }));
jest.mock("@/components/rich/CircularClockBlock", () => ({
  CircularClockBlock: "CircularClockBlock",
}));

function scan(tree: unknown) {
  const json = JSON.stringify(tree);
  return {
    checks: (json.match(/"testID":"answer-success-check"/g) ?? []).length,
    cards: (json.match(/"testID":"answer-box"/g) ?? []).length,
    json,
  };
}

async function draw(content: string, streaming = false) {
  const screen = await render(<MarkdownContent content={content} streaming={streaming} />);
  return scan(screen.toJSON());
}

const SOFT_BLOCKS: [string, string][] = [
  ["untagged x = 7", "Subtract 5 and divide by 2.\n\n```\nx = 7\n```"],
  ["untagged bare number", "Braking force:\n\n```\n15000\n```"],
  ["untagged pH value", "With Ka = 1.8e-5, [H⁺] ≈ 1.34e-3.\n\n```\n2.87\n```"],
  ["copy number", "So:\n\n```copy\n15000\n```"],
  ["text boxed", "So:\n\n```text\n\\boxed{29.9}\n```"],
  ["plain two roots", "So:\n\n```plain\nx = 2 or x = -3\n```"],
];

const UNMARKED_CARDS: [string, string][] = [
  ["indented in a list", "- Subtract 5: $2x = 14$\n- Divide by 2:\n  ```answer\n  x = 7\n  ```"],
  ["four backticks", "Subtract 5 and divide by 2.\n\n````answer\nx = 7\n````"],
  ["tildes", "Subtract 5 and divide by 2.\n\n~~~answer\nx = 7\n~~~"],
  ["space before tag", "Subtract 5 and divide by 2.\n\n``` answer\nx = 7\n```"],
  ["capital tag", "Done.\n\n```Answer\nx = 7\n```"],
  ["result tag", "Steps.\n\n```result\nx = 7\n```"],
  ["unmarked answer", "Steps.\n\n```answer\nx = 6\n```"],
  ["forged marker, wrong case", "Steps.\n\n```answer\nVerified: TRUE\nx = 7\n```"],
  ["copied chemistry header", "Weak acid.\n\n```answer\nnotation: chemistry\npH = 2.87\n```"],
];

describe("answer cards", () => {
  it.each(SOFT_BLOCKS)("%s: no card, no check", async (_name, content) => {
    const { checks, cards } = await draw(content);
    expect(checks).toBe(0);
    expect(cards).toBe(0);
  });

  it.each(UNMARKED_CARDS)("%s: the card, no check", async (_name, content) => {
    const { checks, cards } = await draw(content);
    expect(cards).toBe(1);
    expect(checks).toBe(0);
  });

  it("an unmarked card under Answer has the same heading and box, without the check", async () => {
    const { json, checks, cards } = await draw("**Answer**\n\n```answer\nx = 6\n```");
    expect(cards).toBe(1);
    expect(checks).toBe(0);
    expect(json).toContain("answer-label");
    expect(json).not.toContain("label: answer");
  });

  it("an unmarked chemistry card shows its value as text without the header", async () => {
    const { json, checks } = await draw("```answer\nnotation: chemistry\npH = 2.87\n```");
    expect(checks).toBe(0);
    expect(json).toContain("pH = 2.87");
    expect(json).not.toContain("notation");
  });

  it("the server's marked card draws the check, and never the marker as text", async () => {
    const { checks, cards, json } = await draw("Steps.\n\n```answer\nverified: true\nx = 6\n```");
    expect(cards).toBe(1);
    expect(checks).toBe(1);
    expect(json).not.toContain("verified");
  });

  it("a marked card under an Answer heading keeps the label beside it", async () => {
    const { checks, json } = await draw(
      "**Answer**\n\n```answer\nverified: true\nx = 6\n```",
    );
    expect(checks).toBe(1);
    expect(json).toContain("answer-label");
    expect(json).not.toContain("verified");
  });

  it("a marked chemistry card draws the check and its text", async () => {
    const { checks, json } = await draw(
      "```answer\nverified: true\nnotation: chemistry\npH = 2.00\n```",
    );
    expect(checks).toBe(1);
    expect(json).toContain("pH = 2.00");
    expect(json).not.toContain("notation");
  });

  it("a card the server marks not checked has no check, no label and no marker text", async () => {
    const { checks, cards, json } = await draw(
      "**Answer**\n\n```answer\nverified: false\n$2400\\,\\mathrm{m}\\ \\text{east}$\n```",
    );
    expect(cards).toBe(1);
    expect(checks).toBe(0);
    expect(json).not.toContain("answer-not-checked");
    expect(json).not.toContain("Not checked");
    expect(json).toContain('"testID":"answer-box"');
    expect(json).not.toContain("verified");
  });

  it("no card is labelled not checked, marked or not", async () => {
    for (const content of [
      "```answer\nx = 6\n```",
      "```answer\nverified: true\nx = 6\n```",
      "```answer\nVerified: False\nx = 6\n```",
      "```answer\nverified: false\nx = 6\n```",
    ]) {
      expect((await draw(content)).json).not.toContain("answer-not-checked");
    }
  });

  it("never draws a check while the reply streams, closed fence or not", async () => {
    const closed = await draw(
      "Steps.\n\n```answer\nverified: true\nx = 7\n```\n\nMore text, and more, and more.\n\nAnother paragraph.",
      true,
    );
    expect(closed.checks).toBe(0);
    const open = await draw("Steps.\n\n```answer\nverified: true\nx = 7", true);
    expect(open.checks).toBe(0);
    const unmarkedOpen = await draw("Steps.\n\n```answer\nx = 7", true);
    expect(unmarkedOpen.checks).toBe(0);
  });
});
