import { normalizeUnicodeScripts } from "@/lib/unicodeSupSub";

import { repairLeakedMath } from "@/lib/math/healMathSource";
import { rewriteLatexChemistry } from "@/lib/math/latexChemistry";
import { CMD_REPLACEMENTS } from "@/lib/math/latexCommands";
import { rewriteLatexDialects } from "@/lib/math/latexDialects";
import { braceFractionArguments, isParenthesizedArgument, readGroup } from "@/lib/math/latexGroups";
import { rewriteLatexStructure } from "@/lib/math/latexStructure";
import { rewriteSolutionSeparatorBars } from "@/lib/math/solutionBars";
import {
  NATIVE_LITERAL_APOSTROPHE_MARKER,
  NATIVE_LITERAL_LEFT_BRACE_MARKER,
  NATIVE_LITERAL_RIGHT_BRACE_MARKER,
  NATIVE_UPRIGHT_END_MARKER,
  NATIVE_UPRIGHT_START_MARKER,
  UPRIGHT_TEXT_COMMAND_RE,
  UPRIGHT_TEXT_UNWRAP_RE,
  restoreMathEscapes,
} from "@/lib/math/textMarkers";

// Bracket glyphs for the matrix family, by the letter before "matrix" or
// "smallmatrix" ("" draws no bracket at all), matching how KaTeX draws each.
const ENV_BRACKETS: Record<string, [string, string]> = {
  "": ["", ""],
  p: ["(", ")"],
  b: ["[", "]"],
  v: ["|", "|"],
  V: ["‖", "‖"],
  B: [NATIVE_LITERAL_LEFT_BRACE_MARKER, NATIVE_LITERAL_RIGHT_BRACE_MARKER],
};

const ENV_RE = /\\begin\{([A-Za-z]+)\*?\}([\s\S]*?)\\end\{\1\*?\}/g;
// Environments whose first argument is a column or alignment spec, not content.
const ENV_SPEC = new Set(["array", "subarray", "crampedsubarray", "alignat", "alignedat", "xalignat", "xxalignat"]);

/** Split a LaTeX environment body into rows ("\\" is the row separator) and
 * cells within a row ("&" is the column/alignment separator), trimming each. */
function splitEnvRows(body: string): string[][] {
  return body
    .split("\\\\")
    .map((row) => row.trim())
    .filter(Boolean)
    .map((row) => row.split("&").map((cell) => cell.trim()));
}

/**
 * Native MathText flattens environments into readable rows. Display math
 * does not take this path: MathBlock sends the original LaTeX to MathJax-SVG,
 * which scales the brackets. This fallback exists so a matrix still reads
 * as rows if MathJax cannot parse it.
 */
function expandLatexEnvironments(latex: string): string {
  return latex.replace(ENV_RE, (_match, env: string, body: string) => {
    // \begin{array}{cc}… — the column spec ({cc}, {c|c}, …) is the first
    // thing in the body and carries no plain-text meaning. Strip a leading
    // braced group before splitting rows, otherwise it leaks as "{cc}" in
    // the first cell.
    let envBody = body;
    if (ENV_SPEC.has(env) && envBody.trimStart().startsWith("{")) {
      const group = readGroup(envBody, envBody.indexOf("{"));
      if (group) envBody = envBody.slice(group.next);
    }
    const rows = splitEnvRows(expandLatexEnvironments(envBody));
    if (!rows.length) return "";
    if (/cases$/.test(env)) {
      // Piecewise: "expr & condition" per row → "expr if condition".
      return rows
        .map(([expr, cond]) => (cond ? `${expr} if ${cond}` : (expr ?? "")))
        .join("; ");
    }
    const matrix = /^([pbvVB]?)(?:small)?matrix$/.exec(env);
    if (!matrix) {
      // Alignment columns carry no visible meaning outside KaTeX's layout —
      // just join the cells with a space and each row with a separator.
      return rows.map((cells) => cells.join(" ")).join(";  ");
    }
    const [open, close] = ENV_BRACKETS[matrix[1]] ?? ["[", "]"];
    const matrixRows = rows.map((cells) => cells.join(", "));
    return `${open}${matrixRows.join("; ")}${close}`;
  });
}

/** Native postfix primes are math glyphs, not prose quotation marks.
 * Keep text-command contents and escaped quotes literal through recursive
 * fraction/root parsing. KaTeX receives only restoreMathEscapes, never this. */
function normalizeNativeDerivativePrimes(source: string): string {
  let out = "";
  for (let i = 0; i < source.length;) {
    if (source[i] === "\\") {
      const textCommand = UPRIGHT_TEXT_COMMAND_RE.exec(source.slice(i));
      if (textCommand) {
        let groupAt = i + textCommand[0].length;
        while (source[groupAt] === " ") groupAt += 1;
        const group = source[groupAt] === "{" ? readGroup(source, groupAt) : null;
        if (group) {
          out += source.slice(i, group.next).replace(/'/g, NATIVE_LITERAL_APOSTROPHE_MARKER);
          i = group.next;
          continue;
        }
        if (source[groupAt] === "{") {
          // An incomplete text group stays literal; do not rescan nested
          // text openers or reinterpret its apostrophes as derivatives.
          out += source.slice(i).replace(/'/g, NATIVE_LITERAL_APOSTROPHE_MARKER);
          break;
        }
      }
      if (source[i + 1] && !/[A-Za-z]/.test(source[i + 1])) {
        out += source.slice(i, i + 2).replace(/'/g, NATIVE_LITERAL_APOSTROPHE_MARKER);
        i += 2;
        continue;
      }
    }
    if (source[i] === "'") {
      let end = i + 1;
      while (source[end] === "'") end += 1;
      const previous = source[i - 1] ?? "";
      let atom = /[0-9)\]}α-ωΑ-Ω]/.test(previous);
      if (/[A-Za-z]/.test(previous)) {
        let wordStart = i - 1;
        while (wordStart > 0 && /[A-Za-z]/.test(source[wordStart - 1])) wordStart -= 1;
        atom = wordStart === i - 1 || source[wordStart - 1] === "\\";
      }
      // A contraction/quoted word is not a mathematical postfix.
      if (atom && !/[A-Za-z]/.test(source[end] ?? "")) {
        const count = end - i;
        out += count === 1 ? "′" : count === 2 ? "″" : count === 3 ? "‴" : "′".repeat(count);
      } else {
        out += source.slice(i, end);
      }
      i = end;
      continue;
    }
    out += source[i];
    i += 1;
  }
  return out;
}

function preserveNativeUprightRuns(source: string): string {
  let out = "";
  for (let i = 0; i < source.length;) {
    if (source[i] === "\\") {
      const command = UPRIGHT_TEXT_COMMAND_RE.exec(source.slice(i));
      if (command) {
        let groupAt = i + command[0].length;
        while (source[groupAt] === " ") groupAt += 1;
        const group = source[groupAt] === "{" ? readGroup(source, groupAt) : null;
        if (group) {
          // TeX ignores a space before \text. The brace holds the visible
          // space (`43 \text{ per hour}`); keeping both shows `43  per`.
          if (/^\s/.test(group.value)) out = out.replace(/ +$/, "");
          // Markdown attaches sentence punctuation to a math run as
          // `\text{.}` / `\text{,}`. Keep that punctuation in the adjacent
          // run so copy, wrapping, and tests see one continuous expression.
          out += /^[\s.,;:!?]+$/.test(group.value)
            ? group.value
            : `${NATIVE_UPRIGHT_START_MARKER}${group.value}${NATIVE_UPRIGHT_END_MARKER}`;
          i = group.next;
          continue;
        }
      }
    }
    out += source[i];
    i += 1;
  }
  return out;
}

/** Unwrap only SymPy's invisible function-argument group, before escaped
 * set braces lose their backslashes. Ordinary brace groups stay unchanged. */
function unwrapSympyFunctionArguments(source: string): string {
  let out = "";
  for (let i = 0; i < source.length;) {
    if (source.startsWith("{\\left(", i) && /[A-Za-z]/.test(source[i - 1] ?? "") &&
      !/[A-Za-z]/.test(source[i - 2] ?? "")) {
      const group = readGroup(source, i);
      if (!group) { out += source.slice(i); break; }
      const body = group.value.trim();
      if (body.startsWith("\\left(") && body.endsWith("\\right)")) {
        const argument = `(${body.slice(6, -7).trim()})`;
        if (isParenthesizedArgument(argument)) {
          out += argument;
          i = group.next;
          continue;
        }
      }
      // A nonmatching complete group remains literal as a whole.
      out += source.slice(i, group.next);
      i = group.next;
      continue;
    }
    out += source[i];
    i += 1;
  }
  return out;
}

/** Unicode scripts become `^`/`_` scripts, except inside an upright run: that is drawn as
 * written, so `\mathrm{m/s²}` showed "m/s^2". There the ² glyph stays. */
function normalizeScriptsOutsideUpright(source: string): string {
  let out = "";
  let i = 0;
  while (i < source.length) {
    const start = source.indexOf(NATIVE_UPRIGHT_START_MARKER, i);
    const end = start < 0 ? -1 : source.indexOf(NATIVE_UPRIGHT_END_MARKER, start);
    if (end < 0) return out + normalizeUnicodeScripts(source.slice(i));
    out += normalizeUnicodeScripts(source.slice(i, start)) + source.slice(start, end + 1);
    i = end + 1;
  }
  return out;
}

export function preprocessLatex(latex: string): string {
  // Package dialects (`\bm`, `\SI`, `\abs`) and mhchem become plain TeX first,
  // so their units and formulas reach the upright-run step below.
  const source = rewriteLatexChemistry(rewriteLatexDialects(restoreMathEscapes(latex.trim())));
  let s = repairLeakedMath(normalizeNativeDerivativePrimes(unwrapSympyFunctionArguments(source)));
  s = preserveNativeUprightRuns(s);
  // Protect visible set delimiters before command replacement turns `\{`
  // into an ordinary `{`, which is otherwise indistinguishable from an
  // invisible TeX grouping brace. Sized set delimiters are visible too.
  s = s.replace(/\\left\\\{/g, NATIVE_LITERAL_LEFT_BRACE_MARKER);
  s = s.replace(/\\right\\\}/g, NATIVE_LITERAL_RIGHT_BRACE_MARKER);
  s = s.replace(
    /\\[Bb]ig(?:gl|gr|l|r|g)?\\\{/g,
    NATIVE_LITERAL_LEFT_BRACE_MARKER,
  );
  s = s.replace(
    /\\[Bb]ig(?:gl|gr|l|r|g)?\\\}/g,
    NATIVE_LITERAL_RIGHT_BRACE_MARKER,
  );
  s = s.replace(/\\\{/g, NATIVE_LITERAL_LEFT_BRACE_MARKER);
  s = s.replace(/\\\}/g, NATIVE_LITERAL_RIGHT_BRACE_MARKER);
  // Undo lib/markdown/preprocess.ts's PROTECTED_ESCAPE_MARKER substitution first,
  // before any command table below runs — see the marker's own doc comment.
  s = rewriteSolutionSeparatorBars(s);
  // OCR / models often emit Unicode supers/subs (`x²`, `a₁₀`) instead of
  // caret form. Rewrite to `^`/`_` so the segment parser builds real scripts.
  s = normalizeScriptsOutsideUpright(s);
  // Must run before every other substitution — it depends on the raw "\\"
  // row separator and "&" column separator, which later rules (e.g. the
  // \\, → " " spacing rule) would otherwise destroy.
  s = expandLatexEnvironments(s);
  // Boxes, colours, labels, spacing, sized delimiters, \binom and labelled
  // arrows keep only what is seen, with every argument brace-matched. A line
  // break or an alignment mark left outside an environment is only a gap.
  s = rewriteLatexStructure(s).replace(/\s*\\\\\s*/g, "; ").replace(/\s*(?<!\\)&\s*/g, " ");
  // \dfrac / \tfrac / \cfrac are display/text-style fractions — KaTeX treats
  // them like \frac, so normalize before parsing so parseFrac catches them
  // (otherwise they leak as raw "\dfrac{a}{b}" inline).
  s = s.replace(/\\[dct]frac/g, "\\frac");
  s = braceFractionArguments(s);
  for (const [re, rep] of CMD_REPLACEMENTS) {
    s = s.replace(re, rep);
  }
  // \sqrt{...} is handled by parseSqrt below (in the character-by-character
  // parser, not here) — a flat regex over `[^}]+` can't track nested braces,
  // so `\sqrt{\frac{M}{2}}` broke on the FIRST `}` (the one closing \frac's
  // own `{M}`), leaking the rest of the radicand as raw text. readGroup
  // already solves this correctly for \frac's num/den; \sqrt reuses it.
  // Nested `\textit` / `\mathrm` inside an upright run is already inside
  // markers. Unwrap the leftover command so the word is not shown raw.
  // One pass misses `\textit{\mathrm{a}}` because the inner `}` blocks the
  // outer match; each pass shrinks the string.
  for (let pass = 0; pass < 4; pass += 1) {
    UPRIGHT_TEXT_UNWRAP_RE.lastIndex = 0;
    const unwrapped = s.replace(UPRIGHT_TEXT_UNWRAP_RE, "$1");
    if (unwrapped === s) break;
    s = unwrapped;
  }
  // Accents stay as commands. parseAccent builds a segment whose rule is
  // measured from the child; combining marks are only the copy/speech form.
  return s.replace(/\\,/g, " ");
}

