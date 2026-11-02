import {
  segmentTextWithMath,
  type MathTextRun,
  type TextWithMathSegments,
} from "@/components/markdown/rules/textWithMathSegments";

const text = (value: string) => ({ type: "text" as const, value });
const math = (value: string) => ({ type: "math" as const, value });
const inline = (...parts: ReturnType<typeof text | typeof math>[]): MathTextRun => ({
  type: "inline",
  parts,
});
const formula = (latex: string, at: number): MathTextRun => ({ type: "formula", latex, at });

const CASES: [string, string, Partial<TextWithMathSegments>][] = [
  ["prose", "plain prose", { content: "plain prose", layout: "prose", runs: [], runHeight: undefined }],
  ["empty", "", { content: "", layout: "prose", runs: [] }],
  ["drops lone colon lines", "a\n:\n  :  \nb", { content: "a\nb", layout: "prose" }],
  ["html breaks become newlines", "one<br>two<BR/>three", { content: "one\ntwo\nthree" }],
  [
    "an English span stays prose with its dollars",
    "$value of money$",
    { content: "$value of money$", layout: "prose", parts: [text("value of money")] },
  ],
  [
    "simple math shares one Text",
    "Let $x + 1$ be",
    { layout: "inline", parts: [text("Let "), math("x + 1"), text(" be")], runs: [], runHeight: undefined },
  ],
  [
    "a raised script leaves the Text run",
    "Let $x^2$ be",
    {
      layout: "nested",
      runs: [inline(text("Let ")), formula("x^2", 1), inline(text(" be"))],
      // The formula's View sizes itself; the prose keeps the body line height.
      runHeight: undefined,
    },
  ],
  [
    "a tick after simple math stays put",
    "$x$ ✓",
    { content: "$x$ ✓", layout: "inline" },
  ],
  [
    "a tick after a stacked fraction moves first",
    String.raw`$\frac{3}{4}=\frac{6}{8}$ ✓`,
    {
      content: String.raw`✓ $\frac{3}{4}=\frac{6}{8}$`,
      layout: "nested",
      runs: [inline(text("✓ ")), formula(String.raw`\frac{3}{4}=\frac{6}{8}`, 1)],
      runHeight: undefined,
    },
  ],
  [
    "nested math keeps the prose after its punctuation untrimmed",
    String.raw`Use $\sqrt{2}$, then compare $x + 1$ with 4.`,
    {
      layout: "nested",
      runs: [
        inline(text("Use ")),
        formula(String.raw`\sqrt{2}\text{,}`, 1),
        inline(text(" then compare "), math("x + 1"), text(" with 4.")),
      ],
    },
  ],
  [
    "nested math drops a trailing lone colon",
    String.raw`Use the product rule $\sqrt{ab}=\sqrt{a}\sqrt{b}$:`,
    {
      layout: "nested",
      runs: [inline(text("Use the product rule ")), formula(String.raw`\sqrt{ab}=\sqrt{a}\sqrt{b}`, 1)],
    },
  ],
  [
    "a heavy formula is a display block with its punctuation",
    String.raw`Evaluate $\int_0^1 x\,dx$, then compare.`,
    {
      layout: "display",
      runs: [
        inline(text("Evaluate ")),
        formula(String.raw`\int_0^1 x\,dx\text{,}`, 1),
        inline(text("then compare.")),
      ],
    },
  ],
  [
    "punctuation alone leaves no run behind",
    String.raw`$\int x\,dx$.`,
    { layout: "display", runs: [formula(String.raw`\int x\,dx\text{.}`, 0)] },
  ],
  [
    "a heavy formula outranks nested math",
    String.raw`$\sqrt{2}$ and $\sum_{k=1}^n k$`,
    {
      layout: "display",
      runs: [inline(math(String.raw`\sqrt{2}`), text(" and ")), formula(String.raw`\sum_{k=1}^n k`, 2)],
    },
  ],
  [
    "a parenthesis closing on a display formula joins it with its period",
    String.raw`(so $x$ is $\lim_{h\to0}(1+h)^{1/h} = e$). The second`,
    {
      layout: "display",
      runs: [
        inline(text("(so "), math("x"), text(" is ")),
        formula(String.raw`\lim_{h\to0}(1+h)^{1/h} = e\text{).}`, 3),
        inline(text("The second")),
      ],
    },
  ],
  [
    "a display fraction leaves the prose at body line height",
    String.raw`Here $x$ tends to $\lim_{n\to\infty} \frac{1}{n} = 0$ fast.`,
    { layout: "display", runHeight: undefined },
  ],
  [
    "a bracket after nested math stays with it",
    String.raw`($\sqrt{2}$), then`,
    {
      layout: "nested",
      runs: [inline(text("(")), formula(String.raw`\sqrt{2}\text{),}`, 1), inline(text(" then"))],
    },
  ],
];

describe("segmentTextWithMath", () => {
  it.each(CASES)("%s", (_name, input, expected) => {
    expect(segmentTextWithMath(input)).toMatchObject(expected);
  });
});
