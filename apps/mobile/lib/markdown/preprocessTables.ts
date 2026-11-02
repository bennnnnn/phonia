import { isHtmlFenceLang, parseFenceLang } from "@/lib/codeHighlight";
import {
  isAnswerLang,
  isExplicitCodeLang,
  looksLikeCode,
  looksLikeMathAnswer,
  shouldRenderAsPlainProseFence,
} from "@/lib/copyBlock";
import { allowsContentHeuristic } from "@/lib/fenceDispatch";
import { readInlineMathSpan } from "@/lib/markdown/inlineMath";
import { looksLikeMarkdownListProse } from "@/lib/markdown/preprocessNormalize";
import { closesFence, mapClosedFences, readFenceMarker } from "@/lib/mdFenceScan";
import { isStructuredFenceLang } from "@/lib/richBlocks";

/** A ```markdown / ```md / ```table fence that only holds a pipe table. */
const TABLE_FENCE_LANGS: ReadonlySet<string> = new Set(["markdown", "md", "table"]);

function isPipeRow(line: string): boolean {
  const t = line.trim();
  return t.includes("|") && /^\|.+\|$/.test(t);
}

export function isLoosePipeRow(line: string): boolean {
  const t = line.trim();
  if (!t.includes("|") || isDividerLine(t)) return false;
  const cells = splitPipesOutsideMath(t)
    .map((c) => c.trim())
    .filter((c) => c.length > 0);
  return cells.length >= 2;
}

/** GFM tables split on `|`; bars inside explicit math must not count as columns. */
function splitPipesOutsideMath(line: string): string[] {
  const cells: string[] = [];
  let buf = "";
  let inMath = false;
  for (let i = 0; i < line.length; i += 1) {
    const span = readInlineMathSpan(line, i, true);
    if (span) {
      buf += line.slice(i, span.end);
      i = span.end - 1;
      continue;
    }
    const ch = line[i];
    // Preserve the existing unfinished-dollar guard for streaming text.
    if (ch === "$") {
      inMath = !inMath;
      buf += ch;
      continue;
    }
    if (ch === "|" && !inMath) {
      cells.push(buf);
      buf = "";
      continue;
    }
    buf += ch;
  }
  cells.push(buf);
  return cells;
}

export function isTableRow(line: string): boolean {
  return isPipeRow(line) || isLoosePipeRow(line);
}

/** Drop cell fences and HTML breaks so a comparison row stays a table row. */
function sanitizeTableRow(line: string): string {
  let s = "";
  let i = 0;
  while (i < line.length) {
    if (line[i] === "<" && line.slice(i, i + 3).toLowerCase() === "<br") {
      let j = i + 3;
      while (j < line.length && line[j] !== ">") j += 1;
      if (j < line.length && line[j] === ">") {
        s += " ";
        i = j + 1;
        continue;
      }
    }
    if (line.startsWith("```", i)) {
      i += 3;
      while (i < line.length && /[\w-]/.test(line[i]!)) i += 1;
      continue;
    }
    s += line[i];
    i += 1;
  }
  return s;
}

/** Lines the model uses instead of proper table rows: ---, ___, ===, etc. */
function isDividerLine(line: string): boolean {
  // Collapse whitespace first — avoid nested `(\s*[-–—_=*~]\s*){3,}` (js/redos).
  const compact = line.trim().replace(/\s+/g, "");
  return compact.length >= 3 && /^[-–—_=*~]+$/.test(compact);
}

/** `---` between two pipe rows is a fake separator; keep it as an hr / setext otherwise. */
function isTableDebrisDivider(prev: string | undefined, next: string | undefined): boolean {
  return Boolean(prev && next && isTableRow(prev) && isTableRow(next));
}

function isSeparatorRow(line: string): boolean {
  // Avoid nested `\s*` / `-+\s*` quantifiers (CodeQL js/redos). Collapse
  // whitespace first, then match a strict pipe + dashes (+ optional colons).
  const compact = line.trim().replace(/\s+/g, "");
  return /^\|(:?-+:?\|)+$/.test(compact) && compact.includes("-");
}

function toStrictPipeRow(line: string): string {
  const t = line.trim();
  if (isPipeRow(t)) return t;
  let parts = splitPipesOutsideMath(t).map((c) => c.trim());
  if (parts[0] === "") parts = parts.slice(1);
  if (parts[parts.length - 1] === "") parts = parts.slice(0, -1);
  return `| ${parts.join(" | ")} |`;
}

function separatorForHeader(headerLine: string): string {
  const strict = toStrictPipeRow(headerLine);
  const cols = splitPipesOutsideMath(strict).filter((c) => c.trim().length > 0);
  return `|${cols.map(() => " --- ").join("|")}|`;
}

function isGhostTableRow(line: string): boolean {
  if (!isTableRow(line)) return false;
  const strict = toStrictPipeRow(line);
  const cells = splitPipesOutsideMath(strict)
    .map((c) => c.trim())
    .filter((c) => c.length > 0);
  return cells.length > 0 && cells.every((c) => /^[-–—_]+$/.test(c));
}

function finalizePipeTable(rows: string[]): string[] {
  const strict = rows.map(toStrictPipeRow).filter((r) => !isGhostTableRow(r));
  if (strict.length < 2) return rows;

  const out: string[] = [strict[0]];
  if (strict.length > 1 && isSeparatorRow(strict[1])) {
    out.push(strict[1], ...strict.slice(2));
  } else {
    out.push(separatorForHeader(strict[0]), ...strict.slice(1));
  }
  return out;
}

/** Strip ASCII dividers, normalize loose pipe rows, build valid GFM tables. */
export function normalizeMarkdownTables(content: string): string {
  let out = content;

  out = mapClosedFences(out, (info, body, original) => {
    const rows = body.split("\n");
    const table = TABLE_FENCE_LANGS.has(parseFenceLang(info)) && rows.length >= 2;
    return table && rows.every((row) => row.includes("|")) ? `\n${body.trim()}\n` : original;
  });

  const lines = out.split("\n");
  const fixed: string[] = [];
  let tableBuffer: string[] = [];
  let openFence: { char: "`" | "~"; len: number } | null = null;

  const flushTable = () => {
    if (tableBuffer.length >= 2) {
      fixed.push(...finalizePipeTable(tableBuffer));
    } else {
      fixed.push(...tableBuffer);
    }
    tableBuffer = [];
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const marker = readFenceMarker(line);

    if (openFence) {
      if (marker && closesFence(marker, openFence)) openFence = null;
      fixed.push(line);
      continue;
    }

    if (marker) {
      // Cell leftovers (` ``` | ```java`) look like fence openers but are
      // table-row tails. Treat them as rows so the next GFM table is not
      // swallowed as fence body.
      if (marker.info.includes("|")) {
        const asRow = sanitizeTableRow(line.split("```").join(""));
        if (isTableRow(asRow)) tableBuffer.push(asRow);
        continue;
      }
      flushTable();
      openFence = { char: marker.char, len: marker.len };
      fixed.push(line);
      continue;
    }

    if (/^\+[-=+]+\+$/.test(line.trim())) {
      continue;
    }

    if (isDividerLine(line) && isTableDebrisDivider(lines[i - 1], lines[i + 1])) {
      continue;
    }

    if (isTableRow(line)) {
      if (isGhostTableRow(line)) continue;
      tableBuffer.push(sanitizeTableRow(line));
      continue;
    }

    flushTable();
    fixed.push(line);
  }
  flushTable();

  return fixed.join("\n");
}

/** True when fenced/plain content is a GFM pipe table (not prose). */
export function isPipeTable(content: string): boolean {
  const normalized = normalizeMarkdownTables(content);
  const lines = normalized
    .trim()
    .split("\n")
    .filter((l) => l.trim());
  if (lines.length < 2) return false;
  const pipeRows = lines.filter(isPipeRow);
  return pipeRows.length >= 2 && pipeRows.length / lines.length >= 0.6;
}

/**
 * A ```python fence that ate a GFM table (cell ```python closer never
 * matched, so "Use Cases" landed in the code block). Split the table back
 * out; keep a leading snippet fenced if there is one.
 */
function splitCodeFenceAroundPipeTable(lang: string, body: string): string | null {
  const lines = body.split("\n");
  let tableAt = -1;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i] ?? "";
    if (!isTableRow(line)) continue;
    let hasSep = false;
    const end = Math.min(lines.length, i + 12);
    for (let j = i; j < end; j++) {
      if (isSeparatorRow(lines[j] ?? "")) {
        hasSep = true;
        break;
      }
    }
    if (!hasSep) continue;
    tableAt = i;
    break;
  }
  if (tableAt < 0) return null;
  let start = tableAt;
  while (start > 0) {
    const prev = (lines[start - 1] ?? "").trim();
    if (prev === "" || /^#{1,6}\s/.test(prev) || isTableRow(lines[start - 1] ?? "")) {
      start -= 1;
      continue;
    }
    break;
  }
  const code = lines.slice(0, start).join("\n").trim();
  const markdown = normalizeMarkdownTables(lines.slice(start).join("\n").trim());
  const codeBlock = code.length > 0 ? `\`\`\`${lang}\n${code}\n\`\`\`\n\n` : "";
  return `\n${codeBlock}${markdown}\n`;
}

/**
 * Hoist prose/table fences into inline markdown so we never nest `<Markdown>` inside
 * fence render rules (that caused stack overflows and stripped formatting).
 */
export function unwrapNonCodeFences(content: string): string {
  return mapClosedFences(content, (info, body, original) => {
    const lang = parseFenceLang((info || "").trim());
    const l = lang.toLowerCase();
    if (isStructuredFenceLang(l) || l === "math" || isHtmlFenceLang(l)) {
      return original;
    }

    const trimmed = body.replace(/\n$/, "").trim();

    // Drop empty/whitespace fences — they render as blank gray boxes.
    if (!trimmed) return "";

    if (/^\$\)?\s*$/.test(trimmed)) return "";

    if (trimmed.startsWith("$$)\n") || trimmed.startsWith("$)\n")) {
      return `\n\n${trimmed.replace(/^\$\)?\s*\n?/, "")}\n\n`;
    }

    // A final-answer-shaped body (bare number, simplified expression, short
    // assignment) must stay a real fence so renderFence routes it to
    // AnswerBlock — shouldRenderAsPlainProseFence below has no concept of
    // "this looks like a math answer" and would otherwise unwrap it into
    // plain prose text before it ever reaches that dispatch.
    if (
      isAnswerLang(lang) ||
      (allowsContentHeuristic(lang) && looksLikeMathAnswer(trimmed))
    ) {
      return original;
    }

    const taggedLiteral = l === "text" || l === "plain";
    if (!isExplicitCodeLang(lang) && !taggedLiteral) {
      const splitTable = splitCodeFenceAroundPipeTable(lang, trimmed);
      if (splitTable != null) return splitTable;
    }

    if (isExplicitCodeLang(lang) || looksLikeCode(trimmed)) {
      return original;
    }

    if (isPipeTable(trimmed)) {
      if (taggedLiteral) return original;
      return `\n${normalizeMarkdownTables(trimmed)}\n`;
    }

    if (taggedLiteral && /^\+[-=+]+\+$/m.test(trimmed)) {
      return original;
    }

    if (shouldRenderAsPlainProseFence(lang, trimmed)) {
      return `\n\n${trimmed}\n\n`;
    }

    if (looksLikeMarkdownListProse(trimmed)) {
      return `\n\n${trimmed}\n\n`;
    }

    return original;
  });
}
