/**
 * Math input formatter — a single place that holds the features for cleaning up
 * math a user typed in the composer so it renders nicely.
 *
 * The power feature (`x2` → `x^2`) is keypad-only OCR
 * (`applyImplicitPowerNotation`). Model replies do not rewrite digits.
 * Also: spacing around `=` / binary `+` / binary `-`, relational glyphs,
 * `+-` → `\pm`, `*` → `\times`, simple `a/b` → `\frac{a}{b}`.
 *
 * Paste and history can still call `formatMathExpr`. Send stays verbatim
 * (`messageTextForSend`) so the user bubble matches the composer.
 */

import {
  applyImplicitPowerNotation,
  fixImplicitExponents,
} from "@/lib/math/normalizeImplicit";

type MathFormatOptions = {
  /** `x2` → `x^2` (OCR's dropped caret). Default true. */
  power?: boolean;
  /** `x=3` → `x = 3`, `a-b` → `a - b` (binary only). Default true. */
  spacing?: boolean;
  /** `>=` → `\geq`, `<=` → `\leq`, `!=` → `\neq`. Default true. */
  relations?: boolean;
  /** `+-` → `\pm`. Default true. */
  pm?: boolean;
  /** Binary `*` → `\times` (not markdown `**`). Default true. */
  times?: boolean;
  /** Simple `a/b` → `\frac{a}{b}`. Default true. */
  slashFrac?: boolean;
};

const DEFAULTS: Required<MathFormatOptions> = {
  power: true,
  spacing: true,
  relations: true,
  pm: true,
  times: true,
  slashFrac: true,
};

/** Characters that count as the right-hand operand of a binary operator. */
const OPERAND_TAIL = /[a-zA-Z0-9.)\]}]/;
const ATOM = /^(?:\d+(?:\.\d+)?|[a-zA-Z])/;

function lastNonSpace(s: string): string {
  let k = s.length - 1;
  while (k >= 0 && /\s/.test(s[k]!)) k -= 1;
  return s[k] ?? "";
}

function skipLatexCommand(s: string, i: number): number {
  let j = i + 1;
  if (j < s.length && /[a-zA-Z]/.test(s[j]!)) {
    while (j < s.length && /[a-zA-Z]/.test(s[j]!)) j += 1;
  } else {
    j = i + 2;
  }
  return j;
}

/** Skip `\cmd`, optional `[...]` (nth-root index), then `{...}` groups. */
function skipLatexArgs(s: string, i: number): number {
  let j = skipLatexCommand(s, i);
  if (s[j] === "[") {
    const close = s.indexOf("]", j);
    if (close !== -1) j = close + 1;
  }
  while (s[j] === "{") {
    const next = skipBraceGroup(s, j);
    if (next === j) break;
    j = next;
  }
  return j;
}

function skipBraceGroup(s: string, i: number): number {
  let depth = 0;
  let j = i;
  while (j < s.length) {
    if (s[j] === "{") depth += 1;
    else if (s[j] === "}") {
      depth -= 1;
      if (depth === 0) return j + 1;
    }
    j += 1;
  }
  return j;
}

function readAtom(s: string, i: number): { atom: string; next: number } | null {
  let j = i;
  while (j < s.length && /\s/.test(s[j]!)) j += 1;
  const slice = s.slice(j);
  const m = slice.match(ATOM);
  if (!m) return null;
  const next = j + m[0].length;
  // A partial denominator (x in x^2, or a in alpha) changes division's scope.
  if (/^(?:[A-Za-z0-9.(\[]|\s*[_^'′″‴!])/.test(s.slice(next))) return null;
  return { atom: m[0], next };
}

function lastAtomStart(s: string): { atom: string; start: number } | null {
  const t = s.replace(/\s+$/, "");
  const m = t.match(/(?:\d+(?:\.\d+)?|[a-zA-Z])$/);
  if (!m || m.index == null) return null;
  // Do not steal an exponent, subscript, command tail, or product's last letter.
  if (/[A-Za-z0-9._^/\\]\s*$/.test(t.slice(0, m.index))) return null;
  return { atom: m[0], start: m.index };
}

/** Binary `*` → `\times`. Leaves `**` markdown alone. */
function timesOperators(s: string): string {
  let out = "";
  let i = 0;
  const n = s.length;
  while (i < n) {
    if (s[i] === "\\") {
      const j = skipLatexArgs(s, i);
      out += s.slice(i, j);
      i = j;
      continue;
    }
    if (s.startsWith("**", i)) {
      out += "**";
      i += 2;
      continue;
    }
    if (s[i] === "*") {
      const prev = lastNonSpace(out);
      let k = i + 1;
      while (k < n && /\s/.test(s[k]!)) k += 1;
      const nextCh = s[k] ?? "";
      const binary = OPERAND_TAIL.test(prev) && /[a-zA-Z0-9.(\\[]/.test(nextCh);
      if (binary) {
        out = out.replace(/\s+$/, "") + " \\times ";
        i += 1;
        continue;
      }
    }
    out += s[i];
    i += 1;
  }
  return out;
}

/** Length/time unit slashes (`m/s`, `km/h`) — not algebraic `a/b`. */
function isUnitSlash(left: string, right: string): boolean {
  return /^(?:nm|mm|cm|km|m)$/i.test(left) && /^(?:ms|min|hr|s|h)$/i.test(right);
}

/** Simple `a/b` (number or single letter) → `\frac{a}{b}`. */
function slashToFrac(s: string): string {
  let out = "";
  let i = 0;
  const n = s.length;
  while (i < n) {
    if (s[i] === "\\") {
      const j = skipLatexArgs(s, i);
      out += s.slice(i, j);
      i = j;
      continue;
    }
    if ((s[i] === "^" || s[i] === "_") && s[i + 1] === "{") {
      const j = skipBraceGroup(s, i + 1);
      out += s.slice(i, j);
      i = j;
      continue;
    }
    if (s[i] === "/") {
      const left = lastAtomStart(out);
      const right = readAtom(s, i + 1);
      if (left && right && !isUnitSlash(left.atom, right.atom)) {
        out = out.slice(0, left.start) + `\\frac{${left.atom}}{${right.atom}}`;
        i = right.next;
        continue;
      }
    }
    out += s[i];
    i += 1;
  }
  return out;
}

/**
 * `9\sqrt{9}` is 9 × square-root, not the 9th root `\sqrt[9]{9}`.
 * Leave `\sqrt[...]{...}` (ⁿ√) alone.
 */
function implicitTimesBeforeSqrt(s: string): string {
  let out = "";
  let i = 0;
  const n = s.length;
  while (i < n) {
    if (s.startsWith("\\sqrt", i) && s[i + 5] !== "[") {
      const trimmed = out.replace(/\s+$/, "");
      const prev = lastNonSpace(trimmed);
      const afterBareCommand = /\\[a-zA-Z]+$/.test(trimmed);
      if (OPERAND_TAIL.test(prev) && !afterBareCommand) {
        out = trimmed + " \\times ";
      }
    }
    if (s[i] === "\\") {
      const j = skipLatexArgs(s, i);
      out += s.slice(i, j);
      i = j;
      continue;
    }
    out += s[i];
    i += 1;
  }
  return out;
}

/**
 * Space `=` and binary `+`/`-`. Leaves `^{...}` / `_{...}` groups (exponents
 * and indices) and `\command` names verbatim so grouping and LaTeX commands
 * are never corrupted. Unary `+`/`-` (start, or after an operator / `(` /
 * `=` / `,`) is left unspaced.
 */
function spaceOperators(s: string): string {
  let out = "";
  let i = 0;
  const n = s.length;
  while (i < n) {
    const ch = s[i]!;
    if (ch === "\\") {
      const j = skipLatexArgs(s, i);
      out += s.slice(i, j);
      i = j;
      continue;
    }
    if ((ch === "^" || ch === "_") && s[i + 1] === "{") {
      const j = skipBraceGroup(s, i + 1);
      out += s.slice(i, j);
      i = j;
      continue;
    }
    if (ch === "^" || ch === "_") {
      out += ch + (s[i + 1] ?? "");
      i += 2;
      continue;
    }
    if (ch === "=") {
      out = out.replace(/\s+$/, "") + " = ";
      i += 1;
      continue;
    }
    if (ch === "+" || ch === "-") {
      const prev = lastNonSpace(out);
      const binary = OPERAND_TAIL.test(prev) && prev !== "=";
      if (binary) {
        out = out.replace(/\s+$/, "") + ` ${ch} `;
      } else {
        out += ch;
      }
      i += 1;
      continue;
    }
    out += ch;
    i += 1;
  }
  return out.replace(/\s+/g, " ").trim();
}

/**
 * Unicode radical → LaTeX: `√(49)` and bare `√49` alike. Model replies (and
 * pasted text before `mathPasteNormalize` runs) use the Unicode glyph, but
 * the native math renderer (`components/rich/MathText.tsx`) only stacks a vinculum for the
 * literal `\sqrt{...}` command — an unconverted `√` is drawn as a plain
 * character with no radicand grouping.
 */
function radicalToSqrt(s: string): string {
  let out = s.replace(/√\s*\(([^()]*)\)/g, "\\sqrt{$1}");
  out = out.replace(/√\s*(\d+(?:\.\d+)?)/g, "\\sqrt{$1}");
  return out;
}

/** Balanced-paren scan backward from `end` over one `(...)` group ending
 * just before `end` (after trimming trailing whitespace), or the simple
 * atom `slashToFrac` already recognizes. Returns the un-parenthesized text
 * plus where it starts in `out`, so the caller can splice a `\frac{}{}`
 * over the whole span (including the parens). */
function readGroupedLeft(out: string): { text: string; start: number } | null {
  let i = out.length;
  while (i > 0 && /\s/.test(out[i - 1]!)) i -= 1;
  if (i === 0) return null;
  if (out[i - 1] === ")") {
    let depth = 0;
    let j = i - 1;
    for (; j >= 0; j -= 1) {
      if (out[j] === ")") depth += 1;
      else if (out[j] === "(") {
        depth -= 1;
        if (depth === 0) break;
      }
    }
    if (depth !== 0 || /[A-Za-z0-9._^/\\]\s*$/.test(out.slice(0, j))) return null;
    return { text: out.slice(j + 1, i - 1).trim(), start: j };
  }
  const atom = lastAtomStart(out.slice(0, i));
  return atom ? { text: atom.atom, start: atom.start } : null;
}

/** Mirror of `readGroupedLeft` walking forward from `start` — a `(...)`
 * group right after the slash, or the simple atom `slashToFrac` reads. */
function readGroupedRight(s: string, start: number): { text: string; next: number } | null {
  let i = start;
  while (i < s.length && /\s/.test(s[i]!)) i += 1;
  if (s[i] === "(") {
    let depth = 0;
    let j = i;
    for (; j < s.length; j += 1) {
      if (s[j] === "(") depth += 1;
      else if (s[j] === ")") {
        depth -= 1;
        if (depth === 0) {
          j += 1;
          break;
        }
      }
    }
    if (depth !== 0 || /^(?:[A-Za-z0-9.(\[]|\s*[_^'′″‴!])/.test(s.slice(j))) return null;
    return { text: s.slice(i + 1, j - 1).trim(), next: j };
  }
  const atom = readAtom(s, i);
  return atom ? { text: atom.atom, next: atom.next } : null;
}

/**
 * `a/b` PLUS a parenthesized numerator/denominator on either side —
 * `(11 + 7)/6` and `(-b \pm \sqrt{d})/(2a)` → `\frac{...}{...}` — unlike
 * `slashToFrac`'s bare-atom-only rule (intentionally conservative there
 * since a composer user typing `(11+7)/6` may still be mid-edit; a
 * *complete* model reply line never is). Assistant-only — see
 * `formatAssistantMathExpr`.
 */
function groupedSlashToFrac(s: string): string {
  let out = "";
  let i = 0;
  const n = s.length;
  while (i < n) {
    if (s[i] === "\\") {
      const j = skipLatexArgs(s, i);
      out += s.slice(i, j);
      i = j;
      continue;
    }
    if ((s[i] === "^" || s[i] === "_") && s[i + 1] === "{") {
      const j = skipBraceGroup(s, i + 1);
      out += s.slice(i, j);
      i = j;
      continue;
    }
    if (s[i] === "/") {
      const left = readGroupedLeft(out);
      const right = readGroupedRight(s, i + 1);
      if (left && right && left.text && right.text && !isUnitSlash(left.text, right.text)) {
        out = out.slice(0, left.start) + `\\frac{${left.text}}{${right.text}}`;
        i = right.next;
        continue;
      }
    }
    out += s[i];
    i += 1;
  }
  return out;
}

/**
 * Format a model/assistant math expression for the native renderer:
 * `√(...)` → `\sqrt{...}`, `a/b` AND `(a+b)/c` → `\frac{}{}` (see
 * `groupedSlashToFrac` — steps commonly parenthesize a multi-term numerator
 * or denominator, which the composer's bare-atom-only `slashToFrac` skips),
 * `±` → `\pm`, WITHOUT the composer-only `x2` → `x^2` OCR rewrite (model
 * replies already write explicit `^` for exponents; reinterpreting bare
 * digits after a letter would corrupt subscript-like text the model never
 * intended as an exponent — see the module docstring).
 *
 * This is the fix for steps like `x = (11 - 7)/6 = 4/6 = 2/3` or
 * `x = (-b ± √(b^2-4ac)) / (2a)` rendering as literal parens-and-slash text
 * instead of a stacked fraction with a vinculum: passed as
 * `preprocessMarkdown`'s `mathFormat`, every bare-equation / math-in-parens
 * span `normalizeImplicitMath` wraps in `$...$` now also gets this
 * conversion instead of just `fixImplicitExponents`'s whitespace collapse.
 */
export function formatAssistantMathExpr(expr: string): string {
  const s = fixImplicitExponents(radicalToSqrt(expr));
  const withFracs = groupedSlashToFrac(s);
  return formatMathExpr(withFracs, { power: false, slashFrac: false });
}

/** Format a single math expression (no prose). */
export function formatMathExpr(
  expr: string,
  opts: MathFormatOptions = {},
): string {
  const o = { ...DEFAULTS, ...opts };
  let s = expr.trim();
  if (!s) return s;
  if (o.power) s = applyImplicitPowerNotation(s);
  if (o.relations) {
    s = s.replace(/<=/g, " \\leq ").replace(/>=/g, " \\geq ").replace(/!=/g, " \\neq ");
  }
  if (o.pm) {
    // Only glued `+-` (OCR / typed ±). Spaced `+ -5` is plus then unary
    // minus — MathPapa writes that, and `\+\s*-` used to smash it into `\pm`.
    s = s.replace(/\+-/g, " \\pm ");
  }
  if (o.times) s = timesOperators(s);
  if (o.slashFrac) s = slashToFrac(s);
  s = implicitTimesBeforeSqrt(s);
  if (o.spacing) {
    s = spaceOperators(s);
  }
  return s.replace(/\s+/g, " ").trim();
}
