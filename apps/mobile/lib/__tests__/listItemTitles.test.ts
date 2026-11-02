import { breakListItemTitles } from "@/lib/markdown/listItemTitles";
import { markdownItInstance } from "@/lib/markdown/parser";
import { preprocessMarkdown } from "@/lib/markdown/preprocess";

describe("breakListItemTitles", () => {
  it("puts a numbered item's title on its own line", () => {
    const source = [
      "1. **Read widely** – Consume diverse books and articles outside your comfort zone.",
      "10. **Embrace failure** — View mistakes as data points for improvement.",
    ].join("\n");

    expect(breakListItemTitles(source)).toBe(
      [
        "1. **Read widely**\\",
        "   Consume diverse books and articles outside your comfort zone.",
        "10. **Embrace failure**\\",
        "    View mistakes as data points for improvement.",
      ].join("\n"),
    );
  });

  it("splits bullets and nested items, keeping their indent", () => {
    expect(
      breakListItemTitles(
        "  - **Sleep** - Aim for seven to nine hours nightly.",
      ),
    ).toBe("  - **Sleep**\\\n    Aim for seven to nine hours nightly.");
  });

  it.each([
    ["a short value", "- **Price** – $5 a month"],
    [
      "a timeline year",
      "1. **1941** — Germany invades the USSR; Japan attacks Pearl Harbor.",
    ],
    ["a colon label", "- **Formula:** water is two hydrogens and one oxygen"],
    ["no dash", "1. **Read widely** and often, every single day of the week."],
    [
      "a plain item",
      "- Read widely – books and articles of every kind you find.",
    ],
    [
      "a lesson step",
      "**1. Subtract 4 from both sides** — Subtraction property of equality",
    ],
  ])("leaves %s alone", (_name, line) => {
    expect(breakListItemTitles(line)).toBe(line);
  });

  it("leaves code fences alone", () => {
    const source = [
      "```md",
      "1. **Read widely** – Consume diverse books and articles.",
      "```",
    ].join("\n");
    expect(breakListItemTitles(source)).toBe(source);
  });

  it("keeps the title and description in one list paragraph, split by a hard break", () => {
    const prepared = preprocessMarkdown(
      "1. **Read widely** – Consume diverse books and articles outside your comfort zone.\n" +
        "2. **Prioritize sleep** – Aim for 7–9 hours nightly to consolidate memories.",
    );
    const tokens = markdownItInstance.parse(prepared, {});
    expect(tokens.filter((t) => t.type === "list_item_open")).toHaveLength(2);
    const inline = tokens.find((t) => t.type === "inline");
    const kids = (inline?.children ?? []).filter(
      (c) => c.type !== "text" || c.content,
    );
    expect(kids.map((c) => c.type)).toEqual([
      "strong_open",
      "text",
      "strong_close",
      "hardbreak",
      "text",
    ]);
    expect(kids[4].content).toBe(
      "Consume diverse books and articles outside your comfort zone.",
    );
  });
});
