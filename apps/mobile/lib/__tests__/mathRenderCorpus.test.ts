/**
 * Reproduction corpus: assistant-shaped strings through preprocess → inline
 * split → native parse. A leftover `\\command` after this pipeline is what
 * painted as raw LaTeX in chat.
 */
import { markdownItInstance } from "@/lib/markdown/parser";
import { preprocessMarkdown, splitInlineMath } from "@/lib/markdown/preprocess";
import { readableLatexFallback, segmentsToPlain, parseSimpleLatex } from "@/lib/math/text";
import { findStableMarkdownPrefixLen, preprocessMarkdownForStream } from "@/lib/markdown/preprocessStream";

const BACKSLASH_CMD = /\\[a-zA-Z]+/;

function mathSpansAfterPreprocess(raw: string): string[] {
  const prepared = preprocessMarkdown(raw);
  const tokens = markdownItInstance.parse(prepared, {});
  const texts: string[] = [];
  const walk = (ts: Array<{ type: string; content?: string; children?: unknown[] | null }>) => {
    for (const t of ts) {
      if (t.type === "text" && t.content) texts.push(t.content);
      if (t.children) walk(t.children as typeof ts);
    }
  };
  walk(tokens);
  return texts.flatMap((c) => splitInlineMath(c).filter((p) => p.type === "math").map((p) => p.value));
}

describe("math render corpus (preprocess → typeset, never raw \\cmd)", () => {
  it("inline $x^2$", () => {
    const spans = mathSpansAfterPreprocess("Let $x^2$ be the square.");
    expect(spans).toEqual(["x^2"]);
    expect(readableLatexFallback(spans[0])).toBe("x^2");
    expect(readableLatexFallback(spans[0])).not.toMatch(BACKSLASH_CMD);
  });

  it("reads the equilibrium arrows chemistry writes between species", () => {
    const equilibrium = readableLatexFallback("N_2 + 3H_2 \\rightleftharpoons 2NH_3");
    expect(equilibrium).toContain("⇌");
    expect(equilibrium).not.toMatch(BACKSLASH_CMD);
    expect(equilibrium).not.toContain("rightleftharpoons");
    expect(readableLatexFallback("A \\leftrightharpoons B")).toContain("⇋");
    expect(readableLatexFallback("A \\leftrightarrow B")).toContain("↔");
  });

  it("converts $$ display math into a ```math fence", () => {
    const out = preprocessMarkdown("The area is $$\\pi r^2$$ for a circle.");
    expect(out).toContain("```math");
    expect(out).toContain("\\pi r^2");
    expect(out).not.toContain("$$");
  });

  it("converts \\(...\\) to $...$ so markdown-it cannot strip delimiters", () => {
    const out = preprocessMarkdown("Cancel \\(\\frac{m}{m}\\) since \\(m \\neq 0\\).");
    expect(out).toContain("$\\frac{m}{m}$");
    expect(out).not.toContain("\\(");
    const spans = mathSpansAfterPreprocess("Cancel \\(\\frac{m}{m}\\) since \\(m \\neq 0\\).");
    expect(spans.some((s) => s.includes("\\frac{m}{m}"))).toBe(true);
    expect(readableLatexFallback("\\frac{m}{m}")).toBe("m/m");
  });

  it("converts \\[...\\] display math into a ```math fence", () => {
    const out = preprocessMarkdown("Solve:\n\n\\[ x = \\pm \\sqrt{4} \\]\n");
    expect(out).toContain("```math");
    expect(out).toContain("x = \\pm \\sqrt{4}");
    expect(out).not.toContain("\\[");
  });

  it("keeps a ```math fence as a fence (not inline $)", () => {
    const out = preprocessMarkdown("```math\n\\frac{1}{2}\n```");
    expect(out).toContain("```math");
    expect(readableLatexFallback("\\frac{1}{2}")).toBe("1/2");
  });

  it("numbered steps with inline math still produce math spans", () => {
    const input = "1. Divide by $m$: $1 = 2m$.\n2. So $m = \\frac{1}{2}$.";
    const spans = mathSpansAfterPreprocess(input);
    expect(spans.length).toBeGreaterThanOrEqual(3);
    expect(spans).toContain("m = \\frac{1}{2}");
  });

  it("list items with inline math still produce math spans", () => {
    const spans = mathSpansAfterPreprocess("- Let $x^2 + 1$ be positive.");
    expect(spans).toContain("x^2 + 1");
  });

  it("BUG FIX regression: dollar-wrapped negative equation keeps its sign and renders as math", () => {
    const input = String.raw`1. Isolate x
$- 1\cdot x = 2 - 3^{\frac{2}{3}}$`;
    const prepared = preprocessMarkdown(input);
    expect(prepared).toContain(String.raw`$- 1\cdot x = 2 - 3^{\frac{2}{3}}$`);
    expect(markdownItInstance.parse(prepared, {}).some((token) => token.type === "bullet_list_open")).toBe(false);
    const spans = mathSpansAfterPreprocess(input);
    expect(spans.some((s) => s.includes("\\cdot") && s.includes("\\frac{2}{3}"))).toBe(true);
    const prose = (() => {
      const tokens = markdownItInstance.parse(prepared, {});
      const texts: string[] = [];
      const walk = (ts: Array<{ type: string; content?: string; children?: unknown[] | null }>) => {
        for (const t of ts) {
          if (t.type === "text" && t.content) texts.push(t.content);
          if (t.children) walk(t.children as typeof ts);
        }
      };
      walk(tokens);
      return texts
        .flatMap((c) => splitInlineMath(c).filter((p) => p.type === "text").map((p) => p.value))
        .join("");
    })();
    expect(prose).not.toMatch(/\\cdot/);
    expect(prose).not.toMatch(/\\frac/);
  });

  it("table cells with inline math still produce math spans", () => {
    const input = "| Qty | Formula |\n| --- | --- |\n| area | $\\pi r^2$ |";
    const spans = mathSpansAfterPreprocess(input);
    expect(spans.some((s) => s.includes("\\pi r^2") || s.includes("pi r^2"))).toBe(true);
  });

  it("aligned / matrix / cases degrade without leftover backslash commands", () => {
    const aligned = String.raw`\begin{aligned} a &= b \\ c &= d \end{aligned}`;
    const matrix = String.raw`\begin{pmatrix} 1 & 0 \\ 0 & 1 \end{pmatrix}`;
    const cases = String.raw`\begin{cases} x & x \ge 0 \\ -x & x < 0 \end{cases}`;
    for (const src of [aligned, matrix, cases]) {
      const plain = segmentsToPlain(parseSimpleLatex(src));
      expect(plain).not.toMatch(BACKSLASH_CMD);
      expect(plain).not.toContain("\\begin");
    }
  });

  it("mixed prose + math on one line", () => {
    const spans = mathSpansAfterPreprocess("If $a > 0$ then $b = a^2$ holds.");
    expect(spans).toEqual(["a > 0", "b = a^2"]);
  });

  it("math adjacent to a code fence is not swallowed by the fence", () => {
    const input = "See $x^2$ then\n```\ncode\n```\nand $y^2$.";
    const spans = mathSpansAfterPreprocess(input);
    expect(spans).toContain("x^2");
    expect(spans).toContain("y^2");
  });

  it("an unclosed $$ mid-stream stays out of the stable prefix", () => {
    const raw = "Before.\n\n$$\n\\frac{1}{2}\n";
    expect(findStableMarkdownPrefixLen(raw)).toBeLessThan(raw.length);
    const { prepared } = preprocessMarkdownForStream(raw, null);
    // Unstable tail is still raw; it must not be turned into a half fence.
    expect(prepared).toContain("$$");
  });
});

describe("real-world inline math corpus (full pipeline, never raw \\cmd)", () => {
  // Each entry is a sentence with one inline `$...$` span. After preprocess →
  // markdown-it → splitInlineMath → native parse, the rendered plain text
  // must contain NO leftover `\command` (the "raw LaTeX on screen" bug) and,
  // where noted, must contain the expected glyph. These are the constructs
  // that previously leaked and the common homework forms most likely to.
  const corpus: Array<{ name: string; input: string; expect?: string }> = [
    { name: "sized delimiters", input: "Group $\\bigl(x+1\\bigr)$ first." , expect: "(x+1)" },
    { name: "sized brackets", input: "Use $\\Bigl[x+1\\Bigr]$ now." , expect: "[x+1]" },
    { name: "big cup", input: "The union $\\bigcup_{i=1}^{n} A_i$ is finite.", expect: "∪" },
    { name: "contour integral", input: "By $\\oint_C F\\,dr$ we get 0.", expect: "∮" },
    { name: "double integral", input: "So $\\iint_D f\\,dA$ works.", expect: "∬" },
    { name: "direct sum", input: "Note $\\oplus A$ is direct.", expect: "⊕" },
    { name: "overset equals", input: "Then $a \\overset{\\text{def}}{=} b$.", expect: "=" },
    { name: "stackrel", input: "And $x \\stackrel{!}{=} y$ here.", expect: "=" },
    { name: "color unwrap", input: "Red $\\color{red}{x+1}$ shows.", expect: "x+1" },
    { name: "textcolor unwrap", input: "Blue $\\textcolor{blue}{y}$ too.", expect: "y" },
    { name: "therefore", input: "So $\\therefore x = 1$.", expect: "∴" },
    { name: "because", input: "Since $\\because y = 0$.", expect: "∵" },
    { name: "bmod", input: "Compute $a \\bmod b$ now.", expect: "mod" },
    { name: "pmod", input: "Same $x \\pmod{7}$ here.", expect: "(mod 7)" },
    { name: "smallmatrix", input: "Matrix $\\begin{smallmatrix}1&2\\\\3&4\\end{smallmatrix}$.", expect: "1, 2; 3, 4" },
    { name: "Bmatrix", input: "Set $\\begin{Bmatrix}1&2\\\\3&4\\end{Bmatrix}$.", expect: "{1, 2; 3, 4}" },
    { name: "array with colspec", input: "Tab $\\begin{array}{cc}1&2\\\\3&4\\end{array}$.", expect: "1 2;  3 4" },
    { name: "substack", input: "Sum $\\sum_{\\substack{i=1\\\\i\\ne 2}}^{n} i$." , expect: ";" },
    { name: "quadratic", input: "Roots $x = \\frac{-b \\pm \\sqrt{b^2-4ac}}{2a}$." },
    { name: "sum identity", input: "Know $\\sum_{i=1}^{n} i = \\frac{n(n+1)}{2}$." },
    { name: "definite integral", input: "So $\\int_0^1 x^2\\,dx = \\frac{1}{3}$." },
    { name: "famous limit", input: "And $\\lim_{x\\to 0} \\frac{\\sin x}{x} = 1$." },
    { name: "reals", input: "On $\\mathbb{R}$ it holds." , expect: "ℝ" },
    { name: "epsilon delta", input: "For $\\forall \\epsilon > 0, \\exists \\delta > 0$." },
    { name: "vector", input: "Let $\\vec{v} = \\langle 1,2,3\\rangle$." },
    { name: "repeating decimal", input: "Note $\\overline{0.714285}$ repeats." },
    { name: "cube root", input: "Since $\\sqrt[3]{8} = 2$." },
    { name: "binom", input: "Use $\\binom{n}{k} = \\frac{n!}{k!(n-k)!}$." },
    { name: "sized parens", input: "Wrap $\\left(\\frac{1}{2}\\right)$." },
    { name: "interval", input: "On $x \\in [0,1]$ only." },
  ];

  for (const { name, input, expect: expected } of corpus) {
    it(name, () => {
      const spans = mathSpansAfterPreprocess(input);
      expect(spans.length).toBeGreaterThanOrEqual(1);
      for (const span of spans) {
        const rendered = readableLatexFallback(span);
        // The core invariant: no leftover `\command` paints as raw LaTeX.
        expect(rendered).not.toMatch(BACKSLASH_CMD);
        expect(rendered).not.toContain("\\begin");
        if (expected) expect(rendered).toContain(expected);
      }
    });
  }
});
