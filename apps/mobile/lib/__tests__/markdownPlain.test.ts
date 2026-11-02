import * as markdownPlain from "@/lib/markdown/plain";
import {
  markdownToCopyText,
  markdownToSpeechText,
} from "@/lib/markdown/plain";
import { markdownToStructuredPrintHtml } from "@/features/chat/model/printDocument";
import { readVendorLibrary } from "@/lib/vendorAssets";

// KaTeX's stylesheet is a vendored asset the print path reads from disk.
const MOCK_KATEX_CSS = ".katex{font:normal 1.21em KaTeX_Main}";
jest.mock("@/lib/vendorAssets", () => ({
  readVendorLibrary: jest.fn(async () => MOCK_KATEX_CSS),
}));

describe("markdownPlain", () => {
  it("strips fences and markdown emphasis for TTS", () => {
    const plain = markdownToSpeechText("# Title\n\n**Bold** and `code`\n\n```json\n{}\n```");
    expect(plain).toContain("Title");
    expect(plain).toContain("Bold");
    expect(plain).not.toContain("```");
    expect(plain).toContain("{}");
  });

  it("does not re-export print helpers that pull KaTeX", () => {
    expect(Object.keys(markdownPlain).sort()).toEqual(
      [
        "fenceToCopyText",
        "mapFenceRegions",
        "markdownToCopyText",
        "markdownToSpeechText",
        "spokenText",
      ].sort(),
    );
  });

  it("does not load printDocument", () => {
    jest.resetModules();
    jest.doMock("@/features/chat/model/printDocument", () => {
      throw new Error("markdownPlain must not import printDocument");
    });
    expect(() => require("@/lib/markdown/plain")).not.toThrow();
    jest.dontMock("@/features/chat/model/printDocument");
  });

  it("keeps the visible final answer and flattens pipe tables", () => {
    const src =
      "Intro\n\n```answer\n42\n```\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n";
    const copy = markdownToCopyText(src);
    const spoken = markdownToSpeechText(src);
    expect(copy).toContain("Intro");
    expect(copy).toContain("42");
    expect(copy).not.toContain("```");
    expect(copy).toContain("A — B");
    expect(copy).toContain("1 — 2");
    expect(spoken).toContain("42");
  });

  it("keeps code syntax, identifiers, and currency on Copy", () => {
    const src = [
      "user_id = {\"count\": 2}",
      "",
      "```python",
      "print(user_id * 2)",
      "```",
      "",
      "Costs $5 or $10.",
    ].join("\n");
    const copy = markdownToCopyText(src);
    expect(copy).toContain('user_id = {"count": 2}');
    expect(copy).toContain("print(user_id * 2)");
    expect(copy).toContain("Costs $5 or $10.");
    expect(copy).not.toContain("userid");
  });

  it("copies inline math as readable text, not raw $ / \\frac", () => {
    const copy = markdownToCopyText("The answer is $\\frac{2}{3}$.");
    expect(copy).toContain("2/3");
    expect(copy).not.toContain("$");
    expect(copy).not.toContain("\\frac");
  });

  it("speaks a superscripted fraction and a radical of a fraction", () => {
    const fraction = markdownToSpeechText("The answer is $\\frac{x^{2}}{4}$.");
    expect(fraction).toBe("The answer is x squared over 4.");
    expect(fraction).not.toContain("\\frac");
    expect(fraction).not.toContain("fracx");

    const radical = markdownToSpeechText("$$\\sqrt{\\frac{a}{b}}$$");
    expect(radical).toBe("the square root of a over b");
    expect(radical).not.toContain("\\");
    expect(radical).not.toContain("frac");
  });

  it("does not strip a numeric-only answer fence", () => {
    expect(markdownToCopyText("```answer\n42\n```")).toBe("42");
    expect(markdownToSpeechText("```answer\n42\n```")).toBe("42");
  });

  it("labels a chart for speech and omits chart JSON from Copy", () => {
    const src = 'Rainfall\n\n```chart\n{"mark":"bar"}\n```\n';
    expect(markdownToCopyText(src)).toBe("Rainfall");
    expect(markdownToSpeechText(src)).toContain("Rainfall");
    expect(markdownToSpeechText(src)).toContain("a chart");
    expect(markdownToCopyText(src)).not.toContain("mark");
  });

  it("never copies or speaks reminder control JSON", () => {
    const src = 'Done.\n\n```reminder\n{"title":"Pay rent"}\n```\n';
    expect(markdownToCopyText(src)).toBe("Done.");
    expect(markdownToSpeechText(src)).toBe("Done.");
    expect(markdownToCopyText(src)).not.toContain("Pay rent");
  });

  it("reads a teaching picture aloud and copies its sentence", () => {
    const src =
      '```arithmetic\n{"type":"ten_frame","answer":"12","speech":"7 plus 3 makes 10, and 2 remain."}\n```\n';
    expect(markdownToSpeechText(src)).toContain("7 plus 3 makes 10");
    expect(markdownToCopyText(src)).toContain("7 plus 3 makes 10");
    expect(markdownToCopyText(src)).not.toContain("ten_frame");
  });

  it("labels diagrams for speech and omits smiles JSON from Copy", () => {
    const src = 'Water\n\n```smiles\nO\n```\n';
    expect(markdownToCopyText(src)).toBe("Water");
    expect(markdownToSpeechText(src)).toContain("a diagram");
  });

  it("preserves ordered markers and nested indentation when copying", () => {
    const src = [
      "1. Open Settings",
      "2. Choose Privacy",
      "   - Disable analytics",
      "   - Keep crash reports",
    ].join("\n");
    const copy = markdownToCopyText(src);
    expect(copy).toContain("1. Open Settings");
    expect(copy).toContain("2. Choose Privacy");
    expect(copy).toContain("   • Disable analytics");
    expect(copy).toContain("   • Keep crash reports");
  });
});

describe("markdownToStructuredPrintHtml", () => {
  it("styles the document with KaTeX's vendored stylesheet", async () => {
    const html = await markdownToStructuredPrintHtml("Note", "Solve $x^2=4$.");
    expect(readVendorLibrary).toHaveBeenCalledWith("katexCss");
    const head = html.slice(0, html.indexOf("</head>"));
    expect(head).toContain(`<style>${MOCK_KATEX_CSS}`);
  });

  it("still exports, unstyled math and all, when the stylesheet cannot be read", async () => {
    jest.mocked(readVendorLibrary).mockRejectedValueOnce(new Error("asset missing"));
    const html = await markdownToStructuredPrintHtml("Note", "Solve $x^2=4$.");
    expect(html).not.toContain(MOCK_KATEX_CSS);
    expect(html).toContain("katex");
    expect(html).toContain("<h1>Note</h1>");
  });

  it("keeps code fences as pre blocks", async () => {
    const html = await markdownToStructuredPrintHtml("Note", "Intro\n\n```js\nconst x = 1;\n```\n\nDone");
    expect(html).toContain("<pre><code");
    expect(html).toContain("const x = 1;");
    expect(html).toContain("<p>Intro</p>");
    expect(html).toContain("<p>Done</p>");
  });

  it("renders headings and lists", async () => {
    const html = await markdownToStructuredPrintHtml(
      "Guide",
      "## Section\n\n- one\n- two\n\n1. first\n2. second",
    );
    expect(html).toContain("<h3>Section</h3>");
    expect(html).toContain("<ul>");
    expect(html).toContain("<li>one</li>");
    expect(html).toContain("<ol>");
    expect(html).toContain("<li>first</li>");
  });

  it("renders math fences with KaTeX instead of raw pre blocks", async () => {
    const html = await markdownToStructuredPrintHtml(
      "Math",
      "Answer:\n\n```math\nx^2 + 1 = 0\n```\n",
    );
    expect(html).toContain("katex");
    expect(html).toContain("math-block");
    expect(html).not.toContain("<pre><code class=\"language-math\"");
  });

  it("renders inline $math$ with KaTeX", async () => {
    const html = await markdownToStructuredPrintHtml("Inline", "Solve $x^2=4$ next.");
    expect(html).toContain("katex");
    expect(html).toContain("math-inline");
    expect(html).not.toContain("$x^2=4$");
  });

  it("converts $$ block math via preprocess before printing", async () => {
    const html = await markdownToStructuredPrintHtml("Display", "See\n\n$$\\frac{a}{b}$$\n");
    expect(html).toContain("katex");
    expect(html).toContain("math-block");
  });

  it("keeps hyphenated fence langs and prints GFM tables plus links", async () => {
    const html = await markdownToStructuredPrintHtml(
      "Note",
      "See [docs](https://example.com).\n\n```vega-lite\n{}\n```\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n",
    );
    expect(html).toContain('class="language-vega-lite"');
    expect(html).toContain('<a href="https://example.com">docs</a>');
    expect(html).toContain("<table>");
    expect(html).toContain("<th>A</th>");
    expect(html).toContain("<td>1</td>");
  });
});

describe("markdownPlain chemistry", () => {
  const chemistryAnswer = "```answer\nnotation: chemistry\nM(H₂O) = 18.02 g/mol\n```";

  it("copies and speaks a chemistry answer without its notation header", () => {
    expect(markdownToCopyText(chemistryAnswer)).toBe("M(H₂O) = 18.02 g/mol");
    expect(markdownToSpeechText(chemistryAnswer)).toBe("M(H₂O) = 18.02 g/mol");
  });

  it("does not copy the JSON of a drawn scene, and names it when read aloud", () => {
    const scene = '```chem_scene\n{"kind":"cell","title":"Galvanic cell"}\n```';
    expect(markdownToCopyText(scene)).not.toContain("{");
    expect(markdownToSpeechText(scene)).not.toContain("{");
  });
});

describe("lesson cards as text", () => {
  const md = [
    "Given:",
    "",
    "```array",
    '{"name":"nums","values":[3,2,4]}',
    "```",
    "",
    "```quiz",
    '{"question":"What does it return?","options":["[0, 1]","[1, 2]"],"answer":1}',
    "```",
  ].join("\n");

  it("copies the list and the question with lettered options", () => {
    const text = markdownToCopyText(md);
    expect(text).toContain("nums = [3, 2, 4]");
    expect(text).toContain("What does it return?\nA) [0, 1]\nB) [1, 2]");
  });

  it("reads a card written as plain text as the text it shows, and half-written JSON as nothing", () => {
    for (const lang of ["clarify", "quiz", "array"]) {
      const plain = `Intro\n\n\`\`\`${lang}\nWhich region do you mean?\n\`\`\``;
      expect(markdownToCopyText(plain)).toBe("Intro\n\nWhich region do you mean?");
      expect(markdownToSpeechText(plain)).toContain("Which region do you mean?");
      expect(markdownToCopyText(`Intro\n\n\`\`\`${lang}\n{"questions":[{"id"\n\`\`\``)).toBe("Intro");
    }
  });

  it("copies a quiz with broken JSON as its card shows it, and never a quiz's answer", () => {
    const broken = '```quiz\n{"question": "Pick", "options": ["a", "b",], "answer": 1, "explanation": "secret"}\n```';
    expect(markdownToCopyText(broken)).toBe("Pick\nA) a\nB) b");
    const keyed = '```quiz\nHere you go:\n{"question":"Q","options":["a","b"],"answer":1,"explanation":"secret"}\n```';
    for (const md of [keyed, broken]) {
      expect(markdownToCopyText(md)).not.toContain("secret");
      expect(markdownToSpeechText(md)).not.toContain("secret");
    }
  });
});

it("leaves a photo request out of copy and speech", () => {
  const md = "```photo\nEthiopia location map\n```\n\nEthiopia is in East Africa.";
  expect(markdownToCopyText(md).trim()).toBe("Ethiopia is in East Africa.");
  expect(markdownToSpeechText(md)).not.toContain("location map");
});
