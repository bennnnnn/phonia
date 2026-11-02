import { isHeavyInlineMath } from "@/lib/math/fenceRetag";
import {
  inlineMathNeedsScroll,
  layoutMath,
  measureRunWidth,
  measureTextWidth,
} from "@/lib/math/layout";
import { findLayouts, layoutProblems } from "@/components/__tests__/layoutChecks";
import { fixImplicitExponents } from "@/lib/math/normalizeImplicit";
import { parseSimpleLatex, readableLatexFallback, segmentsToPlain } from "@/lib/math/text";

/**
 * Appearance invariants for the native math layout tree. These catch a bar
 * that outgrows its radicand, a fraction that overlaps, a script left on the
 * baseline, and a glyph that collapses to zero — without a device screenshot.
 */
const CORPUS: { id: string; latex: string; kind?: "frac" | "sqrt" | "accent" | "script" }[] = [
  { id: "arithmetic", latex: "x + 2 = 5" },
  { id: "quadratic-poly", latex: "3x^2 - 4x + 1", kind: "script" },
  { id: "subscripts", latex: "a_1 + a_2", kind: "script" },
  { id: "neg-exp", latex: "x^{-2}", kind: "script" },
  { id: "frac-exp", latex: "x^{1/6}", kind: "script" },
  { id: "half", latex: String.raw`\frac{1}{2}`, kind: "frac" },
  { id: "rational", latex: String.raw`\frac{x+1}{x-1}`, kind: "frac" },
  { id: "nested-frac", latex: String.raw`\frac{\frac{a}{b}}{\frac{c}{d}}`, kind: "frac" },
  { id: "quadratic-formula", latex: String.raw`\frac{-b \pm \sqrt{b^2-4ac}}{2a}`, kind: "sqrt" },
  { id: "sqrt-x", latex: String.raw`\sqrt{x}`, kind: "sqrt" },
  { id: "sqrt-x1", latex: String.raw`\sqrt{x+1}`, kind: "sqrt" },
  { id: "sqrt-frac", latex: String.raw`\sqrt{\frac{x+1}{x-1}}`, kind: "sqrt" },
  { id: "nested-sqrt", latex: String.raw`\sqrt{x^2+\sqrt{y}}`, kind: "sqrt" },
  { id: "cbrt", latex: String.raw`\sqrt[3]{x}`, kind: "sqrt" },
  { id: "root-12", latex: String.raw`\sqrt[12]{x+1}`, kind: "sqrt" },
  { id: "overline-x", latex: String.raw`\overline{x}`, kind: "accent" },
  { id: "overline-AB", latex: String.raw`\overline{AB}`, kind: "accent" },
  { id: "bar", latex: String.raw`\bar{x}`, kind: "accent" },
  { id: "hat", latex: String.raw`\hat{x}`, kind: "accent" },
  { id: "vec", latex: String.raw`\vec{v}`, kind: "accent" },
  { id: "sub-sup", latex: "x_i^2", kind: "script" },
  { id: "a-n1", latex: "a_{n+1}", kind: "script" },
  { id: "exp-decay", latex: "e^{-kt}", kind: "script" },
  { id: "derivative", latex: String.raw`\frac{dy}{dx}`, kind: "frac" },
  { id: "partial", latex: String.raw`\frac{\partial f}{\partial x}`, kind: "frac" },
  { id: "nabla", latex: String.raw`\nabla f` },
  { id: "abs", latex: "|x|" },
  { id: "norm", latex: String.raw`\|v\|` },
  { id: "ceil", latex: String.raw`\lceil x \rceil` },
  { id: "floor", latex: String.raw`\lfloor x \rfloor` },
  { id: "set", latex: String.raw`\{x \in \mathbb{R} : x > 0\}` },
  { id: "log", latex: String.raw`\log_b a`, kind: "script" },
  { id: "ln", latex: String.raw`\ln(x^2+1)`, kind: "script" },
  { id: "trig", latex: String.raw`\sin^2\theta + \cos^2\theta = 1`, kind: "script" },
  { id: "tan", latex: String.raw`\tan(\frac{\pi}{4})`, kind: "frac" },
  { id: "circle", latex: String.raw`A = \pi r^2`, kind: "script" },
  { id: "binomial-frac", latex: String.raw`\frac{n!}{k!(n-k)!}`, kind: "frac" },
  { id: "binomial-cmd", latex: String.raw`\binom{n}{k}` },
  { id: "bayes", latex: String.raw`P(A|B) = \frac{P(B|A)P(A)}{P(B)}`, kind: "frac" },
  { id: "mean", latex: String.raw`\bar{x} = \frac{1}{n}\sum x_i`, kind: "accent" },
  { id: "variance", latex: String.raw`\sigma^2 = \frac{\sum (x_i - \mu)^2}{n}`, kind: "frac" },
  { id: "dot", latex: String.raw`\vec{a}\cdot\vec{b}`, kind: "accent" },
  { id: "complex", latex: "a + bi" },
  { id: "euler", latex: String.raw`e^{i\pi} + 1 = 0`, kind: "script" },
  { id: "distance", latex: String.raw`\sqrt{x^2+y^2+z^2}`, kind: "sqrt" },
  { id: "gaussian", latex: String.raw`\frac{1}{\sigma\sqrt{2\pi}} e^{-\frac{(x-\mu)^2}{2\sigma^2}}`, kind: "frac" },
  { id: "newton", latex: String.raw`x_{n+1} = x_n - \frac{f(x_n)}{f'(x_n)}`, kind: "frac" },
  { id: "repeating", latex: String.raw`0.\overline{714285}`, kind: "accent" },
  { id: "widehat", latex: String.raw`\widehat{ABC}`, kind: "accent" },
  { id: "underline", latex: String.raw`\underline{AB}`, kind: "accent" },
  { id: "triple-frac", latex: String.raw`\frac{1}{1+\frac{1}{1+\frac{1}{x}}}`, kind: "frac" },
  { id: "cancel", latex: String.raw`\frac{\cancel{3}x}{\cancel{3}}`, kind: "frac" },
  { id: "pm-digit", latex: String.raw`x = \pm2` },
  { id: "cdots", latex: String.raw`n \times (n-1) \times \cdots \times 1` },
  { id: "inequality", latex: String.raw`3x-7 \neq 2` },
  { id: "long", latex: "x+1+".repeat(24) + "x" },
  { id: "matrix", latex: String.raw`\begin{bmatrix}1&2\\3&4\end{bmatrix}` },
  { id: "pmatrix", latex: String.raw`\begin{pmatrix}a&b\\c&d\end{pmatrix}` },
  { id: "cases", latex: String.raw`\begin{cases}x&x>0\\-x&x<0\end{cases}` },
  { id: "sum", latex: String.raw`\sum_{i=1}^{n} i` },
  { id: "integral", latex: String.raw`\int_0^\infty e^{-x}dx` },
  { id: "double-int", latex: String.raw`\iint_R f(x,y)\,dA` },
  { id: "limit", latex: String.raw`\lim_{x\to 0}\frac{\sin x}{x}`, kind: "frac" },
];

function layoutOf(latex: string, em: number) {
  const segments = parseSimpleLatex(fixImplicitExponents(latex.trim()));
  return { segments, layout: layoutMath(segments, em) };
}

describe("native math layout invariants", () => {
  it("has a corpus large enough to cover the notation families", () => {
    expect(CORPUS.length).toBeGreaterThanOrEqual(50);
  });

  it("absorbs a nested script raise into a structured exponent", () => {
    const { layout } = layoutOf(String.raw`x^{y^2}`, 16);
    const structured = findLayouts(layout, "script").find((node) => node.stackedScript);
    expect(structured?.children[0]?.padTop ?? 0).toBeGreaterThan(0);
  });

  it.each(CORPUS)("$id lays out without broken boxes at 16px", ({ latex, kind }) => {
    const { segments, layout } = layoutOf(latex, 16);
    expect(layoutProblems(layout, 16)).toEqual([]);
    expect(layout.width).toBeGreaterThan(0);
    expect(layout.height).toBeGreaterThan(0);
    const plain = segmentsToPlain(segments);
    expect(plain).not.toMatch(/\\[a-zA-Z]+/);
    expect(readableLatexFallback(latex)).not.toMatch(/\\[a-zA-Z]+/);
    if (kind) expect(findLayouts(layout, kind).length).toBeGreaterThan(0);
  });

  it.each([16, 20, 24])("keeps finite boxes when the type size is %s", (em) => {
    for (const item of CORPUS) {
      const { layout } = layoutOf(item.latex, em);
      expect(layoutProblems(layout, em)).toEqual([]);
    }
  });

  it.each([1, 1.3, 1.6])("scales view boxes by font scale %s without NaN", (fontScale) => {
    for (const item of CORPUS) {
      const { layout } = layoutOf(item.latex, 16);
      const width = layout.width * fontScale;
      const height = layout.height * fontScale;
      expect(Number.isFinite(width)).toBe(true);
      expect(Number.isFinite(height)).toBe(true);
      expect(width).toBeGreaterThan(0);
      expect(height).toBeGreaterThan(0);
    }
  });

  it("spaces an unspaced relation without changing the characters", () => {
    expect(measureRunWidth("x+2=5", 16, false)).toBeGreaterThan(measureTextWidth("x+2=5", 16));
    const { segments } = layoutOf("x+2=5", 16);
    expect(segmentsToPlain(segments)).toBe("x+2=5");
  });

  it("scrolls a formula that is wider than a phone column and leaves a short one inline", () => {
    const long = layoutOf("x+1+".repeat(24) + "x", 16).layout;
    expect(long.width).toBeGreaterThan(320);
    expect(inlineMathNeedsScroll(long.width, 390)).toBe(true);
    expect(inlineMathNeedsScroll(long.width, 320)).toBe(true);
    expect(inlineMathNeedsScroll(long.width * 1.6, 430)).toBe(true);
    const short = layoutOf("x + 2 = 5", 16).layout;
    expect(inlineMathNeedsScroll(short.width, 390)).toBe(false);
    expect(inlineMathNeedsScroll(short.width, 320)).toBe(false);
  });

  it("stacks simultaneous scripts in one column narrower than the two glyphs side by side", () => {
    const { layout } = layoutOf("x_i^2", 16);
    const column = findLayouts(layout, "script").find((item) => item.children.length === 2);
    expect(column).toBeDefined();
    const sideBySide = (column?.children ?? []).reduce((sum, child) => sum + child.width, 0);
    expect(column!.width).toBeLessThan(sideBySide);
    expect(layoutProblems(layout, 16)).toEqual([]);
  });

  it("sends matrices, cases, and large operators to MathJax", () => {
    expect(isHeavyInlineMath(String.raw`\begin{bmatrix}1&2\\3&4\end{bmatrix}`)).toBe(true);
    expect(isHeavyInlineMath(String.raw`\begin{pmatrix}a&b\\c&d\end{pmatrix}`)).toBe(true);
    expect(isHeavyInlineMath(String.raw`\begin{cases}x&x>0\\-x&x<0\end{cases}`)).toBe(true);
    expect(isHeavyInlineMath(String.raw`\sum_{i=1}^{n} i`)).toBe(true);
    expect(isHeavyInlineMath(String.raw`\int_0^\infty e^{-x}\,dx`)).toBe(true);
    expect(isHeavyInlineMath(String.raw`\lim_{x\to0}\frac{\sin x}{x}`)).toBe(true);
    expect(isHeavyInlineMath(String.raw`\frac{1}{2}`)).toBe(false);
    expect(isHeavyInlineMath(String.raw`\sqrt{x}`)).toBe(false);
    expect(isHeavyInlineMath(String.raw`\overline{AB}`)).toBe(false);
  });
});

/** The box each segment kind measures to at 16 px, so a refactor cannot move one. */
const BOXES: [string, number, number, [string, number, number, number][]][] = [
  ["x + 1", 39.36, 25, [["run", 39.36, 25, 0]]],
  [String.raw`\frac{x^2}{y_1}`, 22.66, 50.84, [["frac", 16.66, 50.84, 6]]],
  [String.raw`\sqrt[3]{x^2}`, 32, 33.32, [["sqrt", 28, 33.32, 4]]],
  [String.raw`\sqrt[n+1]{x}`, 36.48, 27.56, [["sqrt", 32.48, 27.56, 4]]],
  [String.raw`\overline{AB}`, 24.32, 28.52, [["accent", 24.32, 28.52, 0]]],
  [String.raw`\widehat{x}`, 8.96, 28.52, [["accent", 8.96, 28.52, 0]]],
  [String.raw`\hat{x}`, 8.32, 28.52, [["accent", 8.32, 28.52, 0]]],
  [String.raw`\cancel{3}x`, 16.32, 25, [["cancel", 8, 25, 0], ["run", 8.32, 25, 0]]],
  ["x_i^2", 13.92, 34.72, [["run", 8.32, 25, 0], ["script", 5.6, 34.72, 0]]],
  ["x^{1/2}", 17.056, 34.16, [["run", 8.32, 25, 0], ["script", 8.736, 34.16, 0]]],
  [String.raw`x^{\frac{1}{2}}`, 20.556, 36.16, [["run", 8.32, 25, 0], ["script", 12.236, 30.4, 0]]],
  [String.raw`\frac{\sqrt{x}}{\hat{y}}`, 37.08, 48.32, [["frac", 31.08, 48.32, 6]]],
];

describe("native math layout boxes", () => {
  it.each(BOXES)("measures %s to its box", (latex, width, height, children) => {
    const layout = layoutMath(parseSimpleLatex(latex), 16);
    expect(layout.width).toBeCloseTo(width, 3);
    expect(layout.height).toBeCloseTo(height, 3);
    expect(layout.children).toHaveLength(children.length);
    layout.children.forEach((child, index) => {
      const [kind, w, h, outer] = children[index];
      expect(child.kind).toBe(kind);
      expect(child.width).toBeCloseTo(w, 3);
      expect(child.height).toBeCloseTo(h, 3);
      expect(child.outer).toBeCloseTo(outer, 3);
    });
  });
});
