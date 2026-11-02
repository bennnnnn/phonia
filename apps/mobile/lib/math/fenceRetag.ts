import { isMathFenceLang } from "@/lib/fenceRegistry";
import { escapedAt } from "@/lib/markdown/inlineCode";
import { closesFence, mapClosedFences, readFenceMarkerLoose } from "@/lib/mdFenceScan";
import { restoreMathEscapes } from "@/lib/math/text";

// Trailing (?=[^a-zA-Z]|$) instead of \b: \b treats `_` as a word char, so it
// would not match the boundary between a command and a subscript
// (`\log_2`, `\lim_{x\to0}`, `\sum_{i=1}^n` are all extremely common LaTeX).
const LATEX_CMD_RE =
  /\\(?:pm|mp|sqrt|frac|text|mathrm|boxed|times|cdots|ldots|dots|cdot|leq|geq|neq|infty|alpha|beta|gamma|delta|epsilon|zeta|eta|theta|iota|kappa|lambda|mu|nu|xi|omicron|pi|rho|sigma|tau|upsilon|phi|chi|psi|omega|begin|left|right|langle|rangle|lvert|rvert|lVert|rVert|log|ln|exp|lim|sup|inf|sin|cos|tan|sec|csc|cot|arcsin|arccos|arctan|sinh|cosh|tanh|sum|prod|int|det|gcd|min|max|arg|deg|ker|dim|hom|binom|partial|nabla|vec|hat|bar|dot|overline|underline|Longrightarrow|Rightarrow|longrightarrow|rightarrow|Longleftrightarrow|Leftrightarrow|longleftrightarrow|leftrightarrow|Longleftarrow|Leftarrow|longleftarrow|leftarrow|implies|iff|to|mapsto|longmapsto|lor|vee|land|wedge|mathbb|operatorname|approx|equiv|propto|angle|degree|cup|cap|subset|supset|forall|exists|notin|in)(?=[^a-zA-Z]|$)/;

/** LaTeX spacing (`\;` `\,` `\:` `\!` `\quad`) — not a C `;` statement. */
const LATEX_SPACING_RE = /\\[;,:!]|\\(?:quad|qquad)(?=[^a-zA-Z]|$)/;

/** Normalize spacing cmds so algebra heuristics don't see literal `;`. */
function stripLatexSpacing(s: string): string {
  return s.replace(LATEX_SPACING_RE, " ");
}

function hasNamedLatexCommand(s: string): boolean {
  return LATEX_CMD_RE.test(s) || /\\text\{/.test(s);
}

/** Drop `"..."` / `'...'` so a command that only lives in a string is not math. */
function stripQuoted(s: string): string {
  let out = "";
  let i = 0;
  while (i < s.length) {
    const quote = s[i];
    if (quote === "\"" || quote === "'") {
      i += 1;
      while (i < s.length && s[i] !== quote) {
        if (s[i] === "\\") i += 1;
        i += 1;
      }
      if (i < s.length) i += 1;
      continue;
    }
    out += s[i];
    i += 1;
  }
  return out;
}

function hasCodeSyntax(s: string): boolean {
  const forCode = stripLatexSpacing(s);
  if (/;|console\.|print\(|=>/.test(forCode)) return true;
  return /(^|\n)\s*(?:def |class |import |from |function |const |let |var |return )/i.test(s);
}

/**
 * A long untagged body is math when LaTeX commands are the body, not one
 * token inside a program. A majority of lines must carry a command, and a
 * command that only appears inside quotes does not count.
 */
function lineHasMathCommand(line: string): boolean {
  return hasNamedLatexCommand(line) || (LATEX_SPACING_RE.test(line) && /=/.test(line) && /\d/.test(line));
}

function consistentlyLatex(s: string, lines: string[]): boolean {
  const outside = stripQuoted(s);
  if (!lineHasMathCommand(outside)) return false;
  if (hasCodeSyntax(s)) return false;
  const hits = lines.filter((line) => lineHasMathCommand(line.trim())).length;
  return lines.length > 0 && hits / lines.length >= 0.5;
}

function looksLikeAlgebraLine(line: string): boolean {
  if (!line || line.length > 120) return false;
  if (/^(def |class |import |function |const |let |var |if |for |while )/i.test(line)) {
    return false;
  }
  // `;`/console./print(/=> are real code tells — but `\;` is LaTeX thin space,
  // so strip spacing commands before treating `;` as a statement terminator.
  const forCodeCheck = stripLatexSpacing(line);
  if (/;|console\.|print\(|=>/.test(forCodeCheck)) return false;
  if (/^[a-zA-Z]\^[\d{]/.test(line)) return true;
  if (/=/.test(line) && /[a-zA-Z]\^/.test(line)) return true;
  // Digits, letters, ops, factorial (!), unicode math (× ÷ → …), LaTeX cmds.
  // Allow `;` only as part of already-stripped spacing (check normalized form).
  if (
    /=/.test(line) &&
    /^[\da-zA-Z+\-*/^=(){}\\_!\s.,²³√±×÷·⋅→←↔⇒⇔∞πθ∑∏]+$/.test(forCodeCheck)
  ) {
    return true;
  }
  return false;
}

/** Plain ``` or ```math body that should render as math, not a code block. */
export function looksLikeMathFenceBody(content: string): boolean {
  const raw = content.trim();
  if (!raw) return false;
  if (raw.startsWith("{")) return false;

  // A body that's ENTIRELY wrapped in a redundant $...$/$$...$$ (the model
  // mistaking fence syntax for inline-math syntax) must be classified on
  // what's underneath the wrap — e.g. "$2^x = 2$" has no recognized LaTeX
  // command of its own, so without unwrapping first it fails every check
  // below (the `$` characters also aren't in looksLikeAlgebraLine's allowed
  // character class) and falls through to a plain code block.
  const s = stripRedundantDollarWrap(raw);

  const lines = s.split("\n").filter((line) => line.trim());
  const longBody = s.length > 400 || lines.length > 12;

  // An unambiguous LaTeX command (\times, \begin, \frac, \text{, ...) is a
  // strong enough signal on a short fence. A long fence stays math only when
  // the body is consistently LaTeX — one `\frac` inside a Python string is
  // still code. The length and line caps below still protect bare algebra,
  // which has no command to lean on.
  if (longBody) {
    if (consistentlyLatex(s, lines)) return true;
  } else if (hasNamedLatexCommand(s)) {
    return true;
  }
  // Spacing-only arithmetic (e.g. `20 \;-\; 10 \;=\; 10`) has no named
  // command from LATEX_CMD_RE — without this, the `;` inside `\;` made the
  // algebra heuristic reject it as "code" and the Copy box showed raw LaTeX.
  if (!longBody && LATEX_SPACING_RE.test(s) && /=/.test(s) && /[\d]/.test(s)) return true;

  // Bare algebra has no command. Keep the length cap here so a long
  // code-like body does not become a math card.
  if (s.length > 400) return false;
  // A multi-step derivation written as bare algebra (one equation per line,
  // no LaTeX commands) routinely runs 5+ lines — e.g. a 5-step solve or a
  // system of 3 equations. The old cap of 4 rejected those and fell through
  // to a plain code block. Raise the cap to 12 for the algebra-only path;
  // a long command-bearing body is handled above only when it is consistently
  // LaTeX, so this only affects the weaker "every line is bare algebra"
  // heuristic, where 12 is still a reasonable safety net against prose.
  if (lines.length > 12) return false;

  if (lines.every((line) => looksLikeAlgebraLine(line.trim()))) {
    return lines.some((line) => /=/.test(line));
  }
  return false;
}

/**
 * A ```math fence body must be bare LaTeX — $...$/$$...$$ are markdown-level
 * inline/display delimiters, not KaTeX syntax, so a model that wraps a fence
 * body in them anyway produces a literal "$" KaTeX can't parse: with
 * throwOnError:false it renders the raw source in errorColor instead of
 * throwing (e.g. "$= \pi \times 16$" showing up in red instead of typeset
 * math). Strip a redundant whole-string wrap defensively rather than let it
 * visibly break.
 */
export function stripRedundantDollarWrap(s: string): string {
  const double = s.match(/^\$\$([\s\S]+)\$\$$/);
  if (double) return double[1].trim();
  const single = s.match(/^\$([^$\n]+)\$$/);
  if (single) return single[1].trim();
  return s;
}

/**
 * The model sometimes wraps only individual sub-expressions in $...$ within
 * an otherwise-bare fence body — e.g. "n! = n $\times$ (n-1)!" — rather than
 * the whole body, which stripRedundantDollarWrap's whole-string match above
 * doesn't catch. Any matched $...$/$$...$$ pair anywhere in a fence body is
 * invalid (same "bare LaTeX only" contract), so unwrap every one of them,
 * leaving an unmatched lone "$" (e.g. real currency text) untouched.
 */
export function stripEmbeddedDollarWraps(s: string): string {
  if (!s.includes("$")) return s;
  // `\$43 ... \$1,720` is currency inside the formula. The `$` of `\$` is not
  // a wrap, and stripping the pair leaves `\43` and `\1,720`.
  return s.replace(
    /\$\$([^$\n]+?)\$\$|\$([^$\n]+?)\$/g,
    (match, double, single, offset: number, source: string) => {
      const opener = double != null ? offset + 1 : offset;
      const closer = offset + match.length - 1;
      if (escapedAt(source, opener) || escapedAt(source, closer)) return match;
      return double ?? single;
    },
  );
}

/** Model often emits ```latex — detect and reroute at render time. */
export function looksLikeLatexFence(content: string): boolean {
  return looksLikeMathFenceBody(content);
}

/**
 * True when inline `$...$` math is sent to MathJax-SVG (display), not the
 * native inline renderer: a LaTeX environment (`\begin{matrix}`, cases,
 * aligned, …) or a large operator (`\sum` / `\prod` / `\int` / `\binom`).
 */
export function isHeavyInlineMath(latex: string): boolean {
  const source = restoreMathEscapes(latex);
  return /\\begin\{[\w*]+\}/.test(source) ||
    /\\(?:sum|prod|int|iint|iiint|oint|oiint|oiiint|[dt]?binom|lim|limsup|liminf)(?![A-Za-z])/.test(source);
}

const INLINE_MATH_FENCE_MAX = 48;
/** List-hosted one-liners can include a short equation (`x - 3 = 0 → x = 3`). */
const LIST_MATH_FENCE_MAX = 160;

function isOneLineMathFenceBody(body: string, maxLen: number): string | null {
  const t = stripRedundantDollarWrap(body.trim());
  if (!t || t.includes("\n")) return null;
  if (t.length > maxLen) return null;
  if (/\\begin\{/.test(t)) return null;
  return t;
}

/**
 * Short one-line ```math (or untagged algebra) belongs in the sentence as
 * `$...$`, not a gray card. Display environments and multi-line derivations
 * stay block fences.
 */
export function shouldRenderMathFenceInline(body: string): boolean {
  const t = isOneLineMathFenceBody(body, INLINE_MATH_FENCE_MAX);
  if (t == null) return false;
  if (/[=\\]/.test(t) && !/^\d+\s*[+\-*/]\s*[A-Za-z]$/.test(t)) return false;
  if (/^[A-Za-z]$/.test(t)) return true;
  if (/^\d+\s*[+\-*/]\s*[A-Za-z]$/.test(t)) return true;
  if (/^[A-Za-z]\s*[+\-*/]\s*\d+$/.test(t)) return true;
  return false;
}

/**
 * A lone `-` / `1.` followed by ```math (or `\[...\]` rewritten as a fence)
 * streams as an empty bullet — live: step "Solve for x" showed `x = 1/2`
 * and hid `x = 3`. Fold that one-line equation onto the marker as `$...$`.
 */
export function shouldInlineMathFenceOnBareListMarker(body: string): boolean {
  return isOneLineMathFenceBody(body, LIST_MATH_FENCE_MAX) != null;
}

function mathFenceLang(info: string): boolean {
  return isMathFenceLang(info.split(/\s/)[0]?.toLowerCase() ?? "");
}

/** Step labels / headings that must not live inside a ```math body. */
export function isMathFenceInterruptLine(line: string): boolean {
  const t = line.trim();
  if (!t) return false;
  return (
    /^#{1,6}\s/.test(t) ||
    /^\d+\.\s+\*\*/.test(t) ||
    /^[-*]\s+\*\*/.test(t) ||
    /^\d+\.\s+[A-Z]/.test(t)
  );
}

/**
 * Models open ```math for step 1 and forget the closer, then open another
 * ```math for step 2. CommonMark (and `[\s\S]*?``` regexes) treat the second
 * opener's backticks as a closer, so the next step becomes a code card and
 * `\frac` paints as prose. Close the first fence before the interrupt.
 */
export function closeInterruptedMathFences(content: string): string {
  const lines = content.split("\n");
  const out: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const open = readFenceMarkerLoose(lines[i]!);
    if (!open || !mathFenceLang(open.info) || open.info.includes("|")) {
      out.push(lines[i]!);
      i += 1;
      continue;
    }
    out.push(lines[i]!);
    i += 1;
    let closed = false;
    while (i < lines.length) {
      const line = lines[i]!;
      const inner = readFenceMarkerLoose(line);
      if (inner && closesFence(inner, open)) {
        out.push(line);
        i += 1;
        closed = true;
        break;
      }
      const nextOpener = Boolean(inner && inner.info !== "");
      if (nextOpener || isMathFenceInterruptLine(line)) {
        out.push(open.char.repeat(open.len));
        out.push("");
        closed = true;
        break;
      }
      out.push(line);
      i += 1;
    }
    if (!closed) {
      out.push(open.char.repeat(open.len));
      out.push("");
    }
  }
  return out.join("\n");
}

/**
 * Rewrite model math fences before markdown parse (latex/plain → math only).
 *
 * Fences are read as the renderer reads them (``mapClosedFences``): a ```latex line
 * inside a ```markdown fence is that fence's example, never a fence of its own.
 */
export function retagMathAndDiagramFences(content: string): string {
  return mapClosedFences(content, (info, body, original) => {
    const bodyTrimmed = body.trim();
    // Tagged latex/tex → math; an untagged fence → math when the body looks like math.
    if (/^(latex|tex)$/i.test(info) || (!info && bodyTrimmed && looksLikeMathFenceBody(bodyTrimmed))) {
      return `\`\`\`math\n${bodyTrimmed}\n\`\`\``;
    }
    return original;
  });
}
