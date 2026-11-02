import { normalizeBoldInlineMath, normalizeMarkdownTables, preprocessMarkdown, splitInlineMath, layoutCheckVerificationLines, breakAttachedMathFences, unwrapProseMathBackticks, mergeStrandedColons, separateStandaloneBoldLines, stripBoldListLabelContinuationColons, trimBoldDelimiterWhitespace, breakMidlineAtxHeadings } from "@/lib/markdown/preprocess";
import { isPipeTable } from "@/lib/markdown/preprocessTables";
import { repairBrokenMarkdownLinks } from "@/lib/places/placesList";
import { markdownItInstance } from "@/lib/markdown/parser";
import {
  PROTECTED_ESCAPE_MARKER,
  PROTECTED_MATH_STAR_MARKER,
  PROTECTED_MATH_UNDERSCORE_MARKER,
  parseSimpleLatex,
  segmentsToPlain,
} from "@/lib/math/text";

const RESTAURANT_LIST = `Here are some top-rated restaurants in San Francisco that might tickle your taste buds 🍽️:

### **Fine Dining**
1. **Benu** – 3-Michelin stars, modern Asian fusion ($$$)
2. **Atelier Crenn** – Poetic, French-inspired ($$$)

### **Casual & Trendy**
3. **State Bird Provisions** – Creative dim-sum ($$)
4. **Tartine Manufactory** – Bakery meets Californian fare ($$)`;

/** The block tokens at the top of a parsed document: one list stays one list. */
function topLevelTypes(markdown: string): string[] {
  return markdownItInstance
    .parse(markdown, {})
    .filter((token) => token.level === 0 && token.nesting === 1)
    .map((token) => token.type);
}

describe("preprocessMarkdown", () => {
  it("BUG FIX regression: preserves a leading minus in an explicit equation", () => {
    const prepared = preprocessMarkdown("$- x = -2$");
    const tokens = markdownItInstance.parse(prepared, {});

    expect(prepared).toBe("$- x = -2$");
    expect(tokens.some((token) => token.type === "bullet_list_open")).toBe(false);
    expect(tokens.some((token) => token.type === "inline" && token.content === "$- x = -2$")).toBe(true);
  });

  it("keeps an asterisk bullet outside its equation math span", () => {
    const prepared = preprocessMarkdown("$* x = 2$");
    const tokens = markdownItInstance.parse(prepared, {});

    expect(prepared).toBe("* $x = 2$");
    expect(tokens.some((token) => token.type === "bullet_list_open")).toBe(true);
  });

  it("preserves a chart fence after a math caption and leaves following prose outside it", () => {
    const source = [
      String.raw`Here’s the graph of \( y = x^{3} \):`,
      "",
      "```chart",
      "type: line",
      "labels: [-3, -2, -1, 0, 1, 2, 3]",
      "series:",
      "  - title: y = x³",
      "    data: [-27, -8, -1, 0, 1, 8, 27]",
      "```",
      "",
      "**Key points**:",
      "- It’s a cubic curve that passes through the origin (0, 0).",
    ].join("\n");
    const tokens = markdownItInstance.parse(preprocessMarkdown(source), {});
    const fences = tokens.filter((token) => token.type === "fence");
    expect(fences).toHaveLength(1);
    expect(fences[0].info).toBe("chart");
    expect(fences[0].content).toContain("data: [-27, -8, -1, 0, 1, 8, 27]");
    expect(fences[0].content).not.toContain("Key points");
    expect(tokens.some((token) => token.type === "inline" && token.content.includes("Key points"))).toBe(true);
  });

  it("does not split restaurant price tiers ($$$) into math fences", () => {
    const out = preprocessMarkdown(RESTAURANT_LIST);

    expect(out).not.toContain("```math");
    expect(out).not.toContain("```\n$$");
    expect(out).toContain("**Benu**");
    expect(out).toContain("($$$)");
    expect(out).toContain("**Atelier Crenn**");
    expect(out).toContain("### **Casual & Trendy**");
  });

  it("does not split ($$) price tiers across list items", () => {
    const input = `1. **Benu** – fusion ($$)
2. **Atelier Crenn** – Poetic ($$)`;

    const out = preprocessMarkdown(input);

    expect(out).not.toContain("```math");
    expect(out).toContain("($$)");
    expect(out).toContain("**Atelier Crenn**");
  });

  it("promotes Warning and Note blockquotes into callouts, not Tip", () => {
    const out = preprocessMarkdown(
      "> Tip: wear gloves\n>\n> Warning: hot surface\n>\n> Note: check the units",
    );
    expect(out).not.toContain("```callout-tip");
    expect(out).toContain("> Tip: wear gloves");
    expect(out).toContain("```callout-warning");
    expect(out).toContain("hot surface");
    expect(out).toContain("```callout-note");
    expect(out).toContain("check the units");
  });

  it("does not promote Hint or GitHub tip, important, and info alerts into cards", () => {
    const out = preprocessMarkdown(
      "> Hint: try factoring\n\n> [!TIP]\n> save a copy\n\n> [!IMPORTANT]\n> read this\n\n> [!INFO]\n> extra\n",
    );
    expect(out).not.toContain("```callout");
    expect(out).toContain("try factoring");
    expect(out).toContain("save a copy");
    expect(out).not.toContain("[!TIP]");
    expect(out).not.toContain("[!IMPORTANT]");
    expect(out).not.toContain("[!INFO]");
  });

  it("keeps GitHub warning and note alerts as callouts", () => {
    const out = preprocessMarkdown("> [!WARNING]\n> hot\n\n> [!NOTE]\n> units\n");
    expect(out).toContain("```callout-warning");
    expect(out).toContain("```callout-note");
    expect(out).toContain("hot");
    expect(out).toContain("units");
  });

  it("unwraps details fences and HTML details into a bold title and markdown", () => {
    const fenced = preprocessMarkdown(
      "```details\nClick for answer\n$x^2$\n- one\n```",
    );
    expect(fenced).toContain("**Click for answer**");
    expect(fenced).toContain("- one");
    expect(fenced).not.toContain("```details");

    const html = preprocessMarkdown(
      "<details><summary>Click for answer</summary>\n$x=2$\n</details>",
    );
    expect(html).toContain("**Click for answer**");
    expect(html).not.toContain("<details");
    expect(html).not.toContain("```details");
  });

  it("strips nested angle brackets from a details title", () => {
    const html = preprocessMarkdown(
      "<details><summary><scr<script>ipt>Click</script></summary>\nok\n</details>",
    );
    expect(html).toContain("**scrscriptiptClick/script**");
    expect(html).not.toContain("<");
    expect(html).not.toContain(">");
    expect(html).toContain("ok");
  });

  it("does not turn a plain settings sentence into a callout card", () => {
    const src =
      "Location is not turned on. Turn it on in Settings → Location to see nearby places.\n\n" +
      "Notifications are off. Turn them on in Settings → Notifications for reminders.";
    const out = preprocessMarkdown(src);
    expect(out).not.toContain("```callout-tip");
    expect(out).not.toContain("```callout-warning");
    expect(out).not.toContain("```callout-important");
    expect(out).toContain("Location is not turned on");
    expect(out).toContain("Notifications are off");
  });

  it("does not turn italic settings copy into a callout card", () => {
    const src =
      "*Location and notifications are off. Turn them on in Settings → Location / Settings → Notifications.*";
    const out = preprocessMarkdown(src);
    expect(out).not.toContain("```callout");
  });

  it("promotes a quoted paragraph with attribution into a blockquote", () => {
    const src =
      '"Courage is the most important of all the virtues because without courage, you can\'t practice any other virtue consistently." - Maya Angelou';
    const out = preprocessMarkdown(src);
    expect(out).toContain("> Courage is the most important of all the virtues");
    expect(out).toContain("> — Maya Angelou");
    expect(out).not.toMatch(/^"/);
  });

  it("does not promote a mid-sentence quoted phrase", () => {
    const src = 'She said "hello there" and left.';
    expect(preprocessMarkdown(src)).toBe(src);
  });

  it("does not rewrite quoted attribution inside a code fence", () => {
    const src =
      '```\n"Courage is the most important of all the virtues because without courage, you can\'t practice any other virtue consistently." - Maya Angelou\n```';
    const out = preprocessMarkdown(src);
    expect(out).toContain('"Courage is the most important');
    expect(out).not.toContain("> — Maya Angelou");
  });

  it("unwraps italic wrapping around a quoted attribution", () => {
    const src =
      '*"Courage is the most important of all the virtues because without courage, you can\'t practice any other virtue consistently." - Maya Angelou*';
    const out = preprocessMarkdown(src);
    expect(out).toContain("> Courage is the most important of all the virtues");
    expect(out).toContain("> — Maya Angelou");
  });

  it("lifts inline blockquote attribution onto its own line", () => {
    const src =
      "> Courage is the most important of all the virtues, because without courage you can't practice any other virtue consistently. — Maya Angelou";
    const out = preprocessMarkdown(src);
    expect(out).toContain(
      "> Courage is the most important of all the virtues, because without courage you can't practice any other virtue consistently.",
    );
    expect(out).toContain("> — Maya Angelou");
    expect(out).not.toMatch(/consistently\. — Maya Angelou/);
  });

  it("separates a citation line so the author is not part of the quote paragraph", () => {
    const src = "> We are such stuff as dreams are made on.\n> -- Prospero";
    const out = preprocessMarkdown(src);
    expect(out).toBe(
      "> We are such stuff as dreams are made on.\n>\n> -- Prospero",
    );
  });

  it("keeps a cited quote inside its list item", () => {
    const src =
      "1. First point\n\n   > Stay hungry, stay foolish.\n   > — Steve Jobs\n\n2. Second point";
    const out = preprocessMarkdown(src);
    expect(out).toContain("   > Stay hungry, stay foolish.\n   >\n   > — Steve Jobs");
    expect(topLevelTypes(out)).toEqual(["ordered_list_open"]);
  });

  it("keeps an inline attribution split inside its list item", () => {
    const src =
      "- Point\n\n  > Courage is the most important of all the virtues. — Maya Angelou\n\n- Next";
    const out = preprocessMarkdown(src);
    expect(out).toContain(
      "  > Courage is the most important of all the virtues.\n  >\n  > — Maya Angelou",
    );
    expect(topLevelTypes(out)).toEqual(["bullet_list_open"]);
  });

  it("promotes a Note inside a list item to a callout in that item", () => {
    const out = preprocessMarkdown("1. First point\n   > Note: check the units\n2. Second point");
    const tokens = markdownItInstance.parse(out, {});
    const fence = tokens.find((token) => token.type === "fence");
    expect(fence?.info).toBe("callout-note");
    expect(fence?.content).toBe("check the units\n");
    expect(fence?.level).toBeGreaterThan(0);
    expect(topLevelTypes(out)).toEqual(["ordered_list_open"]);
    expect(tokens.filter((token) => token.type === "list_item_open")).toHaveLength(2);
  });

  it("keeps every line of an indented Warning in its callout", () => {
    const out = preprocessMarkdown("- Item\n\n  > Warning: hot surface\n  > keep away\n- Next");
    const fence = markdownItInstance.parse(out, {}).find((token) => token.type === "fence");
    expect(fence?.info).toBe("callout-warning");
    expect(fence?.content).toBe("hot surface\nkeep away\n");
    expect(topLevelTypes(out)).toEqual(["bullet_list_open"]);
  });

  it("leaves an indented Note inside a code fence alone", () => {
    const src = "```markdown\n- Item\n  > Note: example\n```";
    expect(preprocessMarkdown(src)).toBe(src);
  });

  it.each([
    ["an en dash", "> Stay hungry, stay foolish.\n> – Steve Jobs"],
    ["a hyphen", "> Stay hungry, stay foolish.\n> - Steve Jobs"],
    ["a hyphen after a blank quote line", "> Stay hungry, stay foolish.\n>\n> - Steve Jobs"],
  ])("reads %s closing a quote as its attribution", (_name, src) => {
    const out = preprocessMarkdown(src);
    expect(out).toMatch(/>\n> — Steve Jobs$/);
    expect(markdownItInstance.parse(out, {}).some((t) => t.type === "bullet_list_open")).toBe(
      false,
    );
  });

  it("reads a hyphen attribution with its source", () => {
    const out = preprocessMarkdown(
      "> Stay hungry, stay foolish.\n> - Steve Jobs, Stanford commencement",
    );
    expect(out).toContain("> — Steve Jobs, Stanford commencement");
  });

  it("normalizes a hyphen attribution inside a list item", () => {
    const out = preprocessMarkdown(
      "1. First point\n\n   > Stay hungry, stay foolish.\n   > - Steve Jobs\n\n2. Second point",
    );
    expect(out).toContain("   >\n   > — Steve Jobs");
    expect(topLevelTypes(out)).toEqual(["ordered_list_open"]);
  });

  it.each([
    ["several items", "> Shopping:\n> - Eggs\n> - Milk"],
    ["items after a lead-in", "> Bring these\n> - Water\n> - Bread Rolls"],
    ["one item after a colon", "> Remember to:\n> - Buy Milk"],
    ["a lowercase item", "> Here is the plan\n> - buy milk"],
    ["a question", "> Here is the plan\n> - What Next?"],
    ["a lone item", "> - Steve Jobs"],
  ])("keeps a bulleted list inside a quote: %s", (_name, src) => {
    expect(preprocessMarkdown(src)).toBe(src);
  });

  it("still converts real display math delimiters", () => {
    const input = "The area is $$\\pi r^2$$ for a circle.";
    const out = preprocessMarkdown(input);
    expect(out).toContain("```math");
    expect(out).toContain("\\pi r^2");
  });

  it("repairs already-corrupted restaurant markdown from bad ($$) splits", () => {
    const corrupted = `Here are restaurants:

### **Fine Dining**
1. **Benu** – 3-Michelin stars, modern Asian fusion (
\`\`\`math
$)
2. **Atelier Crenn** – Poetic, French-inspired ($$$
\`\`\`
3. **State Bird Provisions** – Creative dim-sum ($$)`;

    const out = preprocessMarkdown(corrupted);

    expect(out).not.toContain("```math");
    expect(out).not.toContain("```\n$$");
    expect(out).toContain("**Benu**");
    expect(out).toContain("**Atelier Crenn**");
    expect(out).toContain("**State Bird Provisions**");
  });

  it("repairs broken salon markdown links with dollar delimiters", () => {
    const broken = `1. [CODE Salon]$https://www.yelp.com/biz/code$ — 4.7 stars
2. [Nepenji]$https://maps.google.com/?q=nepenji$ — Japanese care`;

    const out = preprocessMarkdown(broken);

    expect(out).toContain("[CODE Salon](https://www.yelp.com/biz/code)");
    expect(out).not.toContain("]$https://");
  });

  it("repairBrokenMarkdownLinks helper", () => {
    expect(
      repairBrokenMarkdownLinks("[A]$https://x.com$"),
    ).toBe("[A](https://x.com)");
  });

  it("unwraps inline math from inside bold markers", () => {
    expect(normalizeBoldInlineMath("**Answer: $x = 2$**")).toBe("**Answer:** $x = 2$");
    expect(normalizeBoldInlineMath("**$x^2$**")).toBe("$x^2$");
    expect(normalizeBoldInlineMath("**Final Answer:** $x = 2 or x = -2$")).toBe(
      "**Final Answer:** $x = 2 or x = -2$",
    );
  });

  it("repairs whitespace before bold closers without touching fences", () => {
    expect(trimBoldDelimiterWhitespace("**Why not simply $x$: **")).toBe(
      "**Why not simply $x$:**",
    );
    expect(
      trimBoldDelimiterWhitespace("```md\n**keep this: **\n```\n**repair this: **"),
    ).toBe("```md\n**keep this: **\n```\n**repair this:**");
    expect(preprocessMarkdown("**Apply to $\\sqrt{x}$: **")).toBe(
      "**Apply to $\\sqrt{x}$:**",
    );
  });

  it("pairs bold delimiters in order, so the space before the next opener stays", () => {
    // The closer of one span and the opener of the next used to read as one
    // padded span: "at **60** and at **40**" became "and at**40**", and after
    // punctuation ("20 + 7 = **27**") nothing put the space back.
    expect(trimBoldDelimiterWhitespace("at **60 km/h** and at **40 km/h**.")).toBe(
      "at **60 km/h** and at **40 km/h**.",
    );
    expect(trimBoldDelimiterWhitespace("**Combine:** 20 + 7 = **27**, **Check: **")).toBe(
      "**Combine:** 20 + 7 = **27**, **Check:**",
    );
    expect(trimBoldDelimiterWhitespace("`a ** b` and **c: **")).toBe("`a ** b` and **c:**");
    expect(preprocessMarkdown("**Combine:** 20 + 7 = **27**")).toBe("**Combine:** 20 + 7 = **27**");
    expect(preprocessMarkdown("| **Total** | **40** | **100%** |")).toContain(
      "| **Total** | **40** | **100%** |",
    );
  });

  it("keeps a bold-only math step label above its formula", () => {
    const source = "**Substitute and simplify**\n$\\frac{a}{b}=c$";
    expect(separateStandaloneBoldLines(source)).toBe(
      "**Substitute and simplify**\n\n$\\frac{a}{b}=c$",
    );
    expect(preprocessMarkdown(source)).toContain(
      "**Substitute and simplify**\n\n$\\frac{a}{b}=c$",
    );
    expect(
      separateStandaloneBoldLines("```md\n**keep**\n$x$\n```"),
    ).toBe("```md\n**keep**\n$x$\n```");
  });

  it("keeps mid-span math inside bold so list labels stay one line", () => {
    // Unwrapping produced **Slope (**$m$**):** which stacked as
    // "Slope (" / "m" / "): 3" in list items.
    expect(normalizeBoldInlineMath("**Slope ($m$):** 3")).toBe("**Slope ($m$):** 3");
    expect(normalizeBoldInlineMath("**Y-intercept ($b$):** 4")).toBe(
      "**Y-intercept ($b$):** 4",
    );
  });

  it("splitInlineMath handles final answer line", () => {
    const parts = splitInlineMath("Final Answer: $x = 2 or x = -2$");
    expect(parts).toEqual([
      { type: "text", value: "Final Answer: " },
      { type: "math", value: "x = 2 or x = -2" },
    ]);
  });

  it("does not typeset an English recap stuffed in $...$ as math", () => {
    // Live: "$Since 9 = 3^2, the 2 and 8 cancel down—the 8th root of 9 is just the$"
    // painted as italic ' = 3²,the2and8canceldown… (math mode drops spaces).
    const parts = splitInlineMath(
      "$Since 9 = 3^2, the 2 and 8 cancel down—the 8th root of 9 is just the$",
    );
    expect(parts).toEqual([
      {
        type: "text",
        value:
          "Since 9 = 3^2, the 2 and 8 cancel down—the 8th root of 9 is just the",
      },
    ]);
    expect(splitInlineMath("$3^{1/4}$")).toEqual([
      { type: "math", value: "3^{1/4}" },
    ]);
    expect(
      splitInlineMath("Set $\\begin{Bmatrix}1&2\\\\3&4\\end{Bmatrix}$."),
    ).toEqual([
      { type: "text", value: "Set " },
      { type: "math", value: "\\begin{Bmatrix}1&2\\\\3&4\\end{Bmatrix}" },
      { type: "text", value: "." },
    ]);
  });

  it("BUG FIX regression: check lines keep a space after 'x = 2:' so 2:2² does not glue", () => {
    // Live: "For $x = 2$: $2^2 + 2 = 6$" (or one $x = 2: 2^2$ span) rendered
    // as 2:2². Split the label from the formula and force a space after `:`.
    expect(layoutCheckVerificationLines("For $x = 2$:$2^2 + 2 = 6$")).toBe(
      "For $x = 2$:\n\n  $2^2 + 2 = 6$",
    );
    expect(layoutCheckVerificationLines("For $x = 2: 2^2 + 2 = 6$")).toBe(
      "For $x = 2$:\n\n  $2^2 + 2 = 6$",
    );
    expect(layoutCheckVerificationLines("- [x] For $x = -2$:$(-2)^2 + 2 = 6$")).toBe(
      "- [x] For $x = -2$:\n\n  $(-2)^2 + 2 = 6$",
    );
  });

  it("puts the check substitution on the line under For n = …", () => {
    expect(layoutCheckVerificationLines("• For F = 0: 0 + 3 = 3 ✓")).toBe(
      "• For F = 0:\n\n  0 + 3 = 3 ✓",
    );
    expect(layoutCheckVerificationLines("- For F = 0: 0 + 3 = 3")).toBe(
      "- For F = 0:\n\n  0 + 3 = 3",
    );
    expect(layoutCheckVerificationLines("For example: try again")).toBe("For example: try again");
  });

  it("BUG FIX regression: check chains split so = 0 is not clipped off-screen", () => {
    const packed =
      "- For $x = 3$: $2(3)^2 - 7(3) + 3 = 18 - 21 + 3 = 0$";
    const out = layoutCheckVerificationLines(packed);
    expect(out).toContain("- For $x = 3$:");
    expect(out).toMatch(/For \$x = 3\$:\n\n/);
    expect(out).toContain("$2(3)^2 - 7(3) + 3$");
    expect(out).toContain("$= 18 - 21 + 3$");
    expect(out).toContain("$= 0$");
    expect(out).not.toMatch(/18 - 21 \+ 3 = 0/);

    const frac =
      "- For $x = \\frac{1}{2}$: $2(\\frac{1}{2})^2 - 7(\\frac{1}{2}) + 3 = \\frac{1}{2} - \\frac{7}{2} + 3 = \\frac{1 - 7 + 6}{2} = 0$";
    const fracOut = layoutCheckVerificationLines(frac);
    expect(fracOut).toMatch(/For \$x = \\frac\{1\}\{2\}:\$\n\n/);
    expect(fracOut).toContain("$= 0$");
    expect(fracOut.split("\n").some((l) => l.includes("$= 0$"))).toBe(true);

    const homework = "8. Calculate: $x = \\frac{12}{4}$ or $x = \\frac{2}{4}$";
    expect(layoutCheckVerificationLines(homework)).toBe(homework);
  });

  it("BUG FIX regression: no-colon For x = 1/2 still splits the = chain", () => {
    const live =
      "You can check:\n" +
      "- For $x = 3$: $2(3)^2 - 7(3) + 3 = 18 - 21 + 3 = 0$\n" +
      "- For $x = \\frac{1}{2}$\n" +
      "$2(\\frac{1}{2})^2 - 7(\\frac{1}{2}) + 3 = \\frac{1}{2} - \\frac{7}{2} + 3 = \\frac{1-7+6}{2} = 0$";
    const out = layoutCheckVerificationLines(live);
    expect(out).toMatch(/For \$x = 3\$:\n\n/);
    expect(out).toMatch(/For \$x = \\frac\{1\}\{2\}:\$/);
    expect(out).not.toMatch(/For \$x = \\frac\{1\}\{2\}\$\n/);
    expect(out).toContain("$2(3)^2 - 7(3) + 3$");
    expect(out).toContain("$= 18 - 21 + 3$");
    expect(out).toContain("$2(\\frac{1}{2})^2 - 7(\\frac{1}{2}) + 3$");
    expect(out).toContain("$= \\frac{1}{2} - \\frac{7}{2} + 3$");
    expect(out).toContain("$= \\frac{1-7+6}{2}$");
    expect(out.split("\n").filter((l) => l.includes("$= 0$")).length).toBe(2);
    expect(out).not.toMatch(/18 - 21 \+ 3 = 0/);
    expect(out).not.toMatch(/\\frac\{1\}\{2\} - \\frac\{7\}\{2\} \+ 3 = /);

    const mixed =
      "- For $x = 3$:\n$2(3)^2 - 7(3) + 3$ = $18 - 21 + 3$ = $0$";
    const mixedOut = layoutCheckVerificationLines(mixed);
    expect(mixedOut).toContain("$2(3)^2 - 7(3) + 3$");
    expect(mixedOut).toContain("$= 18 - 21 + 3$");
    expect(mixedOut).toContain("$= 0$");
  });

  it("BUG FIX regression: live You can check with ✓ and For $x$ = frac still splits", () => {
    const live =
      "You can check:\n" +
      "- For $x = 3$: $2(3)^2 - 7(3) + 3 = 18 - 21 + 3 = 0$ ✓\n" +
      "- For $x$ = $\\frac{1}{2}$\n" +
      "$2(\\frac{1}{2})^2 - 7(\\frac{1}{2}) + 3 = \\frac{1}{2} - \\frac{7}{2} + 3 = -3 + 3 = 0$\n" +
      "✓";
    const out = preprocessMarkdown(live);
    expect(out).toMatch(/For \$x = 3\$:\n\n/);
    expect(out).toMatch(/For \$x\$ = \$\\frac\{1\}\{2\}:\$/);
    expect(out).toContain("$2(3)^2 - 7(3) + 3$");
    expect(out).toContain("$= 18 - 21 + 3$");
    expect(out).toContain("$2(\\frac{1}{2})^2 - 7(\\frac{1}{2}) + 3$");
    expect(out).toContain("$= \\frac{1}{2} - \\frac{7}{2} + 3$");
    expect(out).toContain("$= -3 + 3$");
    expect(out.split("\n").filter((l) => l.includes("$= 0$")).length).toBeGreaterThanOrEqual(2);
    expect(out).not.toMatch(/18 - 21 \+ 3 = 0/);

    const withTick = layoutCheckVerificationLines(
      "- For $x = 3$:\n$2(3)^2 - 7(3) + 3 = 18 - 21 + 3 = 0$ ✓",
    );
    expect(withTick).toContain("$= 0$ ✓");
    expect(withTick).not.toMatch(/18 - 21 \+ 3 = 0/);

    const fracLabel = layoutCheckVerificationLines("- For $x = \\frac{1}{2}$");
    expect(fracLabel).toContain("$x = \\frac{1}{2}:$");
    expect(fracLabel).not.toMatch(/\\frac\{1\}\{2\}\$:/);
  });

  it("preprocess keeps math adjacent to bold labels", () => {
    const out = preprocessMarkdown("**Final Answer:** $x = 2 or x = -2$");
    expect(out).toContain("**Final Answer:**");
    expect(out).toContain("$x = 2 or x = -2$");
  });

  it("mergeStrandedColons: merges a lone colon line onto the previous line", () => {
    // The model puts ":" on its own line after a bold step header, which
    // renders as a stranded "two dots" between the header and the math.
    expect(
      mergeStrandedColons("2. **Multiply**\n:\n   $3 \\times 2 = 6$"),
    ).toBe("2. **Multiply**:\n   $3 \\times 2 = 6$");
  });

  it("mergeStrandedColons: ignores lines that are not just a colon", () => {
    expect(mergeStrandedColons("Hello\n: world")).toBe("Hello\n: world");
    expect(mergeStrandedColons("**Step**\nSome text\n:")).toBe(
      "**Step**\nSome text:",
    );
  });

  it("mergeStrandedColons: does not merge a colon as the first line", () => {
    expect(mergeStrandedColons(":\nHello")).toBe(":\nHello");
  });

  it("breakMidlineAtxHeadings: pulls ### off the previous sentence", () => {
    expect(breakMidlineAtxHeadings("Here's a breakdown: ### Explanation")).toBe(
      "Here's a breakdown:\n\n### Explanation",
    );
    expect(breakMidlineAtxHeadings("$y = 3x + 4$: ### Explanation")).toBe(
      "$y = 3x + 4$:\n\n### Explanation",
    );
    // Already a real heading — leave it.
    expect(breakMidlineAtxHeadings("### Explanation\n\nHello")).toBe(
      "### Explanation\n\nHello",
    );
  });

  it("BUG FIX regression: mergeStrandedColons also merges stranded semicolons", () => {
    expect(mergeStrandedColons("**Step**\n;\n   $x = 5$")).toBe(
      "**Step**;\n   $x = 5$",
    );
    expect(mergeStrandedColons("Label\n;")).toBe("Label;");
    // Semicolon as first line is not merged
    expect(mergeStrandedColons(";\nHello")).toBe(";\nHello");
  });

  it("BUG FIX regression: mergeStrandedColons does not glue colon onto fence closer or table row (PRE-009)", () => {
    // Fence closer — colon should stay on its own line.
    expect(mergeStrandedColons("```math\n1+1\n```\n:")).toBe("```math\n1+1\n```\n:");
    // Table row — colon should stay on its own line.
    expect(mergeStrandedColons("| a | b |\n:")).toBe("| a | b |\n:");
    // Heading — colon should stay on its own line.
    expect(mergeStrandedColons("# Heading\n:")).toBe("# Heading\n:");
  });

  it("preprocessMarkdown removes stranded colons after bold list labels", () => {
    const input = `1. **Substitute** $n = 3$: $3! = 3 \\times 2 \\times 1$
2. **Multiply**
:
   $3 \\times 2 = 6$
3. **Final step**
:
   $6 \\times 1 = 6$`;
    const out = preprocessMarkdown(input);
    expect(out).toContain("**Multiply**\n");
    expect(out).toContain("**Final step**\n");
    expect(out).not.toMatch(/(?:\n:|\*\*:|·)/);
  });

  it("removes decorative colons before values under bold list labels", () => {
    const input = `- **Chemical Formula**
  : O₂
- **Appearance**
  : Colorless gas
1. **Role**
   : Essential for respiration`;

    expect(stripBoldListLabelContinuationColons(input)).toBe(`- **Chemical Formula**
  O₂
- **Appearance**
  Colorless gas
1. **Role**
   Essential for respiration`);
    expect(preprocessMarkdown(input)).not.toMatch(/^\s*:|·/m);
  });

  it("keeps unrelated and fenced colon-prefixed lines intact", () => {
    const input = `Regular label
: keep this
\`\`\`text
- **Chemical Formula**
  : keep in code
\`\`\``;

    expect(stripBoldListLabelContinuationColons(input)).toBe(input);
  });

  it("keeps a short ```math fence inside a numbered solution step intact", () => {
    const input = `1. Start with the equation:
1 + 4 = 5 + x

2. Simplify the left side:
\`\`\`math
5 = 5 + x
\`\`\`

3. Subtract 5 from both sides to isolate x:
5 - 5 = 5 + x - 5

4. Final result:
\`\`\`math
x = 0
\`\`\``;

    const out = preprocessMarkdown(input);

    expect(out).toContain("```math\n5 = 5 + x\n```");
    expect(out).toContain("```math\nx = 0\n```");
    expect(out).toContain("2. Simplify the left side:");
    expect(out).toContain("3. Subtract 5 from both sides to isolate x:");
    expect(out).toContain("4. Final result:");
  });

  it("BUG FIX regression: inline math fence tail does not absorb list items or headings", () => {
    // After inlining a short ```math fence, the code merges a following
    // line starting with ?!,.;: — but must NOT absorb headings, list
    // items, images, table rows, or blockquotes.
    const input = `\`\`\`math
x = 5
\`\`\`

# Next Section`;
    const out = preprocessMarkdown(input);
    expect(out).toContain("# Next Section");

    const input2 = `\`\`\`math
x = 5
\`\`\`

- A list item`;
    const out2 = preprocessMarkdown(input2);
    expect(out2).toContain("- A list item");

    const input3 = `\`\`\`math
x = 5
\`\`\`

![image](url.png)`;
    const out3 = preprocessMarkdown(input3);
    expect(out3).toContain("![image](url.png)");
  });

  it("BUG FIX regression: liftMathFencesOutOfLists strips body indent to match column-0 opener", () => {
    // A math fence inside a numbered list has its opener lifted to column 0,
    // but body lines used to keep their list indent (4+ spaces), causing
    // CommonMark to treat them as indented code blocks with visible backticks.
    const input = `1. Step:

   \`\`\`math
   x = 5
   \`\`\`

2. Next`;
    const out = preprocessMarkdown(input);
    // The math fence should be at column 0 with body at column 0 too
    expect(out).toContain("```math\nx = 5\n```");
    expect(out).not.toMatch(/```math\n\s+x = 5/);
  });

  it("BUG FIX regression: empty solve bullet + math fence keeps x = 3 on the marker", () => {
    // Live vs ChatGPT: "Solve for x" showed `$2x-1=0 → x=1/2$` then a purple
    // dot with no text — the second root was ```math / \[ \] after a lone `-`,
    // which streams blank and never reaches MathText.
    const fenced = `4. **Solve for x**:
   - $2x - 1 = 0 \\rightarrow x = 1/2$
   -

\`\`\`math
x - 3 = 0 \\rightarrow x = 3
\`\`\``;
    const fromFence = preprocessMarkdown(fenced);
    expect(fromFence).toMatch(/-\s+\$x - 3 = 0 \\rightarrow x = 3\$/);
    expect(fromFence).not.toMatch(/```math/);

    const fromDisplay = preprocessMarkdown(
      "4. **Solve for x**:\n   - $2x - 1 = 0$\n   - \\[ x - 3 = 0 \\rightarrow x = 3 \\]",
    );
    expect(fromDisplay).toMatch(/-\s+\$x - 3 = 0 \\rightarrow x = 3\$/);

    const standalone = preprocessMarkdown("The roots are\n\n```math\nx = 0\n```");
    expect(standalone).toContain("```math");
    expect(standalone).toContain("x = 0");
  });

  it("keeps 2 + Y / Y in the sentence instead of a math card", () => {
    const input = `**Solve an equation** involving
\`\`\`math
2 + Y
\`\`\`
? (e.g., 2 + Y = 7)

what
\`\`\`math
Y
\`\`\`
represents`;
    const out = preprocessMarkdown(input);
    expect(out).not.toMatch(/```math/);
    expect(out).toContain("$2 + Y$");
    expect(out).toContain("$Y$");
    expect(out).toMatch(/involving \$2 \+ Y\$ \?/);
  });

  it("lifts an indented evaluation-bar ```math fence out of a numbered step", () => {
    const input = `2. Apply the limits 2 and 8:
   \`\`\`math
   \\left.\\frac{x^{3}}{3}\\right|_{2}^{8}
   = \\frac{8^{3}}{3}-\\frac{2^{3}}{3}
   = \\frac{512}{3}-\\frac{8}{3}
   = \\frac{504}{3}
   \`\`\`

3. Simplify:
   \`\`\`math
   \\frac{504}{3} = 168
   \`\`\``;
    const out = preprocessMarkdown(input);
    expect(out).toContain("```math\n");
    expect(out).not.toMatch(/^[ \t]+```math/m);
    const tokens = markdownItInstance.parse(out, {});
    const fenceBodies = tokens
      .filter((t) => t.type === "fence")
      .map((t) => t.content);
    expect(fenceBodies.some((b) => b.includes("\\left."))).toBe(true);
    expect(fenceBodies.some((b) => b.includes("504"))).toBe(true);
    const asText = tokens
      .filter((t) => t.type === "inline" || t.type === "paragraph_open")
      .map((t) => t.content)
      .join("\n");
    expect(asText).not.toContain("```math");
  });

  it("BUG FIX regression: ```math glued to a sentence is a real fence, not raw LaTeX", () => {
    // Live: "Multiply both sides by r: ```math" then the equation — CommonMark
    // ignored the mid-line opener and painted ```math, \frac, \quad, \Rightarrow.
    const input =
      "Multiply both sides by r: ```math\n" +
      "r^2 + 1 = \\frac{17}{4}r \\quad \\Rightarrow \\quad 4r^2 - 17r + 4 = 0\n" +
      "```\n\n*Solve:*\n```math\n(4r-1)(r-4)=0\n```";
    const out = preprocessMarkdown(input);
    expect(out).not.toMatch(/r: ```math/);
    expect(breakAttachedMathFences("Multiply both sides by r: ```math")).toContain(
      "```math",
    );
    expect(out).toContain("Multiply both sides by r:");
    const tokens = markdownItInstance.parse(out, {});
    const fences = tokens.filter((t) => t.type === "fence");
    expect(fences.length).toBeGreaterThanOrEqual(2);
    expect(fences.some((t) => t.content.includes("\\frac{17}{4}"))).toBe(true);
    const asText = tokens
      .filter((t) => t.type === "inline")
      .map((t) => t.content)
      .join("\n");
    expect(asText).not.toContain("```math");
    expect(asText).not.toContain("\\frac");
  });

  it("BUG FIX regression: unclosed step ```math does not dump the next step in a code card", () => {
    // Live: "isolate x: ```math" then \frac, then "2. **Simplify:**" and
    // another ```math. A /```math[\s\S]*?```/ closer ate the second opener,
    // so \frac painted as prose and Simplify landed in a gray code block.
    const input =
      "1. **Divide both sides by 4** to isolate x: ```math\n" +
      String.raw`\frac{4x}{4} = \frac{4}{4}` +
      "\n\n2. **Simplify:**\n\n```math\nx = 1\n```";
    const out = preprocessMarkdown(input);
    expect(out).not.toMatch(/x: ```math/);
    expect(out).toContain("2. **Simplify:**");
    const tokens = markdownItInstance.parse(out, {});
    const fences = tokens.filter((t) => t.type === "fence");
    expect(fences.some((t) => (t.info ?? "").trim() === "math" && t.content.includes("\\frac"))).toBe(
      true,
    );
    expect(fences.some((t) => (t.info ?? "").trim() === "math" && /x\s*=\s*1/.test(t.content))).toBe(
      true,
    );
    expect(
      fences.some(
        (t) => t.content.includes("Simplify") || t.content.includes("```math"),
      ),
    ).toBe(false);
    const asText = tokens
      .filter((t) => t.type === "inline")
      .map((t) => t.content)
      .join("\n");
    expect(asText).toContain("**Simplify:**");
    expect(asText).not.toContain("```math");
    expect(asText).not.toMatch(/\\frac\{4x\}/);
  });

  it("BUG FIX regression: 4-space-indented Simplify is not a code card", () => {
    // Live screenshot: step 1 kept mid-line ```math + raw \\frac, and
    // CommonMark ate `    2. **Simplify:**` + nested ```math as indented code
    // (gray Prism card, asterisks visible, `1` highlighted).
    const input = [
      "Got it! Since you wrote 4x = and then 4, the full equation is:",
      "",
      "**Equation to solve:**",
      "4x = 4",
      "",
      "---",
      "",
      "**Step-by-Step Solution:**",
      "1. **Divide both sides by 4** to isolate x: ```math",
      "   " + String.raw`\frac{4x}{4} = \frac{4}{4}`,
      "",
      "    2. **Simplify:**",
      "",
      "    ```math",
      "    x = 1",
      "    ```",
      "",
      "✅ **Check the answer:** Plug x = 1 back in:",
      "4(1) = 4 ✓",
    ].join("\n");
    const out = preprocessMarkdown(input);
    const tokens = markdownItInstance.parse(out, {});
    const codeBlocks = tokens.filter((t) => t.type === "code_block");
    const fences = tokens.filter((t) => t.type === "fence");
    const inline = tokens
      .filter((t) => t.type === "inline")
      .map((t) => t.content)
      .join("\n");
    expect(codeBlocks.some((t) => /Simplify|```/.test(t.content))).toBe(false);
    expect(fences.some((t) => t.content.includes("Simplify"))).toBe(false);
    expect(inline).not.toContain("```");
    const fracInFence = fences.some(
      (t) => (t.info ?? "").trim() === "math" && t.content.includes("\\frac"),
    );
    const fracInMath = /\$[^$]*\\frac\{4x\}/.test(inline);
    expect(fracInFence || fracInMath).toBe(true);
    expect(
      fences.some((t) => /x\s*=\s*1/.test(t.content)) || /\$x\s*=\s*1\$/.test(inline),
    ).toBe(true);
    expect(inline).toContain("**Simplify:**");
  });

  it("BUG FIX regression: glued ``` math (space after ticks) still lifts", () => {
    const out = breakAttachedMathFences("isolate x: ``` math");
    expect(out).not.toMatch(/x: ``` math/);
    expect(out).toContain("isolate x:");
    expect(out).toContain("```math");
  });

  it("BUG FIX regression: glued ````math (4 ticks) still lifts", () => {
    const out = breakAttachedMathFences("isolate x: ````math");
    expect(out).not.toMatch(/x: `+math/);
    expect(out).toContain("isolate x:");
    expect(out).toContain("```math");
  });

  it("BUG FIX regression: lifts glued code fence openers for all langs, not just math", () => {
    // The model also glues code fence openers to prose
    // ("Here's the code: ```python print('hello')```"). The old
    // breakAttachedMathFences only handled math/latex/tex/answer/graph/
    // geometry langs; now it handles all recognized fence langs.
    const out = breakAttachedMathFences("Here's the code: ```python print('hello')```");
    expect(out).not.toMatch(/code: ```python/);
    expect(out).toContain("Here's the code:");
    expect(out).toContain("```python");
  });

  it("moves a quiz's JSON off the ```quiz line so the card still draws", () => {
    // Live: "teach me american history" ended on ```quiz {"label": ...} with the
    // closer on the next line.
    const json =
      '{"label": "Exercise 1", "question": "Why?", "code": "", "options": ["A", "B"], "answer": 1}';
    const out = preprocessMarkdown(`### 5. Your turn\n\`\`\`quiz ${json}\n\`\`\``);
    expect(out).toContain(`\`\`\`quiz\n${json}\n\`\`\``);
    const fence = markdownItInstance.parse(out, {}).find((t) => t.type === "fence");
    expect(fence?.info).toBe("quiz");
    expect(JSON.parse(fence?.content ?? "")).toMatchObject({ answer: 1 });
  });

  it("BUG FIX regression: does not lift ```python out of a table cell", () => {
    // Live: Python vs Java comparison — a Hello World cell started
    // ```python, breakAttachedMathFences pulled it onto its own line, and
    // the closer (` ``` | ```java`) never matched, so the Use Cases table
    // rendered inside a python code block.
    const row = "| Example (Hello World) | ```python";
    expect(breakAttachedMathFences(row)).toBe(row);

    const input = [
      "| Feature | Python | Java |",
      "| --- | --- | --- |",
      "| Readability | high | verbose |",
      "| Example (Hello World) | ```python",
      'print("Hello, world!")',
      "``` | ```java",
      'System.out.println("Hello");',
      "``` |",
      "",
      "### Use Cases",
      "",
      "| Feature | Python | Java |",
      "| --- | --- | --- |",
      "| Web Development | Django, Flask | Spring |",
    ].join("\n");
    const out = preprocessMarkdown(input);
    const tokens = markdownItInstance.parse(out, {});
    const fenceBodies = tokens
      .filter((t) => t.type === "fence")
      .map((t) => t.content)
      .join("\n");
    expect(fenceBodies).not.toMatch(/Web Development/);
    expect(fenceBodies).not.toMatch(/Use Cases/);
    expect(out).toContain("Web Development");
    const tables = tokens.filter((t) => t.type === "table_open");
    expect(tables.length).toBeGreaterThanOrEqual(1);
  });

  it("keeps a GFM table inside an explicit python fence instead of splitting it out", () => {
    // A valid Python program can contain a Markdown table in a string.
    // Splitting it out used to change the program. The table-cell
    // ```python swallow case is handled by breakAttachedMathFences.
    const input = [
      "```python",
      'print("Hello, world!")',
      "",
      "### Use Cases",
      "",
      "| Feature | Python | Java |",
      "| --- | --- | --- |",
      "| Web Development | Django, Flask | Spring |",
      "```",
    ].join("\n");
    const out = preprocessMarkdown(input);
    expect(out).toContain("```python");
    expect(out).toContain("| Web Development | Django, Flask | Spring |");
    const tokens = markdownItInstance.parse(out, {});
    const fenceBodies = tokens
      .filter((t) => t.type === "fence")
      .map((t) => t.content)
      .join("\n");
    expect(fenceBodies).toMatch(/Web Development/);
    expect(tokens.some((t) => t.type === "table_open")).toBe(false);
  });

  it("BUG FIX regression: does not leave a stray backtick on a check-sum line", () => {
    // Live: "✅ Check sum: 2 + 8 + 32 = 42`" — leftover markdown tick.
    const input = "✅ Check sum: `2 + 8 + 32 = 42`\n✅ Check sum: 2 + 8 + 32 = 42`";
    const out = preprocessMarkdown(input);
    expect(out).not.toMatch(/42`/);
    expect(unwrapProseMathBackticks("✅ Check sum: 2 + 8 + 32 = 42`")).toBe(
      "✅ Check sum: 2 + 8 + 32 = 42",
    );
    expect(out).toContain("2 + 8 + 32 = 42");
  });

  it("does not unwrap non-math inline code", () => {
    const input = "Install with `npm install` then run.";
    expect(preprocessMarkdown(input)).toContain("`npm install`");
  });

  it("BUG FIX regression: ```graph glued to a sentence is a real fence, not raw JSON", () => {
    // The model puts ```graph on the same line as the preceding text
    // ("Here's the graph of y = x + 2: ```graph") — CommonMark only
    // recognizes a fence at the start of a line, so without breaking
    // it onto its own line the JSON body renders as a code block instead
    // of routing to FunctionGraphBlock. shouldLiftFenceOutOfList includes
    // graph|geometry, not just math|latex|tex|answer.
    const input =
      "Here's the graph of y = x + 2: ```graph\n" +
      '{"type":"function","expr":"x + 2","variable":"x","x_min":-10.0,"x_max":10.0,"points":[[-10.0,-8.0],[10.0,12.0]]}\n' +
      "```";
    const out = preprocessMarkdown(input);
    expect(out).not.toMatch(/2: ```graph/);
    expect(out).toContain("Here's the graph of y = x + 2:");
    const tokens = markdownItInstance.parse(out, {});
    const fences = tokens.filter((t) => t.type === "fence");
    expect(fences.length).toBeGreaterThanOrEqual(1);
    expect(fences.some((t) => t.info?.trim() === "graph")).toBe(true);
  });

  it("BUG FIX regression: ```geometry glued to a sentence is a real fence", () => {
    const input =
      "Here's the diagram: ```geometry\n" +
      '{"type":"triangle","vertices":[[0,0],[4,0],[2,3]]}\n' +
      "```";
    const out = preprocessMarkdown(input);
    expect(out).not.toMatch(/diagram: ```geometry/);
    expect(out).toContain("Here's the diagram:");
    const tokens = markdownItInstance.parse(out, {});
    const fences = tokens.filter((t) => t.type === "fence");
    expect(fences.some((t) => t.info?.trim() === "geometry")).toBe(true);
  });

  it("BUG FIX regression: ```molecule3d glued to a sentence is a real fence (digits in lang)", () => {
    // takeLang only read [a-zA-Z-], so "molecule3d" was split into
    // "molecule" (unrecognized) + "3d" (body), and the glued opener
    // was never lifted — the fence rendered as prose with literal backticks.
    const input =
      "Here's the 3D structure: ```molecule3d\nO2\n\n     RDKit          3D\n\n  2  1  0  0  0  0  0  0  0  0999 V2000\nM  END\n```";
    const out = preprocessMarkdown(input);
    expect(out).not.toMatch(/structure: ```molecule3d/);
    expect(out).toContain("Here's the 3D structure:");
    const tokens = markdownItInstance.parse(out, {});
    const fences = tokens.filter((t) => t.type === "fence");
    expect(fences.some((t) => t.info?.trim() === "molecule3d")).toBe(true);
  });

  it("collapses adjacent closed smiles + molecule3d into one molecule fence", () => {
    const input =
      "```smiles\nCCO\n```\n\n```molecule3d\nEthanol\n     RDKit          3D\n\n  3  2  0  0  0  0  0  0  0  0999 V2000\n    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0  0\n    1.5000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0  0\n    2.5000    1.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0  0\n  1  2  1  0\n  2  3  1  0\nM  END\n```";
    const out = preprocessMarkdown(input);
    const tokens = markdownItInstance.parse(out, {});
    const fences = tokens.filter((t) => t.type === "fence");
    expect(fences.map((t) => t.info?.trim())).toEqual(["molecule"]);
    expect(out).toContain("CCO");
    expect(out).not.toContain("```smiles");
    expect(out).not.toContain("```molecule3d");
  });

  it("leaves unpaired smiles and standalone molecule3d alone", () => {
    const smilesOnly = preprocessMarkdown("```smiles\nCCO\n```");
    expect(markdownItInstance.parse(smilesOnly, {}).some((t) => t.type === "fence" && t.info?.trim() === "smiles")).toBe(true);

    const input =
      "Here's the 3D structure: ```molecule3d\nO2\n\n     RDKit          3D\n\n  2  1  0  0  0  0  0  0  0  0999 V2000\nM  END\n```";
    const out = preprocessMarkdown(input);
    const fences = markdownItInstance.parse(out, {}).filter((t) => t.type === "fence");
    expect(fences.some((t) => t.info?.trim() === "molecule3d")).toBe(true);
    expect(fences.some((t) => t.info?.trim() === "molecule")).toBe(false);
  });

  it("does not collapse while the trailing molecule3d fence is still open", () => {
    const input = "```smiles\nCCO\n```\n\n```molecule3d\nEthanol\n     RDKit";
    const out = preprocessMarkdown(input);
    expect(out).toContain("```smiles");
    expect(out).toContain("```molecule3d");
    expect(out).not.toMatch(/```molecule\n/);
  });

  it("drops a leftover molecule3d under a 3D Structure heading after pairing", () => {
    const input =
      "```smiles\nCCO\n```\n\n```molecule3d\nEthanol\n     RDKit          3D\n\n  3  2  0  0  0  0  0  0  0  0999 V2000\n    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0  0\n    1.5000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0  0\n    2.5000    1.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0  0\n  1  2  1  0\n  2  3  1  0\nM  END\n```\n\n## 3D Structure\n\n```molecule3d\nnot sdf\n```";
    const out = preprocessMarkdown(input);
    const fences = markdownItInstance.parse(out, {}).filter((t) => t.type === "fence");
    expect(fences.map((t) => t.info?.trim())).toEqual(["molecule"]);
    expect(out).not.toContain("```molecule3d");
    expect(out).not.toMatch(/3D Structure/i);
  });

  it("BUG FIX regression: does not unwrap a math fence just because its content starts with a dollar sign", () => {
    // The price-tier-corruption check matched any body starting with "$",
    // not just the specific "$)" artifact left on its own line by a botched
    // ($$) price-tier split. A legitimate ```math fence whose body happens
    // to start with "$" — e.g. one normalizeImplicitMath had already
    // dollar-wrapped as a bare-equation line before BLOCK_MATH_BRACKET_RE
    // promoted it into a fence — used to get incorrectly unwrapped back to
    // plain inline text.
    const input = "```math\n$x^2 = 4$\n```";
    const out = preprocessMarkdown(input);
    expect(out).toContain("```math");
    expect(out).toContain("$x^2 = 4$");
  });

  it("keeps a currency final inside its explicit answer fence", () => {
    const input = "```answer\n$17,000\n```";
    const out = preprocessMarkdown(input);
    const fences = markdownItInstance.parse(out, {}).filter((t) => t.type === "fence");
    expect(fences).toHaveLength(1);
    expect(fences[0].info.trim()).toBe("answer");
    expect(fences[0].content.trim()).toBe("$17,000");
  });

  it("still repairs a genuine bare-$ (no closing paren) price-tier artifact, stripping the leading $", () => {
    const input = "```math\n$\n1. **Benu** – fusion ($$$)\n```";
    const out = preprocessMarkdown(input);
    expect(out).not.toContain("```math");
    expect(out.trim()).toBe("1. **Benu** – fusion ($$$)");
  });

  it("does not unwrap a math fence just because its content has bold text", () => {
    const input = "```math\n**x** = 5\n```";
    const out = preprocessMarkdown(input);
    expect(out).toContain("```math");
    expect(out).toContain("**x** = 5");
  });

  it("BUG FIX regression: keeps a mis-tagged ```copy fence with a bare math-answer body as a real fence, not unwrapped prose", () => {
    // Reported live: "2c^2" (a simplified final result) sent as ```copy\n2c^2\n```
    // used to get unwrapped into plain prose text by unwrapNonCodeFences
    // (which has no concept of "this looks like a math answer") before it
    // ever reached renderFence's AnswerBlock dispatch — losing the fence
    // entirely and rendering as a bare paragraph instead of a boxed answer.
    const input = "```copy\n2c^2\n```";
    const out = preprocessMarkdown(input);
    expect(out).toContain("```");
    expect(out).toContain("2c^2");
  });

  it("BUG FIX regression: converts \\[...\\] display math with multiple commands to a clean fence, not a $-corrupted one", () => {
    // Reported live (screenshots): "x = $\\pm$ $\\sqrt{4}$" rendered in red
    // inside a ```math fence. normalizeImplicitMath's wrapInlineLatexCommands
    // used to wrap each bare command inside a \\[...\\] span in $...$ before
    // this function's own BLOCK_MATH_BRACKET_RE converted the span into a
    // ```math fence, leaving the fence body with embedded $ characters KaTeX
    // can't parse as bare LaTeX (rendered in errorColor red instead).
    const input = "Solve:\n\n\\[ x = \\pm \\sqrt{4} \\]\n\nSo x = 2 or x = -2";
    const out = preprocessMarkdown(input);
    expect(out).toContain("```math\nx = \\pm \\sqrt{4}\n```");
    expect(out).not.toContain("$\\pm$");
    expect(out).not.toContain("$\\sqrt{4}$");
  });

  it("BUG FIX regression: prose parentheticals with nested $math$ do not steal the next $$ display block", () => {
    const input = [
      "like a hidden quadratic (e.g., in disguise like $x^4$)",
      "",
      "### Title",
      "",
      "$$",
      String.raw`\frac{2x - 1}{x + 3} = \frac{x + 4}{x - 2}`,
      "$$",
      "",
      "⚠️ **Wait — this isn’t *technically* quadratic yet**",
      "- Domain restrictions (excluded values: $x \\neq -3, 2$)",
    ].join("\n");
    const out = preprocessMarkdown(input);
    expect(out).toContain("```math\n\\frac{2x - 1}{x + 3} = \\frac{x + 4}{x - 2}\n```");
    expect(out).toContain("⚠️ **Wait — this isn’t *technically* quadratic yet**");
    expect(out).toContain("excluded values: $x \\neq -3, 2$");
    // Prose must not land inside a math fence
    expect(out).not.toMatch(/```math\n⚠️/);
  });

  it("BUG FIX regression: protects punctuation-led LaTeX commands (\\, \\; \\!) inside inline math from markdown-it's own CommonMark backslash-escape, which otherwise silently drops the backslash and leaves a stray comma/semicolon/exclamation mark mid-formula", () => {
    // Reported live: markdown-it's built-in escape rule treats "\" + any
    // ASCII punctuation char as an escape and drops the backslash *before*
    // splitInlineMath/MathText ever see the text — confirmed by parsing the
    // real markdownItInstance directly. "\," (an invisible thin space) used
    // to render as a bare, visible "," sitting where the space belongs.
    const input = "Body: $\\int x^2\\,dx = C$ end.";
    const prepared = preprocessMarkdown(input);

    // The backslash before the comma must survive as the protected marker,
    // not vanish, and no bare "x^2,dx" (the corrupted shape) should appear.
    expect(prepared).toContain(PROTECTED_ESCAPE_MARKER);
    expect(prepared).not.toContain("x^2,dx");

    // Round-trip through the app's real markdown-it instance, exactly as
    // the render path does, then decode via mathText.ts (as MathText does)
    // and confirm the final rendered text has a real space, not a comma.
    const tokens = markdownItInstance.parse(prepared, {});
    const inline = tokens.find((t) => t.type === "inline");
    const textToken = inline?.children?.find((c) => c.type === "text");
    expect(textToken?.content).toContain(PROTECTED_ESCAPE_MARKER);
    const mathSpan = textToken!.content.match(/\$([^$]+)\$/)![1];
    const finalText = segmentsToPlain(parseSimpleLatex(mathSpan));
    expect(finalText).toBe("∫ x^2 dx = C");
  });

  it("does not protect letter-led LaTeX commands (\\int, \\frac, \\sqrt) — unaffected by CommonMark's escape rule, which only fires on punctuation", () => {
    const input = "Body: $\\int \\frac{1}{2}\\,dx$ end.";
    const prepared = preprocessMarkdown(input);
    expect(prepared).toContain("\\int");
    expect(prepared).toContain("\\frac");
  });

  it("does not touch backslash-punctuation outside a math span", () => {
    const input = "Note: a\\, b (not math) and $x\\,y$ (math)";
    const prepared = preprocessMarkdown(input);
    expect(prepared).toContain("a\\, b");
  });

  it("BUG FIX regression: converts \\(...\\) inline math to $...$ so markdown-it cannot strip the delimiters into raw (\\frac{...})", () => {
    // Reported live: model emits `\(\frac{m}{m}\)`; CommonMark escapes `\(` / `\)`
    // to bare parentheses during inline tokenization, so splitInlineMath never
    // sees a math span and the UI shows literal `(\frac{m}{m})`.
    const input =
      "1. Divide both sides by \\(\\frac{m}{m}\\):\n" +
      "Cancel \\(\\frac{m}{m}\\) (since \\(m \\neq 0\\)) to get \\(1 = 2m\\).\n" +
      "\\(m = \\frac{1}{2}\\)";
    const prepared = preprocessMarkdown(input);
    expect(prepared).toContain("$\\frac{m}{m}$");
    expect(prepared).toContain("$m \\neq 0$");
    expect(prepared).toContain("$m = \\frac{1}{2}$");
    expect(prepared).not.toContain("\\(");
    expect(prepared).not.toContain("\\)");

    const tokens = markdownItInstance.parse(prepared, {});
    const textContents: string[] = [];
    type WalkToken = { type: string; content?: string; children?: WalkToken[] | null };
    const walk = (ts: WalkToken[]) => {
      for (const t of ts) {
        if (t.type === "text" && t.content) textContents.push(t.content);
        if (t.children) walk(t.children);
      }
    };
    walk(tokens as unknown as WalkToken[]);

    const allText = textContents.join("\n");
    const mathParts = textContents.flatMap((c) =>
      splitInlineMath(c).filter((p) => p.type === "math"),
    );
    expect(mathParts.length).toBeGreaterThanOrEqual(3);
    expect(mathParts.some((p) => p.value.includes("\\frac{m}{m}"))).toBe(true);
    // Must not surface the post-escape raw shape with bare parens + \frac.
    expect(allText).not.toMatch(/\(\\frac\{m\}\{m\}\)/);
  });
});

describe("normalizeMarkdownTables", () => {
  it("adds separator row for loose pipe tables", () => {
    const input = `Name | Score
Alice | 95
Bob | 88`;
    const out = normalizeMarkdownTables(input);
    expect(out).toContain("| Name | Score |");
    expect(out).toMatch(/\|\s*---\s*\|/);
  });

  it("unwraps fenced markdown tables", () => {
    const input = "```markdown\nA | B\n1 | 2\n```";
    const out = normalizeMarkdownTables(input);
    expect(out).not.toContain("```");
    expect(out).toContain("| A | B |");
  });

  it("keeps an ASCII table inside a tagged text fence, including borders", () => {
    const input = ["```text", "+---+", "| a |", "+---+", "```"].join("\n");
    const out = normalizeMarkdownTables(input);
    expect(out).toBe(input);
    expect(preprocessMarkdown(input)).toContain("+---+");
    expect(preprocessMarkdown(input)).toContain("```text");
  });

  it("strips divider-only lines between table rows", () => {
    const input = `| Col A | Col B |
---
| one | two |`;
    const out = normalizeMarkdownTables(input);
    expect(out).not.toMatch(/^---$/m);
    expect(out).toContain("| one | two |");
  });

  it("treats spaced divider chars as divider lines (linear check)", () => {
    const input = `| Col A | Col B |
- - - - -
| one | two |`;
    const out = normalizeMarkdownTables(input);
    expect(out).not.toMatch(/^- - - - -$/m);
    expect(out).toContain("| one | two |");
  });

  it("keeps YAML document separators inside a fence", () => {
    const input = "```yaml\n---\nname: deploy\non: push\n---\n```";
    const out = normalizeMarkdownTables(input);
    expect(out).toBe(input);
  });

  it("keeps a bare tilde fence closer", () => {
    const input = "~~~python\nprint('hi')\n~~~";
    const out = normalizeMarkdownTables(input);
    expect(out).toBe(input);
  });

  it("keeps a thematic break surrounded by blank lines", () => {
    const input = "Intro.\n\n---\n\nAfter.";
    const out = normalizeMarkdownTables(input);
    expect(out).toBe(input);
  });

  it("keeps a setext heading underline", () => {
    const input = "My Heading\n===\n\nBody.";
    const out = normalizeMarkdownTables(input);
    expect(out).toBe(input);
  });

  it("preprocessMarkdown does not strip YAML front matter from a fence", () => {
    const input = "```yaml\n---\nname: deploy\non: push\n---\n```";
    const out = preprocessMarkdown(input);
    expect(out).toContain("---");
    expect(out).toContain("name: deploy");
  });

  it("does not turn composer abs-bars $|5|3$ into a GFM table", () => {
    const input = "$|5|3$";
    expect(normalizeMarkdownTables(input)).toBe(input);
    expect(preprocessMarkdown(input)).not.toMatch(/---/);
  });

  it("BUG FIX regression: toStrictPipeRow respects math pipes inside cells", () => {
    const input = `Name | Value
$|x|$ | 5
$|a+b|$ | 10`;
    const out = normalizeMarkdownTables(input);
    expect(out).toContain("| $|x|$ | 5 |");
    expect(out).toContain("| $|a+b|$ | 10 |");
    expect(out).toMatch(/\|\s*---\s*\|/);
  });

  it("BUG FIX regression: separator row count matches columns with math pipes", () => {
    const input = `A | $|x|$ | C
1 | 2 | 3`;
    const out = normalizeMarkdownTables(input);
    const lines = out.split("\n");
    const sep = lines.find((l) => l.match(/^\|.*---.*\|$/));
    expect(sep).toBeTruthy();
    const sepCells = sep!.split("|").filter((c) => c.trim().length > 0);
    expect(sepCells.length).toBe(3);
  });
});

describe("vega retag (linear)", () => {
  it("retags json fences that contain a Vega schema", () => {
    const body = `{
  "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
  "data": { "values": [{"a": 1}] },
  "mark": "bar"
}`;
    const out = preprocessMarkdown("```json\n" + body + "\n```");
    expect(out).toContain("```vega-lite");
    expect(out).toContain("vega.github.io/schema");
  });

  it("wraps bare Vega JSON blocks", () => {
    const body = `{
"$schema": "https://vega.github.io/schema/vega-lite/v5.json",
"mark": "point"
}`;
    const out = preprocessMarkdown("Chart:\n\n" + body + "\n\nDone.");
    expect(out).toContain("```vega-lite");
  });

  it("protects bare _ and * inside $...$ so markdown-it cannot emphasize them", () => {
    const prepared = preprocessMarkdown("See $x_1 * y_2$ and $a_i^2$.");
    expect(prepared).toContain(PROTECTED_MATH_UNDERSCORE_MARKER);
    expect(prepared).toContain(PROTECTED_MATH_STAR_MARKER);
    expect(prepared).not.toMatch(/\$x_1 \* y_2\$/);

    const tokens = markdownItInstance.parse(prepared, {});
    const inline = tokens.find((t) => t.type === "inline");
    const types = (inline?.children ?? []).map((c) => c.type);
    expect(types).not.toContain("em_open");
    expect(types).not.toContain("strong_open");

    const textToken = inline?.children?.find((c) => c.type === "text" && c.content.includes("$"));
    expect(textToken?.content).toContain(PROTECTED_MATH_UNDERSCORE_MARKER);
    const spans = [...(textToken?.content.matchAll(/\$([^$]+)\$/g) ?? [])].map((m) => m[1]);
    expect(segmentsToPlain(parseSimpleLatex(spans[0]!))).toBe("x_1 * y_2");
    expect(segmentsToPlain(parseSimpleLatex(spans[1]!))).toBe("a_i^2");
  });
});

describe("isPipeTable", () => {
  it("returns true for valid pipe tables", () => {
    expect(
      isPipeTable(`| Name | Value |
| --- | --- |
| foo | 1 |`),
    ).toBe(true);
  });

  it("returns false for plain prose", () => {
    expect(isPipeTable("Just a paragraph with | pipes | inline.")).toBe(false);
  });
});

describe("GFM table parsing (markdownItInstance)", () => {
  it("BUG FIX regression: markdownItInstance parses GFM tables (tables: true)", () => {
    const src = `| Name | Value |
| --- | --- |
| foo | 1 |`;
    const tokens = markdownItInstance.parse(src, {});
    const types = tokens.map((t) => t.type);
    expect(types).toContain("table_open");
    expect(types).toContain("thead_open");
    expect(types).toContain("tr_open");
    expect(types).toContain("th_open");
    expect(types).toContain("tbody_open");
    expect(types).toContain("td_open");
  });

  it("BUG FIX regression: markdownItInstance parses loose pipe tables after preprocessing", () => {
    const raw = `Name | Value
foo | 1`;
    const prepared = preprocessMarkdown(raw);
    const tokens = markdownItInstance.parse(prepared, {});
    const types = tokens.map((t) => t.type);
    expect(types).toContain("table_open");
  });
});

describe("fenced code stays opaque to math/table repair", () => {
  it("does not turn $$ inside a Python string into a math fence", () => {
    const input = '```python\ns = "$$x$$"\nprint(s)\n```';
    const out = preprocessMarkdown(input);
    expect(out).toContain('s = "$$x$$"');
    expect(out).not.toMatch(/```math/);
    expect(out).toContain("```python");
  });

  it("does not split a GFM table out of a Python triple-quoted string", () => {
    const input = [
      "```python",
      'doc = """',
      "| A | B |",
      "| --- | --- |",
      "| 1 | 2 |",
      '"""',
      "print(doc)",
      "```",
    ].join("\n");
    const out = preprocessMarkdown(input);
    expect(out).toContain('doc = """');
    expect(out).toContain("| A | B |");
    expect(out).toContain("| --- | --- |");
    expect(out).toContain("```python");
    expect(out).toContain("print(doc)");
  });

  it("renders an escaped currency dollar as a dollar sign", () => {
    const plain = (src: string) => splitInlineMath(preprocessMarkdown(src)).map((part) => (
      part.type === "math" ? segmentsToPlain(parseSimpleLatex(part.value)) : part.value
    )).join("");
    const weekly = String.raw`$\$43 \text{ per hour} \times 40 \text{ hours} = \$1{,}720 \text{ per week}$`;
    expect(preprocessMarkdown(weekly)).not.toContain("```math");
    expect(plain(weekly)).toBe("$43 per hour × 40 hours = $1,720 per week");
    expect(plain(String.raw`$\$1,505$`)).toBe("$1,505");
    expect(plain(String.raw`$1,720 \times 2 = \mathbf{\$3,440}$`)).toBe("1,720 × 2 = $3,440");
  });

  it("still converts $$ display math in prose", () => {
    const out = preprocessMarkdown("See\n\n$$x^2$$\n\nDone.");
    expect(out).toContain("```math");
    expect(out).toContain("x^2");
  });
});
