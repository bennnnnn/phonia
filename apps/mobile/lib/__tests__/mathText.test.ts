import { fixImplicitExponents } from "@/lib/math/normalizeImplicit";
import {
  MATH_TALL_LINE_HEIGHT,
  MATH_SCRIPT_LINE_HEIGHT,
  PROTECTED_ESCAPE_MARKER,
  latexHasStackedFrac,
  latexHasNestedMathView,
  latexNeedsTallLine,
  mathRunLineHeight,
  parseSimpleLatex,
  segmentsToPlain,
  splitMathLines,
} from "@/lib/math/text";

describe("parseSimpleLatex", () => {
  it("puts exponents in a View-capable host so the power can rise", () => {
    expect(latexHasNestedMathView("x^{1/6}")).toBe(true);
    expect(latexHasNestedMathView("x^2")).toBe(true);
    expect(latexHasNestedMathView("x + 1")).toBe(false);
  });
  it("parses superscripts", () => {
    const segs = parseSimpleLatex("x^2 + 2 = 6");
    expect(segmentsToPlain(segs)).toBe("x^2 + 2 = 6");
    expect(segs.some((s) => s.type === "sup" && s.value === "2")).toBe(true);
  });

  it("parses bare multi-character exponents as one script", () => {
    expect(parseSimpleLatex("x^-2").some((s) => s.type === "sup" && s.value === "-2")).toBe(true);
    expect(parseSimpleLatex("10^23").some((s) => s.type === "sup" && s.value === "23")).toBe(true);
  });

  it("keeps an unbraced text command as one upright subscript", () => {
    for (const latex of [String.raw`t_\text{flight}`, String.raw`t_\mathrm{flight}`]) {
      const segments = parseSimpleLatex(latex);
      const subscript = segments.find((segment) => segment.type === "sub");
      expect(subscript?.type).toBe("sub");
      if (subscript?.type !== "sub") return;
      expect(subscript.body).toEqual([{ type: "upright", value: "flight" }]);
      expect(segmentsToPlain(segments)).toBe("t_flight");
      expect(segmentsToPlain(segments)).not.toMatch(/[\uE006\uE007]/);
    }
  });

  it("does not split other upright commands or private-use braces into a one-character script", () => {
    const pua = /[\uE000-\uE00F]/;
    for (const latex of [
      String.raw`t_\textit{rel}`,
      String.raw`t_\textup{rel}`,
      String.raw`t_\emph{rel}`,
      String.raw`t_\mbox{rel}`,
      String.raw`v_\operatorname*{max}`,
      String.raw`t_ \text{flight}`,
      String.raw`\frac{t_\textit{rel}}{c}`,
      String.raw`\sqrt[\textit{n}]{8}`,
    ]) {
      const plain = segmentsToPlain(parseSimpleLatex(latex));
      expect(plain).not.toMatch(pua);
      expect(plain).not.toMatch(/\\/);
      expect(plain).not.toMatch(/textit|textup|emph|mbox|operatorname/);
    }
    const italic = parseSimpleLatex(String.raw`t_\textit{rel}`);
    const subscript = italic.find((segment) => segment.type === "sub");
    expect(subscript).toEqual({ type: "sub", value: "", body: [{ type: "upright", value: "rel" }] });
    expect(parseSimpleLatex(String.raw`t_ \text{flight}`)).toEqual([
      { type: "text", value: "t" },
      { type: "sub", value: "", body: [{ type: "upright", value: "flight" }] },
    ]);

    const styled = parseSimpleLatex(String.raw`F_\mathbf{g}`);
    expect(segmentsToPlain(styled)).toBe("F_g");
    expect(JSON.stringify(styled)).not.toMatch(pua);
    expect(segmentsToPlain(styled)).not.toContain("mathbf");
    expect(parseSimpleLatex(String.raw`\mathbf{x}`)).toEqual([{ type: "text", value: "x" }]);

    expect(segmentsToPlain(parseSimpleLatex(String.raw`x^ {2}`))).toBe("x^2");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`x^\{2\}`))).toBe("x^2");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`x_\{i\}`))).toBe("x_i");
    expect(JSON.stringify(parseSimpleLatex(String.raw`x^\{n\}`))).not.toMatch(pua);
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\{1, 2\}`))).toBe("{1, 2}");

    expect(segmentsToPlain(parseSimpleLatex(String.raw`\hat\text{v}`))).toBe("v̂");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\vec v`))).toBe("v⃗");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\vec\mathbf{F}`))).toBe("F⃗");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\sqrt\text{x}`))).toBe("√x̅");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\sqrt\{y\}`))).toBe("√y̅");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`x^\frac{1}{2}`))).toBe("x^1/2");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`x_\max`))).toBe("x_max");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\text{\textit{\mathrm{kg}}}`))).toBe("kg");
    expect(parseSimpleLatex(String.raw`\textit{don't}`)).toEqual([
      { type: "upright", value: "don't" },
    ]);
  });

  it("keeps upright text styled inside a subscript", () => {
    const segments = parseSimpleLatex(String.raw`t_{\mathrm{flight}}`);
    const subscript = segments.find((segment) => segment.type === "sub");
    expect(subscript?.type).toBe("sub");
    if (subscript?.type !== "sub") return;
    expect(subscript.body).toEqual([{ type: "upright", value: "flight" }]);
    expect(segmentsToPlain(segments)).toBe("t_flight");
    expect(segmentsToPlain(segments)).not.toMatch(/[\uE006\uE007]/);
  });

  it("does not turn adjacent digits into a superscript (MathText pipeline)", () => {
    for (const expr of ["12+3=15", "20-10=10", "99*2=198"]) {
      const segs = parseSimpleLatex(fixImplicitExponents(expr));
      expect(segs.some((s) => s.type === "sup")).toBe(false);
      expect(segmentsToPlain(segs)).toBe(expr);
    }
  });

  it.each([
    ["3 x^{2} + 25 = 25", "3x^{2} + 25 = 25"],
    [String.raw`2 \left(x + 9\right) = 24`, String.raw`2\left(x + 9\right) = 24`],
    [String.raw`4 \sqrt{2}`, String.raw`4\sqrt{2}`],
    ["2.5 t + 1", "2.5t + 1"],
  ])("closes the gap between a coefficient and its term: %s", (expr, expected) => {
    expect(fixImplicitExponents(expr)).toBe(expected);
  });

  it.each([
    ["x + 3 = 5"],
    [String.raw`x = 2 \text{ or } x = 3`],
    [String.raw`\text{For } x = 2:`],
    [String.raw`2 \cdot 3 = 6`],
    [String.raw`14 = 14 \quad \text{(true)}`],
  ])("leaves operators, relations and text spacing alone: %s", (expr) => {
    expect(fixImplicitExponents(expr)).toBe(expr);
  });

  it("BUG FIX regression: braced 2/3 exponent is one sup (not 3 then 2 then /3)", () => {
    const segs = parseSimpleLatex("3^{2/3}");
    expect(segs.some((s) => s.type === "sup" && s.value === "2/3")).toBe(true);
    expect(segmentsToPlain(segs)).toBe("3^2/3");
  });

  it("BUG FIX regression: unicode superscripts/subscripts parse as real scripts", () => {
    // OCR / models emit `x²` / `a₁₀` instead of caret form; without normalize
    // those glyphs stayed plain text and never became MathText sup/sub.
    const sup = parseSimpleLatex("x²");
    expect(sup.some((s) => s.type === "sup" && s.value === "2")).toBe(true);
    expect(segmentsToPlain(sup)).toBe("x^2");
    const sub = parseSimpleLatex("a₁₀");
    expect(sub.some((s) => s.type === "sub" && s.value === "10")).toBe(true);
    expect(segmentsToPlain(parseSimpleLatex(String.raw`n \in \mathbb{P}`))).toContain("ℙ");
  });

  it("handles pm and sqrt", () => {
    const segs = parseSimpleLatex(String.raw`x = \pm \sqrt{4}`);
    expect(segmentsToPlain(segs)).toContain("±");
    // Radicand sits under a combining overline ("4̅"), not in parens — no
    // parens needed since the bar itself delimits what's under the root.
    expect(segmentsToPlain(segs)).toContain("√4̅");
  });

  it("treats TeX grouping braces as invisible while preserving escaped set braces", () => {
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\left|{x}\right|`))).toBe("|x|");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`a{b}`))).toBe("ab");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\{x\}`))).toBe("{x}");
  });

  it("parses fractions", () => {
    const segs = parseSimpleLatex(String.raw`\frac{a}{b}`);
    expect(segs).toEqual([
      { type: "frac", num: [{ type: "text", value: "a" }], den: [{ type: "text", value: "b" }] },
    ]);
  });

  it("parses \\cancel as a cancelled factor, not cancel(3) function notation", () => {
    const segs = parseSimpleLatex(String.raw`\frac{\cancel{3} x}{\cancel{3}}`);
    expect(segmentsToPlain(segs)).toBe("3 x/3");
    expect(segmentsToPlain(segs)).not.toContain("cancel");
    const frac = segs.find((s) => s.type === "frac");
    expect(frac?.type).toBe("frac");
    if (frac?.type === "frac") {
      expect(frac.num.some((s) => s.type === "cancel")).toBe(true);
      expect(frac.den.some((s) => s.type === "cancel")).toBe(true);
    }
  });

  it("BUG FIX regression: \\frac numerator/denominator render as nested segments (superscripts inside a fraction)", () => {
    // \frac{x^2}{4} used to flatten the numerator to the literal string "x^2"
    // (caret shown), not the superscript x². num/den are now MathSegment[] so
    // superscripts/subscripts render correctly inside a fraction.
    const segs = parseSimpleLatex(String.raw`\frac{x^2}{4}`);
    const frac = segs.find((s) => s.type === "frac");
    expect(frac).toBeTruthy();
    if (frac?.type === "frac") {
      expect(frac.num.some((s) => s.type === "sup" && s.value === "2")).toBe(true);
      expect(segmentsToPlain(frac.num)).toBe("x^2");
      expect(segmentsToPlain(frac.den)).toBe("4");
    }
  });

  it("BUG FIX regression: normalizes \\dfrac/\\tfrac/\\cfrac to \\frac (no raw \\dfrac inline)", () => {
    expect(parseSimpleLatex(String.raw`\dfrac{a}{b}`)).toEqual([
      { type: "frac", num: [{ type: "text", value: "a" }], den: [{ type: "text", value: "b" }] },
    ]);
    expect(parseSimpleLatex(String.raw`\tfrac{1}{2}`).some((s) => s.type === "frac")).toBe(true);
    expect(parseSimpleLatex(String.raw`\cfrac{a}{b}`).some((s) => s.type === "frac")).toBe(true);
  });

  it("reads TeX's brace-less fraction arguments: \\frac12 is one half, not the letters frac12", () => {
    const half = { type: "frac", num: [{ type: "text", value: "1" }], den: [{ type: "text", value: "2" }] };
    expect(parseSimpleLatex(String.raw`\frac12`)).toEqual([half]);
    expect(parseSimpleLatex(String.raw`\tfrac12`)).toEqual([half]);
    expect(parseSimpleLatex(String.raw`\frac 1 2`)).toEqual([half]);
    expect(parseSimpleLatex(String.raw`\frac1{2}`)).toEqual([half]);
    const motion = parseSimpleLatex(String.raw`s = \frac12 a t^2`);
    expect(motion.some((seg) => seg.type === "frac")).toBe(true);
    expect(segmentsToPlain(motion)).not.toContain("frac");
    const pi = parseSimpleLatex(String.raw`\frac\pi2`).find((seg) => seg.type === "frac");
    expect(pi?.type).toBe("frac");
    if (pi?.type === "frac") expect(segmentsToPlain(pi.den)).toBe("2");
    // The braced form is untouched, and \\fraction is not a fraction.
    expect(parseSimpleLatex(String.raw`\frac{a}{b}`)).toEqual([
      { type: "frac", num: [{ type: "text", value: "a" }], den: [{ type: "text", value: "b" }] },
    ]);
  });

  it("keeps a nested root index and braced scripts as segments", () => {
    const root = parseSimpleLatex(String.raw`\sqrt[\frac{1}{2}]{x}`).find((seg) => seg.type === "sqrt");
    expect(root?.type).toBe("sqrt");
    if (root?.type !== "sqrt") return;
    expect(root.index?.[0]?.type).toBe("frac");
    expect(root.degree).toBeUndefined();

    const exponent = parseSimpleLatex(String.raw`x^{\sqrt{2}}`).find((seg) => seg.type === "sup");
    expect(exponent?.type).toBe("sup");
    if (exponent?.type !== "sup") return;
    expect(exponent.body?.[0]?.type).toBe("sqrt");

    const fraction = parseSimpleLatex(String.raw`x^{\frac{1}{2}}`).find((seg) => seg.type === "sup");
    expect(fraction?.type).toBe("sup");
    if (fraction?.type !== "sup") return;
    expect(fraction.body?.[0]?.type).toBe("frac");

    const slash = parseSimpleLatex("3^{2/3}").find((seg) => seg.type === "sup");
    expect(slash?.type).toBe("sup");
    if (slash?.type !== "sup") return;
    expect(slash.body).toBeUndefined();
    expect(slash.value).toBe("2/3");
  });

  it("BUG FIX regression: nth-root \\sqrt[n]{x} renders as √[n] with an overlined radicand, not raw", () => {
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\sqrt[3]{8}`))).toBe("√[3]8̅");
  });

  it("BUG FIX regression: \\sqrt{\\frac{...}{...}} renders the fraction, does not leak raw \\frac text", () => {
    // Reported live: "m = \pm\sqrt{\frac{M}{2}}" rendered the fraction as
    // literal, unrendered "\frac{M}{2}" text inside the root. Cause: the
    // \sqrt substitution used to be a flat `[^}]+` regex, which can't track
    // nested braces — it stopped at the FIRST "}" (the one closing \frac's
    // own "{M}"), corrupting the match instead of capturing the whole
    // radicand. \sqrt is now parsed like \frac (readGroup, brace-depth
    // aware), so a fraction inside a root parses and renders correctly.
    const segs = parseSimpleLatex(String.raw`m = \pm\sqrt{\frac{M}{2}}`);
    const plain = segmentsToPlain(segs);
    expect(plain).not.toContain("\\frac");
    expect(plain).not.toContain("{");
    expect(plain).not.toContain("}");
    expect(plain).toBe("m = ±√M̅/̅2̅");

    const sqrtSeg = segs.find((s) => s.type === "sqrt");
    expect(sqrtSeg).toBeTruthy();
    if (sqrtSeg?.type === "sqrt") {
      expect(sqrtSeg.body.some((s) => s.type === "frac")).toBe(true);
    }
  });

  it("BUG FIX regression: uppercase Greek + calculus/set symbols render as unicode, not raw backslash", () => {
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\hbar`))).toBe("ℏ");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\frac{\hbar}{2}`))).toContain("ℏ");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\Gamma + \Theta`))).toBe("Γ + Θ");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\Sigma \Omega \Pi`))).toBe("Σ Ω Π");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\partial f / \partial x`))).toContain("∂");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`x \in S`))).toContain("∈");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`A \subset B`))).toContain("⊂");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`a \equiv b`))).toContain("≡");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`(f \circ g)(2)`))).toBe("(f ∘ g)(2)");
    // `\cdot` used to eat `\cdots` → "·s" in factorial steps.
    expect(segmentsToPlain(parseSimpleLatex(String.raw`n \times (n-1) \times \cdots \times 1`))).toBe(
      "n × (n-1) × ⋯ × 1",
    );
    expect(segmentsToPlain(parseSimpleLatex(String.raw`1, 2, \ldots, n`))).toBe("1, 2, …, n");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`1, 2, \dots, n`))).toBe("1, 2, …, n");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`a \cdot b`))).toBe("a ⋅ b");
  });

  it("BUG FIX regression: renders known function names without the leading backslash", () => {
    // \log_2(2) used to render literally as "\log_2(2)" in the no-WebView
    // (Expo Go) plain-text fallback since \log wasn't in CMD_REPLACEMENTS.
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\log_2(2)`))).toBe("log_2(2)");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\sin(x) + \cos(x)`))).toBe(
      "sin(x) + cos(x)",
    );
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\lim_{x \to 0}`))).toBe("lim_x → 0");
  });

  it("keeps an operation's argument in readable notation, never an unknown command's name", () => {
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\varinjlim{x}`))).toBe("lim(x)");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\nosuchcommand{x}`))).toBe("x");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\nosuchcommand x`))).toBe(" x");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\operatorname{lcm}(4,6)`))).toBe(
      "lcm(4,6)",
    );
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\overbrace{a+b}^{s}`))).toBe("a+b^s");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\underbrace{a+b}`))).toBe("a+b");
  });

  it("preserves braced trigonometric and logarithmic function arguments", () => {
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\sin{x} + \log{y}`))).toBe("sin(x) + log(y)");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\cos {\frac{x}{2}}`))).toBe("cos(x/2)");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\mathbf{x}`))).toBe("x");
  });

  it("matches complete relation commands instead of corrupting their suffixes", () => {
    expect(segmentsToPlain(parseSimpleLatex(String.raw`A \subseteq B \supseteq C`))).toBe("A ⊆ B ⊇ C");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`a \simeq b \cong c`))).toBe("a ≃ b ≅ c");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\int_0^1 x\,dx`))).toBe("∫_0^1 x dx");
  });

  it("BUG FIX regression: \\left/\\right render as bare delimiters, not literal backslash text", () => {
    // `/\\left[\(\[\{|\\right[\)\]\}.]/` used to compile everything after the
    // first `[` into ONE character class, so `\right` never matched and a
    // dangling "\right)" leaked into the output.
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\left(\frac{1}{2}\right)`))).toBe("(1/2)");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\left[x\right]`))).toBe("[x]");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\left\{x\right\}`))).toBe("{x}");
  });

  it("BUG FIX regression: \\langle/\\rangle (and \\left\\langle) render as angle brackets", () => {
    // Live chat: vector components showed raw "\langle 2, 3, 4 \rangle"
    // because MathText had no mapping (KaTeX never sees inline $...$).
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\vec{d} = \langle 2, 3, 4 \rangle`))).toBe(
      "d⃗ = ⟨ 2, 3, 4 ⟩",
    );
    expect(
      segmentsToPlain(parseSimpleLatex(String.raw`\left\langle 2,-1,1 \right\rangle`)),
    ).toBe("⟨ 2,-1,1 ⟩");
  });

  it("BUG FIX regression: \\lor/\\land (and \\vee/\\wedge) render as logical glyphs", () => {
    // Inequality unions ask for `\lor` in the verified prompt; without these
    // MathText leaked raw "\lor" / "\land" on the native inline path.
    expect(segmentsToPlain(parseSimpleLatex(String.raw`x < -1 \lor x > 1`))).toBe(
      "x < -1 ∨ x > 1",
    );
    expect(segmentsToPlain(parseSimpleLatex(String.raw`x < -1 \vee x > 1`))).toBe(
      "x < -1 ∨ x > 1",
    );
    expect(segmentsToPlain(parseSimpleLatex(String.raw`P \land Q`))).toBe("P ∧ Q");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`P \wedge Q`))).toBe("P ∧ Q");
  });

  it("caps nested frac/sqrt depth instead of blowing the call stack", () => {
    let nested = "x";
    for (let i = 0; i < 40; i += 1) {
      nested = String.raw`\frac{${nested}}{1}`;
    }
    const segs = parseSimpleLatex(nested);
    expect(segs.length).toBeGreaterThan(0);
    // Deep overflow flattens to text rather than recursing forever.
    expect(JSON.stringify(segs).length).toBeLessThan(50_000);
  });

  it("BUG FIX regression: \\sum/\\prod/\\int render as unicode glyphs, not the literal words", () => {
    // These were misfiled into ROMAN_FUNCTIONS and rendered as "sum(...)"/
    // "prod(...)"/"int(...)" instead of the actual big-operator symbols.
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\sum_{i=1}^{n} i`))).toBe("Σ_i=1^n i");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\prod_{i=1}^{n} i`))).toContain("∏");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\int_0^1 x\,dx`))).toContain("∫");
  });

  it("BUG FIX regression: previously-missing Greek letters and arrows render as unicode, not raw backslash text", () => {
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\delta \sigma \omega`))).toBe("δ σ ω");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`a \implies b`))).toBe("a ⇒ b");
    expect(
      segmentsToPlain(
        parseSimpleLatex(String.raw`\displaystyle\lim_{x \to 0} \frac{\sin x}{x}`),
      ),
    ).not.toContain("displaystyle");
    expect(
      segmentsToPlain(parseSimpleLatex(String.raw`a \quad \Rightarrow \quad b`)),
    ).toContain("⇒");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`a \Longrightarrow b`))).toBe("a ⟹ b");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`f: a \mapsto b`))).toBe("f: a ↦ b");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`x \le 2`))).toBe("x ≤ 2");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`x \ge 0`))).toBe("x ≥ 0");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`a \neq 0`))).toBe("a ≠ 0");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`a \ne 0`))).toBe("a ≠ 0");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`a \not= 0`))).toBe("a ≠ 0");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`a \neq 0`))).not.toContain("≡");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`a \ne 0`))).not.toBe("a ne 0");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`A \cup B \cap C`))).toBe("A ∪ B ∩ C");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`x \in \mathbb{R}`))).toContain("ℝ");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`n \in \mathbb{Z}`))).toContain("ℤ");
  });

  it("BUG FIX regression: \\boxed{...} unwraps to its inner content, not raw backslash text", () => {
    // \boxed has no plain-text equivalent (KaTeX/MathJax draw an actual
    // border) — the no-WebView (Expo Go) fallback used to show the literal
    // "\boxed{28}" instead of just "28".
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\boxed{28}`))).toBe("28");
  });

  it("BUG FIX regression: a bar between two x= roots reads as or, not a pipe", () => {
    const plain = segmentsToPlain(parseSimpleLatex(String.raw`x = \frac{1}{2} | x = 3`));
    expect(plain).toContain("or");
    expect(plain).not.toContain("|");
  });

  it("BUG FIX regression: \\overline{...} draws a real combining overline, not raw backslash text", () => {
    // Reported live (screenshot): "0.\overline{714285}" (a repeating
    // decimal) rendered as the literal raw text "0.\overline{714285}" —
    // \overline had no entry in CMD_REPLACEMENTS or ROMAN_FUNCTIONS, so it
    // fell through to the generic \cmd fallback, which only consumes the
    // command NAME and leaves the following "{714285}" group as literal text.
    const plain = segmentsToPlain(parseSimpleLatex(String.raw`0.\overline{714285}`));
    expect(plain).not.toContain("\\overline");
    expect(plain).not.toContain("{");
    // Every digit carries a combining overline (U+0305), giving one
    // continuous line across the whole repeating block — not just the
    // last digit.
    expect(plain).toBe("0." + "714285".split("").map((c) => `${c}̅`).join(""));
  });

  it("accent commands (\\hat, \\vec, \\bar, \\dot, \\tilde, \\underline) render via combining marks", () => {
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\hat{x}`))).toBe("x̂");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\vec{v}`))).toBe("v⃗");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\overrightarrow{AB}`))).toBe("A⃗B⃗");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\overleftarrow{AB}`))).toBe("A⃖B⃖");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\bar{x}`))).toBe("x̄");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\dot{x}`))).toBe("ẋ");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\ddot{x}`))).toBe("ẍ");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\tilde{x}`))).toBe("x̃");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\underline{AB}`))).toBe(
      "A̲B̲",
    );
  });

  it("BUG FIX regression: decodes markdownPreprocess.ts's PROTECTED_ESCAPE_MARKER back to a literal backslash before any command table runs", () => {
    // markdownPreprocess.ts substitutes this marker in place of a backslash
    // immediately before punctuation-led commands inside $...$ math, to
    // survive markdown-it's own CommonMark backslash-escape rule. Simulate
    // that substituted text arriving here exactly as it does after a real
    // parse, and confirm \, \; \! resolve to their intended spacing once
    // decoded — not the marker itself, and not the bare punctuation the
    // escape rule would otherwise have left behind.
    const m = PROTECTED_ESCAPE_MARKER;
    expect(segmentsToPlain(parseSimpleLatex(`x^2${m},dx`))).toBe("x^2 dx");
    expect(segmentsToPlain(parseSimpleLatex(`a${m};b`))).toBe("a b");
    expect(segmentsToPlain(parseSimpleLatex(`5${m}!`))).toBe("5");
  });

  it("BUG FIX regression: \\binom{n}{k} renders as C(n,k), not raw backslash text", () => {
    // \binom has no stacked-column equivalent in plain text and had no
    // entry anywhere in this module — it fell through to the generic \cmd
    // fallback, leaving "\binom{5}{2}" visible verbatim in the no-WebView
    // (Expo Go) fallback.
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\binom{5}{2}`))).toBe("C(5,2)");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\binom{}{}`))).toBe("C(,)");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\dbinom{n}{k} = 1`))).toBe("C(n,k) = 1");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\tbinom{n}{k}`))).toBe("C(n,k)");
  });

  it("BUG FIX regression: \\begin{cases}/matrix environments render as readable text, not raw commands", () => {
    // MathBlock renders the WHOLE environment through this native parser
    // whenever the preview WebView is unavailable (Expo Go / no dev
    // build) — \begin{...}/\end{...} had no entry anywhere in this module,
    // so a piecewise function or matrix leaked its literal LaTeX source
    // ("\begin{cases}2x+y=5\\x-y=1\end{cases}") instead of rendering.
    expect(
      segmentsToPlain(parseSimpleLatex(String.raw`\begin{cases} 2x+y=5 \\ x-y=1 \end{cases}`)),
    ).toBe("2x+y=5; x-y=1");
    expect(
      segmentsToPlain(
        parseSimpleLatex(String.raw`\begin{cases} x^2 & x \geq 0 \\ -x^2 & x < 0 \end{cases}`),
      ),
    ).toBe("x^2 if x ≥ 0; -x^2 if x < 0");
    expect(
      segmentsToPlain(parseSimpleLatex(String.raw`\begin{pmatrix} 1 & 2 \\ 3 & 4 \end{pmatrix}`)),
    ).toBe("(1, 2; 3, 4)");
    expect(
      segmentsToPlain(parseSimpleLatex(String.raw`\begin{bmatrix} a & b \\ c & d \end{bmatrix}`)),
    ).toBe("[a, b; c, d]");
    expect(
      segmentsToPlain(
        parseSimpleLatex(String.raw`\begin{aligned} 2x + y &= 5 \\ x - y &= 1 \end{aligned}`),
      ),
    ).toBe("2x + y = 5;  x - y = 1");
    expect(
      segmentsToPlain(parseSimpleLatex(String.raw`\begin{multline}x = 1\end{multline}`)),
    ).toBe("x = 1");
  });
});

describe("parseSimpleLatex: which commands take an argument", () => {
  it.each([
    // A root and a fraction are read by their prefix: `\sqrtx` is the root of x.
    [String.raw`\sqrtx`, [{ type: "sqrt", body: [{ type: "text", value: "x" }] }]],
    [String.raw`\sqrtab+1`, [{ type: "sqrt", body: [{ type: "text", value: "ab" }] }, { type: "text", value: "+1" }]],
    [String.raw`\fracture`, [{ type: "text", value: "" }]],
    [String.raw`\cancelled`, [{ type: "text", value: "" }]],
    [String.raw`\cancelto{0}{x}`, [{ type: "cancel", body: [{ type: "text", value: "x" }] }, { type: "sup", value: "0" }]],
    // An accent is read only as its whole word.
    [String.raw`\hatx`, [{ type: "text", value: "" }]],
    [String.raw`\overlinex`, [{ type: "text", value: "" }]],
    [String.raw`\dotx`, [{ type: "text", value: "" }]],
    [String.raw`\hat x`, [{ type: "accent", kind: "hat", span: false, body: [{ type: "text", value: "x" }] }]],
    [String.raw`\ddot{x}`, [{ type: "accent", kind: "ddot", span: false, body: [{ type: "text", value: "x" }] }]],
    [String.raw`\vec\text{v}`, [{ type: "accent", kind: "vec", span: false, body: [{ type: "upright", value: "v" }] }]],
    // Without its argument a command draws nothing, never its name; an object
    // method is not a command, and an unknown name shows only its argument.
    [String.raw`\sqrt`, [{ type: "text", value: "" }]],
    [String.raw`\sqrt[3`, [{ type: "text", value: "[3" }]],
    [String.raw`\cancel`, [{ type: "text", value: "" }]],
    [String.raw`\bar`, [{ type: "text", value: "" }]],
    [String.raw`\frac{1}`, [{ type: "text", value: "1" }]],
    [String.raw`\constructor`, [{ type: "text", value: "" }]],
    [String.raw`\toString{x}`, [{ type: "text", value: "x" }]],
    [String.raw`\hasOwnProperty{x}`, [{ type: "text", value: "x" }]],
    ["x^", [{ type: "text", value: "x" }]],
  ])("parses %s", (latex, segments) => {
    expect(parseSimpleLatex(latex)).toEqual(segments);
  });
});

describe("splitMathLines", () => {
  it("splits a multi-equation fence body into separate lines", () => {
    expect(splitMathLines("x^2 = 5 - 1\nx^2 = 4")).toEqual(["x^2 = 5 - 1", "x^2 = 4"]);
  });

  it("returns a single-element array for a one-line body", () => {
    expect(splitMathLines("x^2 = 4")).toEqual(["x^2 = 4"]);
  });

  it("drops blank lines", () => {
    expect(splitMathLines("x = 2\n\nx = -2\n")).toEqual(["x = 2", "x = -2"]);
  });

  it("BUG FIX regression: does not split a multi-line \\begin{…} environment", () => {
    // aligned/cases/matrix use newlines between rows and must render as ONE
    // block — splitting shattered them into per-row KaTeX parse errors.
    const aligned = String.raw`\begin{aligned} x^2 &= 4 \\ x &= \pm 2 \end{aligned}`;
    expect(splitMathLines(aligned)).toEqual([aligned]);
    const cases = String.raw`\begin{cases} x & 1 \\ y & 2 \end{cases}`;
    expect(splitMathLines(cases)).toEqual([cases]);
    // Independent equations (no environment) still split.
    expect(splitMathLines("x = 1\ny = 2")).toEqual(["x = 1", "y = 2"]);
  });
});

describe("latexNeedsTallLine", () => {
  it("is true for stacked frac/sqrt so parent Text can clear the line above", () => {
    expect(latexNeedsTallLine(String.raw`\frac{x}{y}`)).toBe(true);
    expect(latexNeedsTallLine(String.raw`\dfrac{1}{2}`)).toBe(true);
    expect(latexNeedsTallLine(String.raw`\sqrt{25}`)).toBe(true);
    expect(MATH_TALL_LINE_HEIGHT).toBeGreaterThan(25);
    expect(mathRunLineHeight(String.raw`a^2(1+9+81)`)).toBe(MATH_SCRIPT_LINE_HEIGHT);
    expect(mathRunLineHeight("CO₂ and 12 m² in prose")).toBeUndefined();
    expect(mathRunLineHeight(String.raw`\frac{1}{2}`)).toBe(MATH_TALL_LINE_HEIGHT);
    // Whole-paragraph astText (prose + several fracs) used to shrink to 34
    // and clip numerators. Stacked frac always needs the tall line box.
    expect(
      mathRunLineHeight(String.raw`\frac{1}{4}: \frac{8}{1/4}=32, 8 \cdot \frac{1}{4}=2`),
    ).toBe(MATH_TALL_LINE_HEIGHT);
    expect(
      mathRunLineHeight(
        "Now we split it for the ±: $x = \\frac{5+1}{2} = \\frac{6}{2} = 3$",
      ),
    ).toBe(MATH_TALL_LINE_HEIGHT);
  });

  it("is false for flat inline algebra", () => {
    expect(latexNeedsTallLine("x + 1 = 2")).toBe(false);
    expect(latexNeedsTallLine(String.raw`x^2`)).toBe(false);
  });
});

describe("latexHasStackedFrac", () => {
  it("is true only for frac commands (View-in-Text smudge)", () => {
    expect(latexHasStackedFrac(String.raw`\frac{d^2y}{dt^2}`)).toBe(true);
    expect(latexHasStackedFrac(String.raw`\dfrac{1}{2}`)).toBe(true);
    expect(latexHasStackedFrac(String.raw`\sqrt{25}`)).toBe(false);
    expect(latexHasStackedFrac("x + 1")).toBe(false);
  });
});

describe("BUG FIX regression: native inline parser leaks (raw LaTeX / bad format)", () => {
  // Each of these used to leak the raw command word or bare braces in
  // inline `$...$` math (native MathText, used for ALL inline math even
  // in dev builds). KaTeX display math had a readable fallback, but inline
  // did not — so the user saw "bigl(x+1bigr)", "a{=}", "red{x+1}", etc.
  it("strips sized delimiters (\\bigl/\\bigr/\\Bigl/\\biggl…) keeping the delimiter", () => {
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\bigl(x+1\bigr)`))).toBe("(x+1)");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\Bigl[x+1\Bigr]`))).toBe("[x+1]");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\biggl\{1\biggr\}`))).toBe("{1}");
  });

  it("maps big operators to glyphs (\\bigcup/\\oint/\\iint/…)", () => {
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\bigcup_{i=1}^{n} A_i`))).toContain("∪");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\oint_C F\,dr`))).toContain("∮");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\iint f`))).toContain("∬");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\iiint g`))).toContain("∭");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\oplus A`))).toBe("⊕ A");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\otimes B`))).toBe("⊗ B");
  });

  it("maps set-theory / relation glyphs (\\notin, \\degree, …)", () => {
    expect(segmentsToPlain(parseSimpleLatex(String.raw`x \notin A`))).toContain("∉");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`90\degree`))).toContain("°");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\bigcup_{i=1}^{n} A_i`))).toContain("∪");
  });

  it("unwraps \\overset/\\underset/\\stackrel to the base (no bare braces)", () => {
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\overset{a}{=}`))).toBe("=");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\stackrel{a}{=}`))).toBe("=");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\underset{x}{\cup}`))).toBe("∪");
  });

  it("unwraps \\color/\\textcolor to the base (no color name leaked)", () => {
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\color{red}{x+1}`))).toBe("x+1");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\textcolor{blue}{y}`))).toBe("y");
  });

  it("renders logic symbols (\\therefore/\\because) and mod (\\bmod/\\pmod)", () => {
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\therefore x`))).toBe("∴ x");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\because y`))).toBe("∵ y");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`a \bmod b`))).toContain("mod");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\pmod{7}`))).toBe("(mod 7)");
  });

  it("expands smallmatrix / Bmatrix / array environments (no env name leaked)", () => {
    expect(
      segmentsToPlain(parseSimpleLatex(String.raw`\begin{smallmatrix}1&2\\3&4\end{smallmatrix}`)),
    ).toBe("1, 2; 3, 4");
    expect(
      segmentsToPlain(parseSimpleLatex(String.raw`\begin{Bmatrix}1&2\\3&4\end{Bmatrix}`)),
    ).toBe("{1, 2; 3, 4}");
    // array strips its column spec ({cc}) — it must not leak as "{cc}".
    expect(
      segmentsToPlain(parseSimpleLatex(String.raw`\begin{array}{cc}1&2\\3&4\end{array}`)),
    ).toBe("1 2;  3 4");
  });

  it("splits \\substack rows (no stray backslash from the row separator)", () => {
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\substack{a\\b}`))).toBe("a; b");
  });

  it("drops the word to copied from 'simplify to' and restores an eaten frac", () => {
    expect(segmentsToPlain(parseSimpleLatex(String.raw`t o 2 \sqrt{2} = 2 \sqrt{2} o t`))).not.toMatch(
      /t o|o t|\bot\b/,
    );
    expect(segmentsToPlain(parseSimpleLatex(String.raw`rac{\sqrt{8}}{2}`))).not.toContain("rac");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`rac{\sqrt{8}}{2}`))).toContain("/");
  });

  it("does not let \\pm eat the \\pmod prefix", () => {
    // \pm → ± must not match inside \pmod (regression guard for the \pm
    // word-boundary fix that lets \pmod reach its own rule).
    expect(segmentsToPlain(parseSimpleLatex(String.raw`x \pm y`))).toBe("x ± y");
    expect(segmentsToPlain(parseSimpleLatex(String.raw`\pmod{7}`))).toBe("(mod 7)");
  });
});
