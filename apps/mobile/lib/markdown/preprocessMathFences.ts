import {
  isAnswerLang,
  isExplicitCodeLang,
  looksLikeCode,
  looksLikeMathAnswer,
} from "@/lib/copyBlock";
import { shouldLiftFenceOutOfList } from "@/lib/fenceRegistry";
import { isLoosePipeRow, isTableRow } from "@/lib/markdown/preprocessTables";
import {
  closeInterruptedMathFences,
  isMathFenceInterruptLine,
  shouldInlineMathFenceOnBareListMarker,
  shouldRenderMathFenceInline,
  stripRedundantDollarWrap,
} from "@/lib/math/fenceRetag";
import { readInlineCodeSpan } from "@/lib/markdown/inlineCode";
import {
  closesFence,
  fenceAfterLine,
  fencedLines,
  readFenceMarker,
  readFenceMarkerLoose,
  type OpenFence,
} from "@/lib/mdFenceScan";
import { isStructuredFenceLang } from "@/lib/richBlocks";

/**
 * The model glues a fence opener to the end of a sentence
 * (`Multiply both sides by r: ```math` or `Here's the code: ```python`).
 * CommonMark only recognizes a fence at the start of a line, so the
 * backticks and the body paint as prose. Pull those openers onto their own
 * line before markdown-it runs. Handles ALL fence langs, not just math ones.
 */
export function breakAttachedMathFences(content: string): string {
  const lines = content.split("\n");
  const out: string[] = [];

  const openFence = (lang: string) => {
    if (out.length > 0 && out[out.length - 1] !== "") out.push("");
    out.push("```" + lang.toLowerCase());
  };

  const takeLang = (afterTicks: string): { lang: string; rest: string } | null => {
    let i = 0;
    while (i < afterTicks.length && /[ \t]/.test(afterTicks[i]!)) i += 1;
    const start = i;
    // Read letters, digits, and hyphens — fence langs like "vega-lite",
    // "callout-note", and "molecule3d" contain hyphens/digits. Without
    // digits, "molecule3d" was split into lang "molecule" + body "3d".
    while (i < afterTicks.length && /[\w-]/.test(afterTicks[i]!)) i += 1;
    const lang = afterTicks.slice(start, i);
    // Accept any recognized fence lang: structured (math, graph, geometry,
    // mermaid, …), answer, or explicit code (python, javascript, …). This
    // lifts glued fence openers for ALL langs, not just math ones — the
    // model also glues code fences to prose ("Here's the code: ```python").
    const l = lang.toLowerCase();
    if (!isStructuredFenceLang(l) && !isAnswerLang(l) && !isExplicitCodeLang(l)) {
      return null;
    }
    return { lang, rest: afterTicks.slice(i).trim() };
  };

  const splitTrailingCloser = (rest: string): { body: string; closed: boolean } => {
    if (rest.endsWith("```")) {
      return { body: rest.slice(0, -3).trim(), closed: true };
    }
    return { body: rest, closed: false };
  };

  for (const line of lines) {
    const tick = line.search(/`{3,}/);
    if (tick === -1) {
      out.push(line);
      continue;
    }
    let tickLen = 0;
    while (line[tick + tickLen] === "`") tickLen += 1;
    const prefix = line.slice(0, tick);
    const parsed = takeLang(line.slice(tick + tickLen));
    if (!parsed) {
      out.push(line);
      continue;
    }
    const attached = prefix.trim().length > 0;
    // A table cell that starts ```python must NOT become a real fence —
    // CommonMark then swallows the rest of the comparison (live: Python vs
    // Java "Use Cases" grid rendered inside a python code block).
    if (attached && (isTableRow(prefix) || isLoosePipeRow(prefix))) {
      out.push(line);
      continue;
    }
    const { body, closed } = splitTrailingCloser(parsed.rest);
    if (!attached && !body) {
      out.push(line);
      continue;
    }
    if (attached) out.push(prefix.trimEnd());
    openFence(parsed.lang);
    if (body) out.push(body);
    if (closed) {
      out.push("```");
      out.push("");
    }
  }
  return out.join("\n");
}

// Arithmetic on numbers alone; `x = 5` or `i += 1` is a line of code.
const NUMERIC_EQUATION = /^[\d\s+\-*/×÷·.,()=^]+$/;
const POWER_NOTATION = /^[\dA-Za-z\s+\-*/^().,={}]+$/;
const MATH_FUNCTION = /^(?:sin|cos|tan|sec|csc|cot|log|ln|exp|sqrt)$/i;
// Operators that only code writes: `+=`, `==`, `**`, `//`, `%`, indexing.
const CODE_OPERATOR = /[+\-*/%<>!=]=|\*\*|\/\/|%|\[|\]/;

/**
 * Inline code is code. Only notation no program would contain leaves the
 * span for the maths renderer: a LaTeX command (`\frac{1}{2}`), arithmetic on
 * numbers alone (`2 + 8 + 32 = 42`), or a power over one-letter variables
 * (`x^2 + 1`). `0`, `x = 5`, `i += 1`, `my_list`, `range(n_items)` and `$5`
 * stay monospace.
 */
function backtickInnerIsMath(inner: string): boolean {
  const t = inner.trim();
  if (!t || /[$"'`;:]/.test(t)) return false;
  if (/\\[a-zA-Z]{2,}/.test(t)) return true;
  if (CODE_OPERATOR.test(t)) return false;
  if (NUMERIC_EQUATION.test(t)) return /=/.test(t) && /[+\-*/×÷·^]/.test(t);
  if (!t.includes("^") || !POWER_NOTATION.test(t)) return false;
  const words = t.match(/[A-Za-z]+/g) ?? [];
  return words.every((word) => word.length === 1 || MATH_FUNCTION.test(word));
}

/** Drop a backtick run left at the end of a line only when it closes no code
 * span: `**Line 1:** \`total = 0\`` keeps its closer. */
function stripUnpairedTrailingTicks(line: string): string {
  const trailing = /`+\s*$/.exec(line);
  if (!trailing) return line;
  for (let i = line.indexOf("`"); i >= 0 && i < trailing.index; i = line.indexOf("`", i)) {
    const end = readInlineCodeSpan(line, i);
    if (end != null && end > trailing.index) return line;
    if (end != null) {
      i = end;
      continue;
    }
    while (line[i] === "`") i += 1;
  }
  return line.slice(0, trailing.index);
}

/**
 * Models wrap arithmetic in markdown backticks (`2+8=42`) or leave a stray
 * closer tick on the check line. Those paint as a literal ` on screen.
 * Leave real ``` fences and other inline code alone.
 */
export function unwrapProseMathBackticks(content: string): string {
  const lines = content.split("\n");
  const fenced = fencedLines(content);
  const out: string[] = [];
  for (const [index, line] of lines.entries()) {
    if (fenced[index]) {
      out.push(line);
      continue;
    }
    let s = line.replace(/`(\$[^`\n]+?\$)`/g, "$1");
    s = s.replace(/`([^`\n]+)`/g, (full, inner: string) => {
      const t = String(inner).trim();
      if (!t) return "";
      if (!backtickInnerIsMath(t)) return full;
      if (t.startsWith("$") && t.endsWith("$")) return t;
      return `$${t}$`;
    });
    out.push(stripUnpairedTrailingTicks(s));
  }
  return out.join("\n");
}

/**
 * CommonMark treats a ```math fence as indented code (raw backticks on screen)
 * when it sits inside a numbered list item. Pull math/answer fences to column 0
 * with a blank line before/after so they parse as real fences.
 */
export function liftMathFencesOutOfLists(content: string): string {
  const lines = content.split("\n");
  const out: string[] = [];
  let open: { fence: OpenFence; lifted: boolean } | null = null;
  for (const line of lines) {
    if (open == null) {
      const fence = fenceAfterLine(null, line, true);
      const lang = fence ? (readFenceMarkerLoose(line)?.info ?? "") : "";
      if (fence && /^[a-zA-Z][\w-]*$/.test(lang) && shouldLiftFenceOutOfList(lang)) {
        if (out.length > 0 && out[out.length - 1] !== "") out.push("");
        out.push("```" + lang.toLowerCase());
        open = { fence, lifted: true };
        continue;
      }
      if (fence) open = { fence, lifted: false };
      out.push(line);
      continue;
    }
    if (fenceAfterLine(open.fence, line, true) == null) {
      out.push(open.lifted ? "```" : line);
      if (open.lifted) out.push("");
      open = null;
      continue;
    }
    // When the fence opener was lifted to column 0, strip the original list
    // indent from body lines too — otherwise CommonMark treats 4+ space-
    // indented body lines as indented code blocks, not fence content.
    out.push(open.lifted ? line.trim() : line);
  }
  return out.join("\n");
}

/**
 * CommonMark treats 4+ space (or tab) indented lines as a code block.
 * After an unclosed ```math, the next `2. **Simplify:**` often lands in
 * that indent — a gray Prism card of markdown source. Pull those steps
 * (and only those) back to column 0. Real fenced bodies are left alone.
 */
export function dedentMisindentedMarkdownSteps(content: string): string {
  const lines = content.split("\n");
  const out: string[] = [];
  let open: OpenFence | null = null;
  for (const line of lines) {
    const before = open;
    open = fenceAfterLine(open, line, true);
    if (before || open) {
      out.push(line);
      continue;
    }
    if (/^(?:[ \t]{4,}|\t+)/.test(line) && isMathFenceInterruptLine(line)) {
      out.push(line.trimStart());
      continue;
    }
    out.push(line);
  }
  return out.join("\n");
}

const INLINE_MATH_FENCE_INFO = /^(math|latex|tex)?$/i;

function isFenceCloser(line: string, open: OpenFence): boolean {
  const marker = readFenceMarker(line);
  return Boolean(marker && closesFence(marker, open));
}

function appendInlineMath(out: string[], latex: string): void {
  const piece = `$${latex}$`;
  while (out.length > 0 && out[out.length - 1]!.trim() === "") out.pop();
  if (out.length > 0 && out[out.length - 1]!.trim() !== "") {
    const prev = out[out.length - 1]!.replace(/\s+$/, "");
    // Always a space after a list marker (`- $eq$`). Dropping it when the
    // line already ended in whitespace produced `-$eq$`, which CommonMark
    // does not treat as a list item.
    out[out.length - 1] = `${prev} ${piece}`;
    return;
  }
  out.push(piece);
}

/** `-` / `1.` with no body — the empty bullet a following ```math used to hide. */
function isBareListMarkerLine(line: string): boolean {
  return /^\s*(?:[-*•]|\d+[.)])\s*$/.test(line);
}

function lastNonemptyLine(lines: string[]): string | undefined {
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    if (lines[i]!.trim() !== "") return lines[i];
  }
  return undefined;
}

/**
 * Models put `$2+Y$` / `Y` in ```math (or an untagged fence). Those parse as
 * block cards — a gray box that splits the sentence. Fold short one-liners
 * back into `$...$`. Keep ```answer finals and multi-line display math.
 */
export function inlineShortMathFences(content: string): string {
  const lines = content.split("\n");
  const out: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const open = readFenceMarker(lines[i]!);
    const lang = open?.info.split(/\s/)[0] ?? "";
    if (!open || !INLINE_MATH_FENCE_INFO.test(lang)) {
      out.push(lines[i]!);
      i += 1;
      continue;
    }
    const body: string[] = [];
    let j = i + 1;
    while (j < lines.length && !isFenceCloser(lines[j]!, open)) {
      body.push(lines[j]!);
      j += 1;
    }
    if (j >= lines.length) {
      out.push(lines[i]!);
      i += 1;
      continue;
    }
    const raw = body.join("\n").trim();
    const keepAnswer = isAnswerLang(lang) && looksLikeMathAnswer(raw);
    const keepCode = !lang && looksLikeCode(raw);
    const host = lastNonemptyLine(out);
    const listInline =
      host != null &&
      isBareListMarkerLine(host) &&
      shouldInlineMathFenceOnBareListMarker(raw);
    if (
      keepAnswer ||
      keepCode ||
      !(listInline || shouldRenderMathFenceInline(raw))
    ) {
      for (let k = i; k <= j; k += 1) out.push(lines[k]!);
      i = j + 1;
      continue;
    }
    appendInlineMath(out, stripRedundantDollarWrap(raw));
    i = j + 1;
    while (i < lines.length && lines[i]!.trim() === "") i += 1;
    if (i < lines.length && isSafeInlineMathTail(lines[i]!.trim())) {
      const tail = lines[i]!.trim();
      const last = out[out.length - 1] ?? "";
      out[out.length - 1] = last + (last.endsWith(" ") ? "" : " ") + tail;
      i += 1;
    }
  }
  return out.join("\n");
}

/**
 * A line that is safe to merge onto the preceding inlined math fence —
 * starts with a punctuation character that continues the sentence (`?`, `!`,
 * `,`, `.`, `;`, `:`) but is NOT a structural markdown element (heading,
 * list item, image, table row, or blockquote).
 */
function isSafeInlineMathTail(t: string): boolean {
  if (!/^[?!,.;:]/.test(t)) return false;
  if (/^#{1,6}\s/.test(t)) return false; // heading
  if (/^[-*+]\s/.test(t)) return false; // unordered list item
  if (/^\d+\.\s/.test(t)) return false; // ordered list item
  if (/^!\[/.test(t)) return false; // image
  if (/^\|/.test(t)) return false; // table row
  if (/^>\s?/.test(t)) return false; // blockquote / callout
  return true;
}

export { closeInterruptedMathFences };
