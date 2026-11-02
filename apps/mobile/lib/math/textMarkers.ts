/**
 * Placeholder for a backslash inside `$...$` / `\(...\)` math that
 * lib/markdown/preprocess.ts substitutes in *before* the content reaches
 * markdown-it. CommonMark's own backslash-escape rule fires on "\" followed
 * by any ASCII punctuation character and silently drops the backslash
 * (e.g. "\," becomes a bare "," — a stray comma sitting where an invisible
 * thin-space belongs; "\!" becomes a bare "!" mid-formula) before the
 * command table ever sees the command. A Private
 * Use Area character isn't ASCII punctuation, so markdown-it's escape rule
 * (and its typographer/smartquotes rules) leave it alone; preprocessLatex
 * decodes it back to a literal backslash as its first step, before any
 * command table runs.
 */
export const PROTECTED_ESCAPE_MARKER = String.fromCharCode(0xe000);
/**
 * `\$` inside math is a dollar sign. Replacing only the backslash leaves a
 * real `$`, and the next scanner closes the span there. The amount then
 * falls out as plain text with the backslash still in front of it.
 */
export const PROTECTED_LITERAL_DOLLAR = String.fromCharCode(0xe00a);
/** Bare `_` inside `$...$` — markdown-it would otherwise start emphasis. */
export const PROTECTED_MATH_UNDERSCORE_MARKER = String.fromCharCode(0xe002);
/** Bare `*` inside `$...$` — markdown-it would otherwise start emphasis. */
export const PROTECTED_MATH_STAR_MARKER = String.fromCharCode(0xe003);
/** Straight math apostrophes must survive Markdown smartquotes unchanged. */
export const PROTECTED_MATH_APOSTROPHE_MARKER = String.fromCharCode(0xe004);
// Native-only literal text/escape preservation across recursive frac parsing.
export const NATIVE_LITERAL_APOSTROPHE_MARKER = String.fromCharCode(0xe005);
// Preserve the semantic boundary of \text{...}/\mathrm{...} until native
// rendering. Without this, unit labels became italic variables after the
// dedicated math font was introduced.
export const NATIVE_UPRIGHT_START_MARKER = String.fromCharCode(0xe006);
export const NATIVE_UPRIGHT_END_MARKER = String.fromCharCode(0xe007);
// Literal set braces must survive the generic TeX-group unwrapping below.
export const NATIVE_LITERAL_LEFT_BRACE_MARKER = String.fromCharCode(0xe008);
export const NATIVE_LITERAL_RIGHT_BRACE_MARKER = String.fromCharCode(0xe009);

/** The literal apostrophe and braces the markers above held back, put back as typed. */
export function restoreNativeLiterals(value: string): string {
  return value
    .split(NATIVE_LITERAL_APOSTROPHE_MARKER).join("'")
    .split(NATIVE_LITERAL_LEFT_BRACE_MARKER).join("{")
    .split(NATIVE_LITERAL_RIGHT_BRACE_MARKER).join("}");
}
// `\textit` and `\operatorname*` belong with `\text`. Leaving them out let a
// bare `_` keep the backslash and print the command name beside the word.
const UPRIGHT_TEXT_COMMANDS =
  "text|textrm|textsf|texttt|textnormal|textbf|textit|textup|emph|mbox|hbox|mathrm|operatorname";
export const UPRIGHT_TEXT_COMMAND_RE = new RegExp(
  `^\\\\(?:${UPRIGHT_TEXT_COMMANDS})\\*?(?![A-Za-z])`,
);
export const UPRIGHT_TEXT_UNWRAP_RE = new RegExp(
  `\\\\(?:${UPRIGHT_TEXT_COMMANDS})\\*?\\{([^}]+)\\}`,
  "g",
);

/** Restore source characters after markdown tokenization, before math parsing. */
export function restoreMathEscapes(latex: string): string {
  return latex
    .split(PROTECTED_LITERAL_DOLLAR).join("$")
    .split(PROTECTED_ESCAPE_MARKER).join("\\")
    .split(PROTECTED_MATH_UNDERSCORE_MARKER).join("_")
    .split(PROTECTED_MATH_STAR_MARKER).join("*")
    .split(PROTECTED_MATH_APOSTROPHE_MARKER).join("'");
}

/** Cap nested \\frac / \\sqrt recursion on pathological model latex. */
export const MAX_MATH_NEST_DEPTH = 12;

// These commands change typography, not the operation applied to an argument.
export const TEXT_STYLE_COMMANDS = new Set([
  "mathbf", "mathit", "mathsf", "mathtt", "mathcal", "mathscr", "boldsymbol", "bm",
]);
