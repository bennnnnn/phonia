/** Command → glyph table applied before the segment parser runs. */

import type { MathSegment } from "@/lib/math/textTypes";

export const CMD_REPLACEMENTS: [RegExp, string][] = [
  [/\\prime(?![a-zA-Z])/g, "′"],
  [/\\pm(?![a-zA-Z])/g, "±"],
  [/\\mp(?![a-zA-Z])/g, "∓"],
  [/\\times(?![a-zA-Z])/g, "×"],
  // Longest-first: `\cdot` is a prefix of `\cdots`. Without these, a
  // factorial step `$n \times (n-1) \times \cdots \times 1$` rendered as `·s`.
  [/\\cdots(?![a-zA-Z])/g, "⋯"],
  [/\\ldots(?![a-zA-Z])/g, "…"],
  [/\\dots(?![a-zA-Z])/g, "…"],
  // U+22C5 is the KaTeX_Main dot. U+00B7 middle dot is not in that face.
  [/\\cdot(?![a-zA-Z])/g, "⋅"],
  // Function composition (f ∘ g) — without this, "$ (f \circ g)(2) $" leaks
  // the literal backslash command in MathText / compact answer pills.
  [/\\circ(?![a-zA-Z])/g, "∘"],
  [/\\div(?![a-zA-Z])/g, "÷"],
  [/\\leq(?![a-zA-Z])/g, "≤"],
  [/\\geq(?![a-zA-Z])/g, "≥"],
  // Short forms — common in homework; without these "$x \le 2$" leaks "\le".
  [/\\le(?![a-zA-Z])/g, "≤"],
  [/\\ge(?![a-zA-Z])/g, "≥"],
  [/\\neq(?![a-zA-Z])/g, "≠"],
  // Short form — models write `$a \ne 0$` as often as `\neq`.
  [/\\ne(?![a-zA-Z])/g, "≠"],
  [/\\not=/g, "≠"],
  [/\\approx(?![a-zA-Z])/g, "≈"],
  [/\\infty(?![a-zA-Z])/g, "∞"],
  [/\\cup(?![a-zA-Z])/g, "∪"],
  [/\\cap(?![a-zA-Z])/g, "∩"],
  // Logical or/and — inequality unions use `\lor` (prompt asks for
  // `$x < -1 \lor x > 1$`); without these MathText leaks raw cmds.
  [/\\lor(?![a-zA-Z])/g, "∨"],
  [/\\vee(?![a-zA-Z])/g, "∨"],
  [/\\land(?![a-zA-Z])/g, "∧"],
  [/\\wedge(?![a-zA-Z])/g, "∧"],
  [/\\setminus(?![a-zA-Z])/g, "∖"],
  [/\\emptyset(?![a-zA-Z])/g, "∅"],
  // Blackboard bold — docs claim native support; without this, steps leak
  // "\mathbb{R}" as raw text (display KaTeX never sees inline $...$).
  [/\\mathbb\{R\}/g, "ℝ"],
  [/\\mathbb\{Z\}/g, "ℤ"],
  [/\\mathbb\{N\}/g, "ℕ"],
  [/\\mathbb\{Q\}/g, "ℚ"],
  [/\\mathbb\{C\}/g, "ℂ"],
  [/\\mathbb\{P\}/g, "ℙ"],
  [/\\mathbb\{H\}/g, "ℍ"],
  [/\\mathbb\{F\}/g, "𝔽"],
  [/\\mathbb\{K\}/g, "𝕂"],
  // \sum/\prod/\int are big-operator SYMBOLS (Σ ∏ ∫), not roman-text
  // function names like \log/\sin — they used to render as the literal
  // words "sum"/"prod"/"int" instead of the actual glyph.
  [/\\sum(?![a-zA-Z])/g, "Σ"],
  [/\\prod(?![a-zA-Z])/g, "∏"],
  [/\\int(?![a-zA-Z])/g, "∫"],
  // Big operators — the "big" variants and the rest of the big-operator family.
  // Without these, \bigcup_{i=1}^n / \oint_C / \iint leaked as the
  // literal words "bigcup"/"oint"/"iint" in inline math.
  [/\\bigcup(?![a-zA-Z])/g, "∪"],
  [/\\bigcap(?![a-zA-Z])/g, "∩"],
  [/\\bigvee(?![a-zA-Z])/g, "∨"],
  [/\\bigwedge(?![a-zA-Z])/g, "∧"],
  [/\\bigoplus(?![a-zA-Z])/g, "⊕"],
  [/\\bigotimes(?![a-zA-Z])/g, "⊗"],
  [/\\bigodot(?![a-zA-Z])/g, "⊙"],
  [/\\biguplus(?![a-zA-Z])/g, "⊎"],
  [/\\oint(?![a-zA-Z])/g, "∮"],
  [/\\iint(?![a-zA-Z])/g, "∬"],
  [/\\iiint(?![a-zA-Z])/g, "∭"],
  [/\\oiint(?![a-zA-Z])/g, "∯"],
  [/\\oiiint(?![a-zA-Z])/g, "⨒"],
  // Base operators not previously handled — leaked as literal names inline.
  [/\\oplus(?![a-zA-Z])/g, "⊕"],
  [/\\otimes(?![a-zA-Z])/g, "⊗"],
  [/\\odot(?![a-zA-Z])/g, "⊙"],
  [/\\uplus(?![a-zA-Z])/g, "⊎"],
  [/\\amalg(?![a-zA-Z])/g, "⨿"],
  // Logic symbols — routine in derivations; leaked as the English words.
  [/\\therefore(?![a-zA-Z])/g, "∴"],
  [/\\because(?![a-zA-Z])/g, "∵"],
  [/\\lnot(?![a-zA-Z])/g, "¬"],
  [/\\neg(?![a-zA-Z])/g, "¬"],
  // \bmod renders as "mod" with math spacing; in plain text use a spaced "mod".
  [/\\bmod(?![a-zA-Z])/g, " mod "],
  // Lowercase Greek letters — matches lib/math/fenceRetag.ts's LATEX_CMD_RE list.
  // Only alpha/beta/gamma/theta/pi were handled here; the rest leaked as
  // raw "\delta"/"\sigma"/etc. backslash text once actually rendered.
  // Reduced Planck constant. Without this, `\hbar` falls through as the word hbar.
  [/\\hbar(?![a-zA-Z])/g, "ℏ"],
  [/\\alpha(?![a-zA-Z])/g, "α"],
  [/\\beta(?![a-zA-Z])/g, "β"],
  [/\\gamma(?![a-zA-Z])/g, "γ"],
  [/\\delta(?![a-zA-Z])/g, "δ"],
  [/\\varepsilon(?![a-zA-Z])/g, "ε"],
  [/\\epsilon(?![a-zA-Z])/g, "ε"],
  [/\\zeta(?![a-zA-Z])/g, "ζ"],
  [/\\eta(?![a-zA-Z])/g, "η"],
  [/\\theta(?![a-zA-Z])/g, "θ"],
  [/\\iota(?![a-zA-Z])/g, "ι"],
  [/\\kappa(?![a-zA-Z])/g, "κ"],
  [/\\lambda(?![a-zA-Z])/g, "λ"],
  [/\\mu(?![a-zA-Z])/g, "μ"],
  [/\\nu(?![a-zA-Z])/g, "ν"],
  [/\\xi(?![a-zA-Z])/g, "ξ"],
  [/\\omicron(?![a-zA-Z])/g, "ο"],
  [/\\pi(?![a-zA-Z])/g, "π"],
  [/\\rho(?![a-zA-Z])/g, "ρ"],
  [/\\sigma(?![a-zA-Z])/g, "σ"],
  [/\\tau(?![a-zA-Z])/g, "τ"],
  [/\\upsilon(?![a-zA-Z])/g, "υ"],
  [/\\phi(?![a-zA-Z])/g, "φ"],
  [/\\chi(?![a-zA-Z])/g, "χ"],
  [/\\psi(?![a-zA-Z])/g, "ψ"],
  [/\\omega(?![a-zA-Z])/g, "ω"],
  [/\\Delta(?![a-zA-Z])/g, "Δ"],
  // Arrow/implication commands — matches lib/math/fenceRetag.ts's LATEX_CMD_RE
  // list. Only the 4 short arrows were handled; the rest (routine in
  // step-by-step derivations and limit notation \lim_{x \to 0}) leaked as
  // raw backslash text.
  [/\\longrightarrow(?![a-zA-Z])/g, "⟶"],
  [/\\rightarrow(?![a-zA-Z])/g, "→"],
  [/\\longleftarrow(?![a-zA-Z])/g, "⟵"],
  [/\\leftarrow(?![a-zA-Z])/g, "←"],
  [/\\Longrightarrow(?![a-zA-Z])/g, "⟹"],
  [/\\Rightarrow(?![a-zA-Z])/g, "⇒"],
  [/\\Longleftarrow(?![a-zA-Z])/g, "⟸"],
  [/\\Leftarrow(?![a-zA-Z])/g, "⇐"],
  [/\\longleftrightarrow(?![a-zA-Z])/g, "⟷"],
  [/\\leftrightarrow(?![a-zA-Z])/g, "↔"],
  [/\\Longleftrightarrow(?![a-zA-Z])/g, "⟺"],
  // Equilibrium arrows: chemistry writes these between species, and the word leaked otherwise.
  [/\\rightleftharpoons(?![a-zA-Z])/g, "⇌"],
  [/\\leftrightharpoons(?![a-zA-Z])/g, "⇋"],
  [/\\Leftrightarrow(?![a-zA-Z])/g, "⇔"],
  [/\\implies(?![a-zA-Z])/g, "⇒"],
  [/\\iff(?![a-zA-Z])/g, "⇔"],
  [/\\to(?![a-zA-Z])/g, "→"],
  [/\\longmapsto(?![a-zA-Z])/g, "⟼"],
  [/\\mapsto(?![a-zA-Z])/g, "↦"],
  [/\\quad(?![a-zA-Z])/g, "  "],
  [/\\qquad(?![a-zA-Z])/g, "    "],
  [/\\displaystyle(?![a-zA-Z])/g, ""],
  [/\\textstyle(?![a-zA-Z])/g, ""],
  [/\\scriptstyle(?![a-zA-Z])/g, ""],
  [/\\,/g, " "],
  [/\\;/g, " "],
  [/\\!/g, ""],
  [/\\ /g, " "],
  [/\\%/g, "%"],
  [/\\#/g, "#"],
  [/\\&/g, "&"],
  [/\\_/g, "_"],
  [/\\\{/g, "{"],
  [/\\\}/g, "}"],
  // Uppercase Greek — only \Delta was handled; the rest (\Gamma, \Theta, …)
  // leaked as raw "\Gamma" inline. Matches mathFenceRetag's LATEX_CMD_RE list.
  [/\\Gamma(?![a-zA-Z])/g, "Γ"],
  [/\\Theta(?![a-zA-Z])/g, "Θ"],
  [/\\Lambda(?![a-zA-Z])/g, "Λ"],
  [/\\Sigma(?![a-zA-Z])/g, "Σ"],
  [/\\Omega(?![a-zA-Z])/g, "Ω"],
  [/\\Pi(?![a-zA-Z])/g, "Π"],
  [/\\Phi(?![a-zA-Z])/g, "Φ"],
  [/\\Psi(?![a-zA-Z])/g, "Ψ"],
  [/\\Xi(?![a-zA-Z])/g, "Ξ"],
  [/\\Upsilon(?![a-zA-Z])/g, "Υ"],
  // Calculus / set-theory / relation symbols that previously showed raw.
  [/\\partial(?![a-zA-Z])/g, "∂"],
  [/\\nabla(?![a-zA-Z])/g, "∇"],
  [/\\in(?![a-zA-Z])/g, "∈"],
  [/\\notin(?![a-zA-Z])/g, "∉"],
  [/\\subset(?![a-zA-Z])/g, "⊂"],
  [/\\subseteq(?![a-zA-Z])/g, "⊆"],
  [/\\supset(?![a-zA-Z])/g, "⊃"],
  [/\\supseteq(?![a-zA-Z])/g, "⊇"],
  [/\\simeq(?![a-zA-Z])/g, "≃"],
  [/\\cong(?![a-zA-Z])/g, "≅"],
  [/\\equiv(?![a-zA-Z])/g, "≡"],
  [/\\propto(?![a-zA-Z])/g, "∝"],
  [/\\sim(?![a-zA-Z])/g, "∼"],
  [/\\forall(?![a-zA-Z])/g, "∀"],
  [/\\exists(?![a-zA-Z])/g, "∃"],
  [/\\emptyset(?![a-zA-Z])/g, "∅"],
  [/\\angle(?![a-zA-Z])/g, "∠"],
  [/\\triangle(?![a-zA-Z])/g, "△"],
  [/\\degree(?![a-zA-Z])/g, "°"],
  [/\\perp(?![a-zA-Z])/g, "⊥"],
  [/\\parallel(?![a-zA-Z])/g, "∥"],
  // Angle brackets for vectors / inner products — homework dumps
  // `\langle 2,3,4\rangle` constantly; without these MathText leaks raw cmds.
  [/\\langle(?![a-zA-Z])/g, "⟨"],
  [/\\rangle(?![a-zA-Z])/g, "⟩"],
  [/\\lvert(?![a-zA-Z])/g, "|"],
  [/\\rvert(?![a-zA-Z])/g, "|"],
  [/\\lceil(?![a-zA-Z])/g, "⌈"],
  [/\\rceil(?![a-zA-Z])/g, "⌉"],
  [/\\lfloor(?![a-zA-Z])/g, "⌊"],
  [/\\rfloor(?![a-zA-Z])/g, "⌋"],
  // Conditional probability / set-builder separator. Without an explicit
  // native mapping the generic command fallback rendered ``\mid`` as the
  // literal word "mid" (for example P(D mid +)).
  [/\\mid(?![a-zA-Z])/g, "∣"],
  [/\\lVert(?![a-zA-Z])/g, "‖"],
  [/\\rVert(?![a-zA-Z])/g, "‖"],
  [/\\Vert(?![a-zA-Z])/g, "‖"],
  // Vertical / bidirectional arrows (rightward/implies already handled).
  [/\\uparrow(?![a-zA-Z])/g, "↑"],
  [/\\downarrow(?![a-zA-Z])/g, "↓"],
  [/\\updownarrow(?![a-zA-Z])/g, "↕"],
  [/\\Updownarrow(?![a-zA-Z])/g, "⇕"],
  [/\\Uparrow(?![a-zA-Z])/g, "⇑"],
  [/\\Downarrow(?![a-zA-Z])/g, "⇓"],
];

// A named function is one upright word wherever it stands: as text, `Fd\sin(\theta)` read
// "Fdsin" and went italic as a product of five variables. (`\lim` and its kin keep text:
// their limits sit under the word.)
export const NAMED_FUNCTIONS: ReadonlySet<string> = new Set([
  "arcsin", "arccos", "arctan", "sinh", "cosh", "tanh", "sin", "cos", "tan", "sec", "csc", "cot",
  "log", "ln", "exp", "det", "gcd",
]);

/** Push a named function, spaced as TeX spaces it: from a symbol on either side ("Fd sin θ",
 * "sin x cos x"), not from an operator or a bracket ("2 + sin(θ)"). `after` is the source that
 * follows the name, or null when it takes a braced argument. */
export function pushNamedFunction(out: MathSegment[], name: string, after: string | null): void {
  const last = out[out.length - 1];
  if (last?.type === "text" && /[\p{L}\p{N})\]}'′°|]$/u.test(last.value)) last.value += " ";
  else if (last && last.type !== "text") out.push({ type: "text", value: " " });
  out.push({ type: "upright", value: name });
  const cmd = after?.[0] === "\\" ? after.slice(1).match(/^[a-zA-Z]+/)?.[0] : undefined;
  if (/^[\p{L}\p{N}]/u.test(after ?? "") || (cmd != null && cmd !== "left" && cmd !== "right")) {
    out.push({ type: "text", value: " " });
  }
}
