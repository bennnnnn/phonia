/** Port of mobile GFM table normalize + swallowed-fence split (linear scans). */

export type FenceSpan = {
  lang: string;
  body: string;
  start: number;
  end: number;
};

const SKIP_SPLIT_LANGS = new Set([
  "email",
  "sms",
  "social",
  "chart",
  "vega",
  "vega-lite",
  "plot",
  "mermaid",
  "geometry",
  "graph",
  "smiles",
  "chemistry",
  "chem_scene",
  "arithmetic",
  "simulation",
  "molecule",
  "molecule3d",
  "mol3d",
  "3dmol",
  "sources",
  "places",
  "tip",
  "note",
  "warning",
  "info",
  "important",
  "callout",
  "answer",
  "result",
  "final",
  "math",
  "html",
  "htm",
]);

function isPipeRow(line: string): boolean {
  const t = line.trim();
  return t.includes("|") && /^\|.+\|$/.test(t);
}

function isDividerLine(line: string): boolean {
  const compact = line.trim().replace(/\s+/g, "");
  return compact.length >= 3 && /^[-–—_=*~]+$/.test(compact);
}

function splitPipesOutsideMath(line: string): string[] {
  const cells: string[] = [];
  let buf = "";
  let inMath = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
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

function isLoosePipeRow(line: string): boolean {
  const t = line.trim();
  if (!t.includes("|") || isDividerLine(t)) return false;
  const cells = splitPipesOutsideMath(t)
    .map((c) => c.trim())
    .filter((c) => c.length > 0);
  return cells.length >= 2;
}

function isTableRow(line: string): boolean {
  return isPipeRow(line) || isLoosePipeRow(line);
}

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

function readFenceMarker(line: string): { char: "`" | "~"; len: number; info: string } | null {
  let i = 0;
  while (i < line.length && i < 3 && line[i] === " ") i += 1;
  const char = line[i];
  if (char !== "`" && char !== "~") return null;
  let len = 0;
  while (i < line.length && line[i] === char) {
    len += 1;
    i += 1;
  }
  if (len < 3) return null;
  return { char, len, info: line.slice(i).trim() };
}

function isTableDebrisDivider(prev: string | undefined, next: string | undefined): boolean {
  return Boolean(prev && next && isTableRow(prev) && isTableRow(next));
}

function isSeparatorRow(line: string): boolean {
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

  const out: string[] = [strict[0]!];
  if (strict.length > 1 && isSeparatorRow(strict[1]!)) {
    out.push(strict[1]!, ...strict.slice(2));
  } else {
    out.push(separatorForHeader(strict[0]!), ...strict.slice(1));
  }
  return out;
}

/** Strip ASCII dividers, normalize loose pipe rows, build valid GFM tables. */
export function normalizeMarkdownTables(content: string): string {
  const lines = content
    .split("\n")
    .filter((line) => !/^\+[-=+]+\+$/.test(line.trim()));
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
    const line = lines[i]!;
    const marker = readFenceMarker(line);

    if (openFence) {
      if (
        marker &&
        marker.char === openFence.char &&
        marker.len >= openFence.len &&
        marker.info === ""
      ) {
        openFence = null;
      }
      fixed.push(line);
      continue;
    }

    if (marker) {
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

/** Pull a GFM table back out of a code fence that swallowed it. */
export function splitSwallowedCodeFenceTables(
  markdown: string,
  fences: FenceSpan[],
): string {
  if (fences.length === 0) return markdown;
  const parts: string[] = [];
  let cursor = 0;
  for (const fence of fences) {
    parts.push(markdown.slice(cursor, fence.start));
    const lang = fence.lang.toLowerCase();
    if (!SKIP_SPLIT_LANGS.has(lang)) {
      const split = splitCodeFenceAroundPipeTable(lang, fence.body.replace(/\n$/, "").trim());
      if (split != null) {
        parts.push(split);
        cursor = fence.end;
        continue;
      }
    }
    parts.push(markdown.slice(fence.start, fence.end));
    cursor = fence.end;
  }
  parts.push(markdown.slice(cursor));
  return parts.join("");
}
