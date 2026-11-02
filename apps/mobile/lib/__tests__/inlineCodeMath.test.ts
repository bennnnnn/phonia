import { preprocessMarkdown, splitInlineMath } from "@/lib/markdown/preprocess";
import { preprocessMarkdownForStream } from "@/lib/markdown/preprocessStream";
import { markdownItInstance } from "@/lib/markdown/parser";
import { restoreMathEscapes } from "@/lib/math/text";

/**
 * What the reader sees once markdown-it and the renderer's `$...$` split
 * have run: code spans, maths spans and the flattened visible text.
 */
function seen(markdown: string) {
  const prepared = preprocessMarkdown(markdown);
  const code: string[] = [];
  const math: string[] = [];
  let text = "";
  for (const block of markdownItInstance.parse(prepared, {})) {
    for (const token of block.children ?? []) {
      if (token.type === "code_inline") {
        code.push(token.content);
        text += token.content;
      } else if (token.type === "text") {
        for (const part of splitInlineMath(token.content)) {
          if (part.type === "math") math.push(restoreMathEscapes(part.value));
          text += part.value;
        }
      } else if (token.type === "softbreak" || token.type === "hardbreak") {
        text += " ";
      }
    }
    if (block.type === "paragraph_close" || block.type === "heading_close") text += "\n";
  }
  return { prepared, code, math, text: text.trim() };
}

// Recall's reply to "Explain this code line by line, then show the value of
// total after each iteration" rendered as
// "n is $2 $. total += n means total$ $. total + = total + n. So, total` becomes$ 0 + 2 = 2$."
const ITERATION =
  "- **Iteration 1**: `n` is $2$. `total += n` means `total = total + n`. So, `total` becomes $0 + 2 = 2$.";

describe("inline code and inline maths in one line", () => {
  it("keeps the reported iteration line as code spans and two maths spans", () => {
    const view = seen(ITERATION);
    expect(view.code).toEqual(["n", "total += n", "total = total + n", "total"]);
    expect(view.math).toEqual(["2", "0 + 2 = 2"]);
    expect(view.text).not.toMatch(/[$`]/);
    expect(view.text).toBe(
      "Iteration 1: n is 2. total += n means total = total + n. So, total becomes 0 + 2 = 2.",
    );
  });

  it("streams the iteration line the same way it settles", () => {
    const source = `${ITERATION}\n`;
    expect(preprocessMarkdownForStream(source, null).prepared).toBe(preprocessMarkdown(source));
  });

  it.each([
    {
      name: "a dollar inside backticks",
      source: "`total` is `$5` and `x$` then $y = 2$.",
      code: ["total", "$5", "x$"],
      math: ["y = 2"],
      text: "total is $5 and x$ then y = 2.",
    },
    {
      name: "a dollar right after a backtick",
      source: "So `total`$ becomes 2.",
      code: ["total"],
      math: [],
    },
    {
      name: "a price on each side of a code span",
      source: "Costs $5 and `total` is $3.",
      code: ["total"],
      math: [],
      text: "Costs $5 and total is $3.",
    },
    {
      name: "backticks inside a dollar pair",
      source: "The value $`total`$ is 2.",
      code: ["total"],
      math: [],
      text: "The value total is 2.",
    },
    {
      name: "a code span opening a dollar pair",
      source: "If $`total` + 2$ is even, stop.",
      code: ["total"],
      math: [],
      text: "If total + 2 is even, stop.",
    },
    {
      name: "spaces inside the dollars",
      source: "`n` is $2 $, so `total` becomes $ 0 + 2 = 2$.",
      code: ["n", "total"],
      math: ["2", "0 + 2 = 2"],
      text: "n is 2, so total becomes 0 + 2 = 2.",
    },
    {
      name: "an odd number of dollars",
      source: "`n` is $2$, so `total` is $2 and `x` is $3$.",
      code: ["n", "total", "x"],
      math: ["2", "3"],
      text: "n is 2, so total is $2 and x is 3.",
    },
    {
      name: "prices around code",
      source: "Prices: $5 and $10, and `total` is $15.",
      code: ["total"],
      math: [],
      text: "Prices: $5 and $10, and total is $15.",
    },
  ])("renders $name without stray delimiters", ({ source, code, math, text }) => {
    const view = seen(source);
    expect(view.code).toEqual(code);
    expect(view.math).toEqual(math);
    expect(view.text).not.toContain("`");
    if (text) expect(view.text).toBe(text);
  });

  it("keeps a lone dollar after code as literal text", () => {
    const view = seen("So `total`$ becomes 2.");
    expect(view.text.replace(/\s+/g, " ")).toMatch(/^So total ?\$ becomes 2\.$/);
  });
});

describe("inline code at the end of a line", () => {
  it("keeps the closing backtick of a bold label's code", () => {
    const view = seen(
      "**Line 1:** `total = 0`\nCreates a variable `total` and sets it to `0`.",
    );
    expect(view.code).toEqual(["total = 0", "total", "0"]);
    expect(view.math).toEqual([]);
    expect(view.text).not.toContain("`");
  });

  it("keeps the closing backtick of a list item's code", () => {
    const view = seen("1. `IndexError` when you read `numbers[2]`\n2. **Final output:** `12`");
    expect(view.code).toEqual(["IndexError", "numbers[2]", "12"]);
    expect(view.text).not.toContain("`");
  });

  it("still drops an unpaired trailing backtick", () => {
    const view = seen("✅ Check sum: 2 + 8 + 32 = 42`");
    expect(view.text).not.toContain("`");
  });

  it("puts the explanation under a bold label's code on its own row", () => {
    const prepared = preprocessMarkdown(
      "**Line 1:** `total = 0`\nCreates a variable `total`.",
    );
    expect(prepared).toBe("**Line 1:** `total = 0`\n\nCreates a variable `total`.");
  });
});

describe("code spans are never typeset as maths", () => {
  it.each([
    "0",
    "12",
    "x = 5",
    "i += 1",
    "x = x + 1",
    "my_list",
    "n_items + 1",
    "range(n_items)",
    "len(my_list) - 1",
    String.raw`print("a\nb")`,
    "x ** 2",
    "total = total + n",
    "$5",
    "x$",
  ])("keeps `%s` as code", (snippet) => {
    const view = seen(`Use \`${snippet}\` here.`);
    expect(view.code).toEqual([snippet]);
    expect(view.math).toEqual([]);
  });

  it.each([
    ["`$x^2$`", "x^2"],
    ["`2 + 8 + 32 = 42`", "2 + 8 + 32 = 42"],
    ["`x^2 + 1`", "x^2 + 1"],
    ["`" + String.raw`\frac{1}{2}` + "`", String.raw`\frac{1}{2}`],
  ])("still reads %s as maths", (snippet, latex) => {
    const view = seen(`Check: ${snippet}`);
    expect(view.code).toEqual([]);
    expect(view.math).toEqual([latex]);
  });
});
