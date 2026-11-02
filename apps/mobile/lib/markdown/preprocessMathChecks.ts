import { splitInlineMath } from "@/lib/markdown/inlineMath";

/**
 * Check lines like `For $x = 2$: $2^2 + 2 = 6$` (or `For F = 0: 0 + 3 = 3 ✓`)
 * must not cram the substitution onto the label line. Split after the colon.
 */
export function layoutCheckVerificationLines(content: string): string {
  let out = content.replace(
    /\$([^$\n]*?=\s*-?\d+)\s*:\s*([^$\n]+)\$/g,
    (_m, label: string, formula: string) => `$${label.trim()}$: $${formula.trim()}$`,
  );
  // Horizontal spacing only: consuming newlines glues the next ```chart
  // opener to a math caption and turns its closer into a new code block.
  out = out.replace(/\$:[ \t]*/g, "$: ");
  out = out
    .split("\n")
    .map((line) => splitPackedCheckLine(normalizeCheckLabelLine(line)))
    .join("\n");
  out = splitChainedEqualsInCheckMath(out);
  // Frac/sqrt labels can't keep a prose `:` after the math View — RN strands
  // it as lone "two dots" and the renderer drops it. Tuck the colon into the
  // last `$...$` so `For x = 1/2:` matches `For x = 3:`.
  return out
    .split("\n")
    .map(tuckStackedCheckColon)
    .join("\n");
}

function splitPackedCheckLine(line: string): string {
  const colon = indexOfCheckLabelColon(line);
  if (colon < 0) return line;
  const after = line.slice(colon + 1).trim();
  if (!after || !looksLikeCheckComputation(after)) return line;
  const before = line.slice(0, colon + 1).trimEnd();
  // A single `\n  ` is a CommonMark softbreak. RN renders that as a space, so
  // `For x = 3:` stuck to the substitution. A blank line is a list paragraph.
  return `${before}\n\n  ${after}`;
}

function lastInlineMathSpan(line: string): { open: number; close: number } | null {
  let open = -1;
  let last: { open: number; close: number } | null = null;
  for (let i = 0; i < line.length; i += 1) {
    if (line[i] !== "$") continue;
    if (open < 0) {
      open = i;
      continue;
    }
    last = { open, close: i };
    open = -1;
  }
  return last;
}

function latexLooksStacked(latex: string): boolean {
  return (
    latex.includes("\\frac") ||
    latex.includes("\\dfrac") ||
    latex.includes("\\sqrt") ||
    latex.includes("\\tbinom")
  );
}

/**
 * `For $x = 3$:` can keep the colon in prose. `For $x = \frac{1}{2}$:` cannot:
 * the fraction is a nested View, so the trailing `:` drops to its own line
 * and markdownRenderRules strips it. Put `:` inside the math span instead.
 */
function tuckStackedCheckColon(line: string): string {
  const forAt = indexOfForKeyword(line);
  if (forAt < 0 || isForExampleAt(line, forAt) || !line.includes("=")) return line;
  const end = line.length;
  let i = end;
  while (i > 0 && (line[i - 1] === " " || line[i - 1] === "\t")) i -= 1;
  if (i === 0 || line[i - 1] !== ":") return line;
  let j = i - 1;
  while (j > 0 && (line[j - 1] === " " || line[j - 1] === "\t")) j -= 1;
  if (j === 0 || line[j - 1] !== "$") return line;
  const span = lastInlineMathSpan(line.slice(0, j));
  if (span == null || span.close !== j - 1) return line;
  const inner = line.slice(span.open + 1, span.close);
  if (!latexLooksStacked(inner) || inner.trim().endsWith(":")) return line;
  return `${line.slice(0, span.open)}$${inner}:$${line.slice(i)}`;
}

function isForExampleAt(line: string, forAt: number): boolean {
  return line.slice(forAt, forAt + 11).toLowerCase() === "for example";
}

/** What may come before a check label's "For": indentation, a bullet, number
 * or task box, a tick, a quote marker, emphasis, and a Check or Verify word
 * (`**Check:** For $x = 2$`). */
const CHECK_LABEL_LEAD = /^(?:\s|[-*+•>_✓✔✅]|\d+[.)]|\[[ xX]\])*(?:(?:check|verify)[*_:]*\s+[*_]*)?/i;

/** The "For" that opens a check label (`- For $x = 2$`), or -1. The label
 * leads its line: a "for" inside a sentence ("$30/day for food = $210.") is
 * prose, and giving it a label's colon printed "$210.:". */
function indexOfForKeyword(line: string): number {
  const at = CHECK_LABEL_LEAD.exec(line)?.[0].length ?? 0;
  if (line.slice(at, at + 3).toLowerCase() !== "for" || isForExampleAt(line, at)) return -1;
  const next = line[at + 3] ?? "";
  return next === " " || next === "*" || next === "$" || next === "" ? at : -1;
}

function stripTrailingCheckTick(s: string): { text: string; mark: string } {
  let i = s.length;
  while (i > 0 && (s[i - 1] === " " || s[i - 1] === "\t")) i -= 1;
  if (i === 0) return { text: s, mark: "" };
  const last = s[i - 1]!;
  if (last !== "✓" && last !== "✔" && last !== "✅") return { text: s, mark: "" };
  let j = i - 1;
  while (j > 0 && (s[j - 1] === " " || s[j - 1] === "\t")) j -= 1;
  return { text: s.slice(0, j), mark: last };
}

function unwrapInlineDollars(s: string): string {
  let out = "";
  for (let i = 0; i < s.length; i += 1) {
    if (s[i] === "$") continue;
    out += s[i]!;
  }
  return out.trim();
}

/**
 * Live checks omit `:` on one root (`For $x = 1/2$`) and keep it on the other
 * (`For $x = 3:`). Put a colon on every For-x label so both match.
 */
function normalizeCheckLabelLine(line: string): string {
  const forAt = indexOfForKeyword(line);
  if (forAt < 0 || isForExampleAt(line, forAt)) return line;
  let afterAt = forAt + 3;
  while (
    afterAt < line.length &&
    (line[afterAt] === "*" || line[afterAt] === " " || line[afterAt] === "\t")
  ) {
    afterAt += 1;
  }
  const afterForRaw = line.slice(afterAt);
  if (!afterForRaw.includes("=") || indexOfCheckLabelColon(line) >= 0) return line;

  const afterFor = afterForRaw.trimStart();
  const leadWs = afterForRaw.length - afterFor.length;
  const prefix = line.slice(0, afterAt + leadWs);
  const latex = unwrapInlineDollars(stripTrailingCheckTick(afterFor).text);
  const segs = splitTopLevelEquals(latex);
  if (latex.includes("=") && segs.length <= 2) {
    return withLabelColon(line);
  }

  const parts = splitInlineMath(afterFor);
  if (parts[0]?.type === "math" && splitTopLevelEquals(parts[0].value).length === 2 && parts.length > 1) {
    let tail = "";
    for (let i = 1; i < parts.length; i += 1) {
      const p = parts[i]!;
      tail += p.type === "math" ? `$${p.value}$` : p.value;
    }
    if (!tail.trim()) return withLabelColon(line);
    return `${prefix}$${parts[0].value}$: ${tail.trim()}`;
  }
  return line;
}

/** A label line with its colon. A line that ends a sentence is no label:
 * "For x = 3." keeps its period rather than reading "3.:". */
function withLabelColon(line: string): string {
  const trimmed = line.replace(/\s+$/, "");
  return /[.,;!?]$/.test(trimmed) ? line : `${trimmed}:`;
}

/** Colon that closes `For x = 2:` / `For $F = 0$:` — not inside `$...$`, not "for example:". */
function indexOfCheckLabelColon(line: string): number {
  const forAt = indexOfForKeyword(line);
  if (forAt < 0 || isForExampleAt(line, forAt)) return -1;
  let i = forAt + 3;
  let inMath = false;
  while (i < line.length) {
    const ch = line[i]!;
    if (ch === "$") {
      inMath = !inMath;
      i += 1;
      continue;
    }
    if (!inMath && ch === ":") {
      const chunk = line.slice(forAt, i);
      if (chunk.includes("=") || unwrapInlineDollars(chunk).includes("=")) return i;
    }
    i += 1;
  }
  return -1;
}

function looksLikeCheckComputation(s: string): boolean {
  if (s.length < 3) return false;
  return /[\d$=+\-]/.test(s);
}

function isCheckLabelOnlyLine(line: string): boolean {
  const colon = indexOfCheckLabelColon(line);
  if (colon >= 0) return line.slice(colon + 1).trim() === "";
  const forAt = indexOfForKeyword(line);
  if (forAt < 0 || isForExampleAt(line, forAt)) return false;
  let afterAt = forAt + 3;
  while (
    afterAt < line.length &&
    (line[afterAt] === "*" || line[afterAt] === " " || line[afterAt] === "\t")
  ) {
    afterAt += 1;
  }
  const afterFor = line.slice(afterAt).trim();
  const latex = unwrapInlineDollars(stripTrailingCheckTick(afterFor).text);
  if (!latex.includes("=") || afterFor.length >= 100) return false;
  return splitTopLevelEquals(latex).length <= 2;
}

function isYouCanCheckHeading(line: string): boolean {
  let t = line.trim().toLowerCase();
  let compact = "";
  for (let i = 0; i < t.length; i += 1) {
    if (t[i] !== "*") compact += t[i]!;
  }
  return compact.startsWith("you can check");
}

function isCheckTickLine(line: string): boolean {
  const t = line.trim();
  return t === "✓" || t === "✔" || t === "✅" || t === "- [x]" || t === "* [x]";
}

/** Top-level `=` only — skip `\{…\}` and `\neq` / `\leq` command tails. */
function splitTopLevelEquals(latex: string): string[] {
  const parts: string[] = [];
  let buf = "";
  let brace = 0;
  for (let i = 0; i < latex.length; i += 1) {
    const ch = latex[i]!;
    if (ch === "\\") {
      buf += ch;
      i += 1;
      while (i < latex.length && /[A-Za-z]/.test(latex[i]!)) {
        buf += latex[i]!;
        i += 1;
      }
      i -= 1;
      continue;
    }
    if (ch === "{") {
      brace += 1;
      buf += ch;
      continue;
    }
    if (ch === "}" && brace > 0) {
      brace -= 1;
      buf += ch;
      continue;
    }
    if (ch === "=" && brace === 0) {
      parts.push(buf.trim());
      buf = "";
      continue;
    }
    buf += ch;
  }
  const last = buf.trim();
  if (last) parts.push(last);
  return parts.filter((p) => p.length > 0);
}

function splitCheckComputationLine(line: string): string[] {
  const indent = line.match(/^\s*/)?.[0] ?? "";
  const body = line.trim();
  if (!body || isCheckTickLine(body)) return [line];

  const { text: peeled, mark } = stripTrailingCheckTick(body);
  const latex = unwrapInlineDollars(peeled);
  const segs = splitTopLevelEquals(latex);
  if (segs.length < 3) return [line];
  const lines: string[] = [];
  segs.forEach((seg, i) => {
    if (i > 0) lines.push("");
    const inner = i === 0 ? seg : `= ${seg}`;
    const suffix = i === segs.length - 1 && mark ? ` ${mark}` : "";
    lines.push(`${indent}$${inner}$${suffix}`);
  });
  return lines;
}

/**
 * Check substitutions like `$a = b = c = 0$` clip the last `= 0` on a phone.
 * One equality per line after a `For x =` label or inside "You can check:" —
 * not numbered homework steps.
 */
function splitChainedEqualsInCheckMath(content: string): string {
  const lines = content.split("\n");
  const out: string[] = [];
  let pendingCheck = false;
  let inCheck = false;
  for (const line of lines) {
    const trimmed = line.trim();
    if (isYouCanCheckHeading(trimmed)) {
      inCheck = true;
      pendingCheck = false;
      out.push(line);
      continue;
    }
    if (trimmed.startsWith("#")) inCheck = false;
    if (isCheckLabelOnlyLine(trimmed)) {
      out.push(line);
      pendingCheck = true;
      continue;
    }
    if ((pendingCheck || inCheck) && (trimmed === "" || isCheckTickLine(trimmed))) {
      out.push(line);
      continue;
    }
    if ((pendingCheck || inCheck) && looksLikeCheckComputation(trimmed)) {
      out.push(...splitCheckComputationLine(line));
      pendingCheck = false;
      continue;
    }
    pendingCheck = false;
    out.push(line);
  }
  return out.join("\n");
}
