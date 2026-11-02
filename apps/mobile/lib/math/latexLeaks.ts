/**
 * LaTeX source left in text a reader sees: a `\command`, an escaped
 * character, a TeX script brace, a math delimiter, a private-use marker the
 * preprocessors use, or a command name printed as a function ("frac(1)").
 * Tests run it over rendered replies; code a reader asked for is not text it
 * sees here, so callers leave code out.
 */

type LatexLeakKind = "command" | "escape" | "script" | "delimiter" | "marker" | "name";
type LatexLeak = { kind: LatexLeakKind; text: string; index: number };

const PATTERNS: [LatexLeakKind, RegExp][] = [
  ["command", /\\[A-Za-z]+/g],
  ["escape", /\\[,;:!> {}()[\]|%&#_$\\]/g],
  ["script", /[\^_]\{/g],
  // A `$` that opens maths: before a command, a brace or a script, or before a
  // letter that an operator follows (`$v = 5`). A price ("$5"), a placeholder
  // ("$X and") and a price tier ("($$)") are not.
  ["delimiter", /\$(?=\\[A-Za-z]|[{^_]|[A-Za-z]\s*[-=^_+*/<>])/g],
  // The preprocessors' own markers. U+E020 up are font glyphs (the negation slash).
  ["marker", /[\uE000-\uE01F]/g],
  [
    "name",
    /\b(?:frac|dfrac|sqrt|mathbb|mathrm|mathbf|mathcal|mathfrak|operatorname|textbf|boxed|overset|underset|xrightarrow|hspace|textcolor|binom|varphi|varepsilon|mathit)\(/g,
  ],
];

export function findLatexLeaks(text: string): LatexLeak[] {
  const leaks: LatexLeak[] = [];
  for (const [kind, pattern] of PATTERNS) {
    for (const match of text.matchAll(pattern)) {
      leaks.push({ kind, text: match[0], index: match.index ?? 0 });
    }
  }
  return leaks.sort((a, b) => a.index - b.index);
}
