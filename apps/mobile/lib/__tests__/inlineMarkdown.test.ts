import { parseInlineMarkdown } from "@/lib/markdown/inlineMarkdown";

describe("parseInlineMarkdown", () => {
  it("returns empty for empty input", () => {
    expect(parseInlineMarkdown("")).toEqual([]);
  });

  it("leaves plain text untouched", () => {
    expect(parseInlineMarkdown("just words")).toEqual([
      { type: "text", value: "just words" },
    ]);
  });

  it("parses bold", () => {
    expect(parseInlineMarkdown("a **bold** b")).toEqual([
      { type: "text", value: "a " },
      { type: "bold", value: "bold" },
      { type: "text", value: " b" },
    ]);
  });

  it("parses italic (asterisk only)", () => {
    expect(parseInlineMarkdown("an *italic* word")).toEqual([
      { type: "text", value: "an " },
      { type: "italic", value: "italic" },
      { type: "text", value: " word" },
    ]);
  });

  it("parses inline code", () => {
    expect(parseInlineMarkdown("run `npm test` now")).toEqual([
      { type: "text", value: "run " },
      { type: "code", value: "npm test" },
      { type: "text", value: " now" },
    ]);
  });

  it("does not interpret emphasis inside inline code", () => {
    expect(parseInlineMarkdown("see `**not bold**`")).toEqual([
      { type: "text", value: "see " },
      { type: "code", value: "**not bold**" },
    ]);
  });

  it("does not treat snake_case underscores as italic", () => {
    expect(parseInlineMarkdown("use my_var_name here")).toEqual([
      { type: "text", value: "use my_var_name here" },
    ]);
  });

  it("handles mixed emphasis in one string", () => {
    const tokens = parseInlineMarkdown("**bold** and *italic* and `code`");
    expect(tokens.map((t) => t.type)).toEqual([
      "bold",
      "text",
      "italic",
      "text",
      "code",
    ]);
  });

  it("leaves a stray single asterisk as text", () => {
    expect(parseInlineMarkdown("5 * 3")).toEqual([{ type: "text", value: "5 * 3" }]);
  });
});
