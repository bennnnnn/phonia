import { fencedLines } from "@/lib/mdFenceScan";
import { citationAuthor, splitTrailingAttribution } from "@/lib/richBlocks";

// Title uses horizontal whitespace only; body lines are `>[^\n]*` (no ReDoS).
// Inside a list item the marker is indented, and its body lines share that indent.
const CALLOUT_RE =
  /^([ \t]*)>[ \t]*\[!(\w+)\][ \t]*([^\n]*)\n((?:\1>[^\n]*(?:\n|$))*)/gim;
/** A callout card is only `> Note:` or `> Warning:`, top level or inside a list item. */
const CALLOUT_LABEL_LINE =
  /^([ \t]*)>[ \t]*(Note|Warning)[ \t]*:[ \t]*(.*)$/i;
/** Any labeled blockquote ends the previous callout, even when it is not a card. */
const LABELED_BLOCKQUOTE_LINE =
  /^>[ \t]*(Tip|Note|Warning|Important|Info|Hint)[ \t]*:/i;

/** Indent every non-blank line, so a block rewritten inside a list item stays in it. */
function indentLines(text: string, indent: string): string {
  if (!indent) return text;
  return text
    .split("\n")
    .map((line) => (line ? `${indent}${line}` : line))
    .join("\n");
}

export function promoteCalloutBlockquotes(content: string): string {
  const lines = content.split("\n");
  const fenced = fencedLines(content);
  const out: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const current = lines[i] ?? "";
    const match = fenced[i] ? null : CALLOUT_LABEL_LINE.exec(current);
    if (!match) {
      out.push(current);
      i += 1;
      continue;
    }
    // A list item's quote is indented to the item's text; every line we
    // write keeps that indent, or markdown-it ends the list there.
    const indent = match[1] ?? "";
    const kind = (match[2] ?? "").trim().toLowerCase();
    const body: string[] = [];
    const first = (match[3] ?? "").trim();
    if (first) body.push(first);
    i += 1;
    while (i < lines.length) {
      const line = lines[i] ?? "";
      if (!line.startsWith(`${indent}>`)) break;
      const quoted = line.slice(indent.length);
      if (LABELED_BLOCKQUOTE_LINE.test(quoted)) break;
      body.push(quoted.replace(/^>\s?/, ""));
      i += 1;
    }
    out.push(`${indent}> [!${kind}]`);
    for (const line of body) out.push(`${indent}> ${line}`);
    out.push("");
  }
  return out.join("\n");
}

const MIN_PROMOTED_QUOTE_CHARS = 24;
const MAX_PROMOTED_AUTHOR_CHARS = 60;

function collapseWs(s: string): string {
  let out = "";
  let prevSpace = false;
  for (let i = 0; i < s.length; i += 1) {
    const c = s[i] ?? "";
    const space = c === " " || c === "\n" || c === "\t" || c === "\r";
    if (space) {
      if (!prevSpace && out.length > 0) {
        out += " ";
        prevSpace = true;
      }
    } else {
      out += c;
      prevSpace = false;
    }
  }
  return out.trim();
}

function unwrapOuterEmphasis(text: string): string {
  let t = text.trim();
  if (t.length >= 4 && t.startsWith("**") && t.endsWith("**")) {
    t = t.slice(2, -2).trim();
  }
  if (t.length >= 2) {
    const a = t[0];
    const b = t[t.length - 1];
    if ((a === "*" && b === "*") || (a === "_" && b === "_")) {
      t = t.slice(1, -1).trim();
    }
  }
  return t;
}

function isQuoteOpen(ch: string): boolean {
  return ch === '"' || ch === "\u201C";
}

function isQuoteClose(ch: string): boolean {
  return ch === '"' || ch === "\u201D";
}

function isAttrDash(ch: string): boolean {
  return ch === "-" || ch === "\u2014" || ch === "\u2013";
}

function looksLikeAuthor(name: string): boolean {
  if (name.length < 2 || name.length > MAX_PROMOTED_AUTHOR_CHARS) return false;
  const c0 = name.charCodeAt(0);
  if (!((c0 >= 65 && c0 <= 90) || (c0 >= 97 && c0 <= 122))) return false;
  for (let i = 0; i < name.length; i += 1) {
    const ch = name[i] ?? "";
    if (ch === "?" || ch === "!" || ch === ":" || ch === "/") return false;
  }
  return true;
}

/** `"Quote body." - Author` → a `>` blockquote with attribution on its own line. */
function quotedAttributionToBlockquote(raw: string): string | null {
  const t = unwrapOuterEmphasis(collapseWs(raw));
  if (t.length < MIN_PROMOTED_QUOTE_CHARS + 4) return null;
  if (t.startsWith(">") || t.startsWith("#") || t.startsWith("|")) return null;
  if (t.startsWith("- ") || t.startsWith("* ")) return null;
  if (!isQuoteOpen(t[0] ?? "")) return null;

  let close = -1;
  for (let i = t.length - 1; i > 0; i -= 1) {
    if (isQuoteClose(t[i] ?? "")) {
      close = i;
      break;
    }
  }
  if (close <= 1) return null;

  const quote = t.slice(1, close).trim();
  if (quote.length < MIN_PROMOTED_QUOTE_CHARS) return null;

  let rest = t.slice(close + 1).trim();
  if (!rest || !isAttrDash(rest[0] ?? "")) return null;
  rest = rest.slice(1).trim();
  if (!looksLikeAuthor(rest)) return null;

  return `> ${quote}\n>\n> — ${rest}`;
}

/** Promote standalone `"…" - Author` paragraphs into quote-card blockquotes. */
export function promoteQuotedAttributions(content: string): string {
  const lines = content.split("\n");
  const fenced = fencedLines(content);
  const out: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i] ?? "";
    if (fenced[i] || line.trim() === "") {
      out.push(line);
      i += 1;
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && !fenced[i] && (lines[i] ?? "").trim() !== "") {
      para.push(lines[i] ?? "");
      i += 1;
    }
    const promoted = quotedAttributionToBlockquote(para.join(" "));
    if (promoted) {
      out.push(promoted);
    } else {
      out.push(...para);
    }
  }
  return out.join("\n");
}

/** `- Name` / `– Name` on a quote line: a bullet or an en dash, then the rest. */
const DASH_ATTRIBUTION_RE = /^[-\u2013][ \t]+(\S.*)$/u;
/** A quote line that opens a list item: the dash line after it is the next item. */
const LIST_ITEM_LINE_RE = /^(?:[-*+\u2013\u2014]|\d+[.)])[ \t]/u;
const MAX_ATTRIBUTION_CHARS = 80;
const MAX_ATTRIBUTION_NAME_WORDS = 6;
/** Lowercase words that sit inside a capitalised name (Antoine de Saint-Exupéry). */
const NAME_PARTICLES = new Set([
  "al", "bin", "da", "de", "del", "della", "der", "di", "du", "ibn", "la", "le", "van", "von",
]);

/** `Steve Jobs` or `Steve Jobs, Stanford 2005`: a short capitalised name, then any source. */
function looksLikeAttributionName(text: string): boolean {
  if (text.length > MAX_ATTRIBUTION_CHARS) return false;
  const name = (text.split(",")[0] ?? "").trim();
  if (name.length < 2 || name.length > MAX_PROMOTED_AUTHOR_CHARS) return false;
  if (/[?!:/]/.test(name)) return false;
  const words = name.split(/\s+/);
  if (words.length > MAX_ATTRIBUTION_NAME_WORDS) return false;
  if (!/^\p{Lu}/u.test(words[0] ?? "")) return false;
  return words.every((word) => !/^\p{Ll}/u.test(word) || NAME_PARTICLES.has(word));
}

/** The text after a quote line's `>` (and the one space after it). */
function quoteLineBody(line: string, indent: string): string {
  return line.slice(indent.length + 1).replace(/^ /, "");
}

/** The nearest non-blank line of the same quote from `from`, walking by `step`; "" past its edge. */
function nearestQuoteText(lines: string[], from: number, step: 1 | -1, indent: string): string {
  for (let j = from; j >= 0 && j < lines.length; j += step) {
    const line = lines[j] ?? "";
    if (!line.startsWith(`${indent}>`)) return "";
    const text = quoteLineBody(line, indent).trim();
    if (text) return text;
  }
  return "";
}

/**
 * `> – Steve Jobs` / `> - Steve Jobs` closing a quote → `> — Steve Jobs`, the
 * citation the quote card reads. markdown-it parses the hyphen form as a
 * bullet inside the quote, so it never reached the card.
 *
 * Only the quote's last line, only a short capitalised name, and only after
 * a line of quotation: a real list (`> - Eggs` / `> - Milk`, or one item
 * after `Remember to:`) stays a list.
 */
export function normalizeQuoteAttributionDashes(content: string): string {
  const lines = content.split("\n");
  const fenced = fencedLines(content);
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i] ?? "";
    const trimmed = line.trimStart();
    if (fenced[i] || !trimmed.startsWith(">")) continue;
    const indent = line.slice(0, line.length - trimmed.length);
    const dash = DASH_ATTRIBUTION_RE.exec(quoteLineBody(line, indent).trimEnd());
    const name = dash?.[1]?.trim() ?? "";
    if (!name || !looksLikeAttributionName(name)) continue;
    if (nearestQuoteText(lines, i + 1, 1, indent)) continue;
    const before = nearestQuoteText(lines, i - 1, -1, indent);
    if (!before || before.endsWith(":") || LIST_ITEM_LINE_RE.test(before)) continue;
    lines[i] = `${indent}> \u2014 ${name}`;
  }
  return lines.join("\n");
}

/** `> quote. — Author` → attribution on its own blockquote line for QuoteBlock. */
export function splitBlockquoteInlineAttribution(content: string): string {
  const lines = content.split("\n");
  const fenced = fencedLines(content);
  const out: string[] = [];
  for (const [index, line] of lines.entries()) {
    const trimmed = line.trimStart();
    if (fenced[index] || !trimmed.startsWith(">")) {
      out.push(line);
      continue;
    }
    // A quote inside a list item is indented to the item's text. Lines we add
    // keep that indent; an unindented `>` ends the list and starts a new quote.
    const quoteMark = `${line.slice(0, line.length - trimmed.length)}>`;
    let prefixEnd = quoteMark.length;
    if (line[prefixEnd] === " ") prefixEnd += 1;
    const body = line.slice(prefixEnd);
    if (body.startsWith("[!")) {
      out.push(line);
      continue;
    }
    // Consecutive `>` lines are one paragraph, so `-- Name` stayed in the
    // quote. A blank line makes that citation its own author row.
    if (citationAuthor(body)) {
      const prev = out[out.length - 1]?.trim() ?? "";
      if (prev.startsWith(">") && prev !== ">") out.push(quoteMark);
      out.push(line);
      continue;
    }
    const split = splitTrailingAttribution(body);
    if (!split) {
      out.push(line);
      continue;
    }
    out.push(`${quoteMark} ${split.quote}`);
    out.push(quoteMark);
    out.push(`${quoteMark} — ${split.author}`);
  }
  return out.join("\n");
}

function calloutBody(title: string, body: string): string {
  const cleaned = body
    .split("\n")
    .map((line) => line.replace(/^[ \t]*>\s?/, ""))
    .join("\n")
    .trim();
  const heading = title.trim();
  if (heading && cleaned) return `${heading}\n\n${cleaned}`;
  return heading || cleaned;
}

/** Tip / Important / Info / Hint alerts stay prose, not a card. */
function plainBlockquote(text: string, indent: string): string {
  if (!text) return "\n";
  const lines = text.split("\n").map((line) => (line.trim() ? `> ${line}` : ">"));
  return `\n${indentLines(lines.join("\n"), indent)}\n`;
}

export function convertCalloutBlocks(content: string): string {
  return content.replace(
    CALLOUT_RE,
    (_match, indent: string, kind: string, title: string, body: string) => {
      const k = kind.trim().toLowerCase();
      const merged = calloutBody(title, body);
      if (k === "note" || k === "warning") {
        return `\n${indentLines(`\`\`\`callout-${k}\n${merged}\n\`\`\``, indent)}\n`;
      }
      return plainBlockquote(merged, indent);
    },
  );
}
