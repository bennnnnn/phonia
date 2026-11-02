import {
  applyImplicitPowerNotation,
  fixImplicitExponents,
  normalizeImplicitMath,
  normalizeImplicitMathInProse,
} from "@/lib/math/normalizeImplicit";

describe("normalizeImplicitMath", () => {
  it("preserves the exact S04 explicit mean formula without wrapping its intervening text", () => {
    const source = String.raw`Mean (\(\mu\)) = \( \frac{1+2+3}{3} = 2 \),`;
    expect(normalizeImplicitMath(source)).toBe(source);
    expect(normalizeImplicitMath(`  - ${source}`)).toBe(`  - ${source}`);
    expect(normalizeImplicitMath(String.raw`x = \(2\)`)).toBe(String.raw`x = \(2\)`);
  });

  it("still normalizes complete equation lines beside an explicit math span", () => {
    const middle = String.raw`Mean (\(\mu\)) = \(2\)`;
    expect(normalizeImplicitMath(`x^2 = 4\n${middle}\nz = 5`)).toBe(`$x^2 = 4$\n${middle}\n$z = 5$`);
    expect(normalizeImplicitMath(String.raw`Use \(x\), then \sqrt{2}.`)).toBe(String.raw`Use \(x\), then $\sqrt{2}$.`);
  });

  it("wraps parenthesized algebra from model output", () => {
    const input = "Given equation: ( x^2 + 2 = 6 )\nStep 2: ( x = \\pm \\sqrt{4} )";
    const out = normalizeImplicitMathInProse(input);
    expect(out).toContain("$x^2 + 2 = 6$");
    expect(out).toContain("$x = \\pm \\sqrt{4}$");
  });

  it("BUG FIX regression: never re-wraps parentheticals INSIDE already-delimited $...$ inline math", () => {
    // Reported live on a quadratic-formula verification: the line
    //   $(-2 + \sqrt{3})^2 + 4(-2 + \sqrt{3}) + 1 = ... = 0$ ✓
    // was already wrapped in $...$, but MATH_IN_PARENS_RE re-wrapped each
    // (-2 + \sqrt{3}) in its own $...$, producing $$ and shattering the $
    // pairing across the whole message — \sqrt{3} then rendered as raw text
    // and adjacent "For x = ..." prose got glued into "Forx = ...". The
    // outer $...$ must be preserved verbatim.
    const line = "  $(-2 + \\sqrt{3})^2 + 4(-2 + \\sqrt{3}) + 1 = (4 - 4\\sqrt{3} + 3) + (-8 + 4\\sqrt{3}) + 1 = 0$ ✓";
    const out = normalizeImplicitMathInProse(line);
    expect(out).toBe(line);
    // No nested/extra $...$ injected inside the outer span, no $$.
    expect(out).not.toContain("$$");
    expect(out.match(/\$/g)?.length).toBe(2);
  });

  it("wraps a bare letter-digit identifier without inventing an exponent", () => {
    const input = "Equation: x2+2=6\nx2=6-2\nx2=4";
    const out = normalizeImplicitMathInProse(input);
    expect(out).toContain("$x2+2=6$");
    expect(out).toContain("$x2=6-2$");
    expect(out).toContain("$x2=4$");
    expect(out).not.toContain("x^2");
  });

  it("does not turn adjacent digits into exponents", () => {
    const input = "For x=2: 22+2=4+2=6 ✓";
    const out = normalizeImplicitMathInProse(input);
    expect(out).toContain("$22+2=4+2=6$");
    expect(out).not.toContain("2^2");
  });

  it("BUG FIX regression: recognizes verification lines with any single-letter variable and 'Let' phrasing, not just x/y/z + 'For'", () => {
    // Reported live: "Let c = 3: 3^2 + 3^2 = 18" used variable "c" (not
    // x/y/z) and "Let" (not "For") — the old regex was hardcoded to
    // [xyz] + "For " only, so this line never got its math wrapped.
    const input = "Let c=3: 3^2+3^2=18 ✓";
    const out = normalizeImplicitMathInProse(input);
    expect(out).toContain("$3^2+3^2=18$");
  });

  it("leaves normal prose alone", () => {
    const input = "Both solutions check out! (see step 2)";
    expect(normalizeImplicitMathInProse(input)).toBe(input);
  });

  it("unwraps dollar-wrapped bullet lines from model output", () => {
    const input = "$- Base = 8 cm$\n$- Height = 5 cm$";
    const out = normalizeImplicitMathInProse(input);
    expect(out).toBe("- Base = 8 cm\n- Height = 5 cm");
  });

  it("BUG FIX regression: keeps leading-negative math inside its delimiters", () => {
    // Reported live: the verified step `$- x = -2$` rendered as a blue list
    // bullet followed by the false equation `x = -2`. Explicit math syntax is
    // authoritative; a leading minus inside it is a unary sign, not Markdown.
    expect(normalizeImplicitMathInProse("$- x = -2$")).toBe("$- x = -2$");

    const input = String.raw`$- 1\cdot x = 2 - 3^{\frac{2}{3}}$`;
    const out = normalizeImplicitMathInProse(input);
    expect(out).toBe(input);
    expect(out).not.toMatch(/^- /);
  });

  it("keeps non-minus bullet markers outside a wrapped equation", () => {
    expect(normalizeImplicitMathInProse("$* x = 2$")).toBe("* $x = 2$");
    expect(normalizeImplicitMathInProse("$• x = 2$")).toBe("• $x = 2$");
  });

  it("BUG FIX regression: wraps a bare list-item equation that contains \\cdot / \\frac", () => {
    const input = String.raw`- 1\cdot x = 2 - 3^{\frac{2}{3}}`;
    const out = normalizeImplicitMathInProse(input);
    expect(out).toBe(String.raw`- $1\cdot x = 2 - 3^{\frac{2}{3}}$`);
  });

  it("BUG FIX regression: wraps \\sqrt[3]{9} including the index, not just \\sqrt", () => {
    const input = String.raw`Since \sqrt[3]{9} equals the root.`;
    const out = normalizeImplicitMathInProse(input);
    expect(out).toContain(String.raw`$\sqrt[3]{9}$`);
    expect(out).not.toContain(String.raw`$\sqrt$`);
  });

  it("BUG FIX regression: wraps 3^{\\frac{2}{3}} as one math span, not shattered commands", () => {
    const input = String.raw`Since the root is 3^{\frac{2}{3}}, isolate.`;
    const out = normalizeImplicitMathInProse(input);
    expect(out).toContain(String.raw`$3^{\frac{2}{3}}$`);
    expect(out).not.toContain(String.raw`$3^{$`);
    expect(out).not.toContain(String.raw`$\frac{2}{3}$}`);
  });

  it("BUG FIX regression: does not swallow a bold-prefixed line into math delimiters", () => {
    // BARE_EQUATION_RE's char class allows `*` for multiplication, which also
    // matches markdown's `**bold**` markers — a line like "**Solve** 2^x + 5 = 7"
    // used to get misread as a bare equation and wrapped whole in `$...$`,
    // which renders as raw source text (not parsed markdown), showing the
    // literal `**` asterisks instead of bold.
    const input = "**Solve** 2^x + 5 = 7";
    expect(normalizeImplicitMathInProse(input)).toBe(input);
  });

  it("BUG FIX regression: So + equation stays prose + math, not 'Sor'", () => {
    const out = normalizeImplicitMathInProse("So r + 1/r = 17/4");
    expect(out.startsWith("So ")).toBe(true);
    expect(out).toContain("$r + 1/r = 17/4$");
    expect(out).not.toMatch(/^\$So /);
  });

  it("BUG FIX regression: wraps a bare LaTeX command embedded mid-sentence, not just whole-line equations", () => {
    // Reported live: "...or simplifying\\frac{8!}{6!}? 😄" rendered the raw
    // backslash command since it has no $...$ wrap at all and isn't a
    // whole-line equation for looksLikeBareEquation to key off — only the
    // command span itself (not the surrounding prose) must be wrapped.
    const input = "Want one with a twist? e.g., 0!, 10!, or simplifying\\frac{8!}{6!}? 😄";
    const out = normalizeImplicitMathInProse(input);
    expect(out).toBe(
      "Want one with a twist? e.g., 0!, 10!, or simplifying$\\frac{8!}{6!}$? 😄",
    );
  });

  it.each([
    [String.raw`Answer: 26.3\,\mathrm{N·m}`, String.raw`Answer: $26.3\,\mathrm{N·m}$`],
    [String.raw`a speed of 3\;\mathrm{m/s} today`, String.raw`a speed of $3\;\mathrm{m/s}$ today`],
    [String.raw`Answer: 26.3\,N·m`, "Answer: 26.3 N·m"],
  ])("keeps a spacing command out of prose, where it shows as a comma: %s", (input, expected) => {
    // A follow-up reply wrote its answer bare, and the screen read "26.3,N·m".
    expect(normalizeImplicitMath(input)).toBe(expected);
  });

  it.each([
    String.raw`Great\! It works.`,
    "Type `5\\,N` here",
  ])("leaves an escaped mark and code as written: %s", (input) => {
    expect(normalizeImplicitMath(input)).toBe(input);
  });

  it("does not re-wrap inside existing $...$ but still wraps bare commands outside them", () => {
    // A line that already has one `$...$` used to bail out of command wrapping
    // entirely, leaving a leftover `\neq` / `\frac` raw on the same line
    // (e.g. after Cancel $\frac{m}{m}$ (since m \neq 0)). Only non-$ segments
    // should get wrapped.
    const input = "We have $x = 2$ and also mention \\frac{1}{2} here.";
    expect(normalizeImplicitMathInProse(input)).toBe(
      "We have $x = 2$ and also mention $\\frac{1}{2}$ here.",
    );
  });

  it("BUG FIX regression: wraps (since m \\neq 0) — LaTeX cmd letters are not English prose", () => {
    // "neq" inside `\neq` used to count as a 3-letter word alongside "since",
    // so looksLikeProseParenthetical rejected the whole paren and left `\neq`
    // raw on screen.
    const input = "Cancel (\\frac{m}{m}) (since m \\neq 0) to get (1 = 2m).";
    const out = normalizeImplicitMathInProse(input);
    expect(out).toContain("$\\frac{m}{m}$");
    // Whole parenthetical wraps (including the leading "since") so `\neq`
    // lands inside `$...$` and renders — not left as raw backslash text.
    expect(out).toContain("$since m \\neq 0$");
    expect(out).toContain("$1 = 2m$");
    expect(out).not.toMatch(/\(since m \\neq 0\)/);
  });

  it("BUG FIX regression: wraps a nested-frac parenthetical as one math span", () => {
    // Multiple `\frac` letter-runs used to trip the prose heuristic so the
    // outer `(...)` never wrapped and wrapInlineLatexCommands shredded it.
    const input =
      "(\\frac{\\frac{1}{2}}{\\frac{1}{2}} = \\frac{1}{2} \\div \\frac{1}{2} = 1)";
    const out = normalizeImplicitMathInProse(input);
    expect(out).toBe(
      "$\\frac{\\frac{1}{2}}{\\frac{1}{2}} = \\frac{1}{2} \\div \\frac{1}{2} = 1$",
    );
  });

  it("still wraps a genuine bare equation line with no markdown emphasis", () => {
    const input = "2^x = 7 - 5 = 2";
    expect(normalizeImplicitMathInProse(input)).toBe("$2^x = 7 - 5 = 2$");
  });

  it("skips fenced code blocks", () => {
    const { normalizeImplicitMath } = require("@/lib/math/normalizeImplicit");
    const input = "```python\n( x = 1 )\n```\nx2=4";
    const out = normalizeImplicitMath(input);
    expect(out).toContain("```python\n( x = 1 )\n```");
    expect(out).toContain("$x2=4$");
  });

  it("BUG FIX regression: mid-line ```math does not skip wrapping \\frac", () => {
    const input =
      "1. **Divide both sides by 4** to isolate x: ```math\n" +
      String.raw`\frac{4x}{4} = \frac{4}{4}` +
      "\n\n2. **Simplify:**\n\n```math\nx = 1\n```";
    const out = normalizeImplicitMath(input);
    expect(out).toMatch(/\$\\frac\{4x\}/);
  });

  it("BUG FIX regression: does not wrap LaTeX commands inside a \\[...\\] display-math span in $...$", () => {
    // Reported live (screenshots): "x = \\pm \\sqrt{4}" inside \\[...\\]
    // rendered in red. wrapInlineLatexCommands used to treat \\[ ... \\] as
    // plain prose and wrap each bare command (\\pm, \\sqrt{4}) in $...$
    // *before* markdownPreprocess.ts's BLOCK_MATH_BRACKET_RE converts the
    // \\[...\\] span into a ```math fence — leaving embedded, un-stripped $
    // characters in the fence body that KaTeX can't parse as bare LaTeX.
    const { normalizeImplicitMath } = require("@/lib/math/normalizeImplicit");
    const input = "Solve:\n\n\\[ x = \\pm \\sqrt{4} \\]\n\nDone.";
    const out = normalizeImplicitMath(input);
    expect(out).toContain("\\[ x = \\pm \\sqrt{4} \\]");
    expect(out).not.toContain("$\\pm$");
    expect(out).not.toContain("$\\sqrt{4}$");
  });

  it("BUG FIX regression: does not touch a $$...$$ display-math span either", () => {
    const { normalizeImplicitMath } = require("@/lib/math/normalizeImplicit");
    const input = "Solve:\n\n$$ x = \\pm \\sqrt{4} $$\n\nDone.";
    const out = normalizeImplicitMath(input);
    expect(out).toContain("$$ x = \\pm \\sqrt{4} $$");
  });

  it("BUG FIX regression: does not re-wrap parentheticals that already contain $...$", () => {
    // Live screenshot: "(excluded values: $x \\neq -3, 2$)" was wrapped as
    // `$excluded values: $x \\neq -3, 2$$`, inventing a trailing `$$` that
    // stole the next display-math opener — equations showed as raw LaTeX
    // and the Wait—prose paragraph was sucked into a MathBlock fence.
    const input =
      "- Domain restrictions (excluded values: $x \\neq -3, 2$)\n" +
      "- Cross-multiplication";
    expect(normalizeImplicitMathInProse(input)).toBe(input);
  });

  it("BUG FIX regression: does not wrap English parentheticals that mention math mid-sentence", () => {
    const input =
      "a hidden quadratic (e.g., in disguise like $x^4$) ✅";
    expect(normalizeImplicitMathInProse(input)).toBe(input);
  });

  it("still wraps a pure algebra parenthetical with an equals", () => {
    const input = "Solve: ( x^2 = 4 )";
    const out = normalizeImplicitMathInProse(input);
    expect(out).toContain("$x^2 = 4$");
  });

  it("BUG FIX regression: does not mangle a \\(...\\) inline-math delimiter", () => {
    // Reported live (screenshot): "\\(\\frac{5}{7} = 0.\\overline{714285}\\)"
    // rendered as raw "\$\\frac{5}{7}$ = 0.\$\\overline{714285}\$" — MATH_IN_PARENS_RE
    // matched the bare `(`/`)` characters INSIDE `\(`/`\)` (ignoring the
    // backslash as unrelated adjacent text) and re-wrapped each captured
    // span — trailing stray backslash included — in its own `$...$`.
    // splitInlineMath (markdownPreprocess.ts) already recognizes `\(...\)`
    // directly as inline math; this heuristic must leave it alone.
    const { normalizeImplicitMath } = require("@/lib/math/normalizeImplicit");
    const input = "Decimal form:\n\n\\(\\frac{5}{7} = 0.\\overline{714285}\\) (repeating).";
    const out = normalizeImplicitMath(input);
    expect(out).toContain("\\(\\frac{5}{7} = 0.\\overline{714285}\\)");
    expect(out).not.toContain("\\$");
  });

  it("BUG FIX regression: does not shred a multi-command \\(...\\) expression into broken fragments", () => {
    // Reported live: "\\(\\left(\\frac{5}{7}\\right)^2 = \\frac{25}{49}\\)" — once
    // MATH_IN_PARENS_RE mangled the outer delimiter (see above), the
    // stranded \\left/\\right/^2 fragments were left as, or individually
    // re-wrapped into, broken LaTeX: \\left and \\right each lost the
    // delimiter they require, and "^2" was left as literal unrendered text
    // outside any math span.
    const { normalizeImplicitMath } = require("@/lib/math/normalizeImplicit");
    const input = "Square: \\(\\left(\\frac{5}{7}\\right)^2 = \\frac{25}{49} \\approx 0.5102\\)";
    const out = normalizeImplicitMath(input);
    expect(out).toContain(
      "\\(\\left(\\frac{5}{7}\\right)^2 = \\frac{25}{49} \\approx 0.5102\\)",
    );
    expect(out).not.toContain("$\\left$");
    expect(out).not.toContain("$\\right$");
  });
});

describe("fixImplicitExponents", () => {
  it("does not invent exponents from adjacent digits or letter+digit identifiers", () => {
    expect(fixImplicitExponents("12+3=15")).toBe("12+3=15");
    expect(fixImplicitExponents("20-10=10")).toBe("20-10=10");
    expect(fixImplicitExponents("99*2=198")).toBe("99*2=198");
    expect(fixImplicitExponents("x2+2=6")).toBe("x2+2=6");
    expect(fixImplicitExponents("x2 = 4")).toBe("x2 = 4");
  });

  it("leaves genuine caret exponents and already-delimited math alone", () => {
    expect(fixImplicitExponents("x^2 = 4")).toBe("x^2 = 4");
    expect(normalizeImplicitMath("$12+3=15$")).toBe("$12+3=15$");
    expect(normalizeImplicitMathInProse("12+3=15")).toBe("$12+3=15$");
    expect(normalizeImplicitMathInProse("20-10=10")).toBe("$20-10=10$");
    expect(normalizeImplicitMathInProse("99*2=198")).toBe("$99*2=198$");
  });

  it("still maps unicode ± to \\pm without touching command tails", () => {
    expect(fixImplicitExponents("x = ±2")).toBe("x = \\pm 2");
    expect(fixImplicitExponents("x = \\pm2")).toBe("x = \\pm2");
    expect(fixImplicitExponents("x = \\pm 2")).toBe("x = \\pm 2");
    expect(fixImplicitExponents("r + 1/r = 17/4")).toBe("r + 1/r = 17/4");
  });
});

describe("applyImplicitPowerNotation", () => {
  it("converts keypad OCR x2 to x^2", () => {
    expect(applyImplicitPowerNotation("x2+2=6")).toBe("x^2+2=6");
    expect(applyImplicitPowerNotation("x2 = 4")).toBe("x^2 = 4");
  });

  it("does not turn a command's trailing letter+digit into a false exponent", () => {
    expect(applyImplicitPowerNotation("x = \\pm2")).toBe("x = \\pm2");
    expect(applyImplicitPowerNotation("x = \\pm x2")).toBe("x = \\pm x^2");
  });

  it("does not rewrite adjacent digits as a base and exponent", () => {
    expect(applyImplicitPowerNotation("12+3=15")).toBe("12+3=15");
  });

  // "(x = 2 or 3)" drew as "x = 2or 3", the "or" two italic variables (2026-10-29).
  it.each([
    ["the roots are (x = 2 or 3).", "the roots are $x = 2 \\text{ or } 3$."],
    ["(x = 1 if y = 2)", "$x = 1 \\text{ if } y = 2$"],
    ["(a = b or c)", "$a = b \\text{ or } c$"],
  ])("sets a joining word in a formula as text: %s", (source, expected) => {
    expect(normalizeImplicitMath(source)).toBe(expected);
  });

  it("leaves a variable that spells part of a word alone", () => {
    expect(normalizeImplicitMath("(x = 2or)")).not.toContain("\\text");
  });
});
