/** Build print-ready HTML documents for PDF export. */

import katex from "katex";

import { splitAnswerNotation } from "@/lib/answerNotation";
import { parseFenceLang } from "@/lib/codeHighlight";
import { fenceIdForLang, isMathFenceLang } from "@/lib/fenceRegistry";
import { fenceAfterLine, readFenceMarker } from "@/lib/mdFenceScan";
import { preprocessMarkdown, splitInlineMath } from "@/lib/markdown/preprocess";
import { looksLikePipeRow } from "@/lib/markdown/streamTableHold";
import { readVendorLibrary } from "@/lib/vendorAssets";

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

const PRINT_STYLES = `
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: 28px; color: #111827; line-height: 1.55; }
  h1 { font-size: 24px; margin: 0 0 8px; letter-spacing: -0.3px; }
  h2 { font-size: 16px; margin: 22px 0 10px; color: #111827; border-bottom: 1px solid #E5E7EB; padding-bottom: 6px; }
  h3 { font-size: 15px; margin: 14px 0 4px; }
  p { font-size: 14px; margin: 0 0 10px; }
  .meta { font-size: 12px; color: #6B7280; margin: 0 0 18px; }
  .item { margin: 0 0 14px; padding-bottom: 10px; border-bottom: 1px solid #E5E7EB; }
  .item:last-child { border-bottom: none; }
  .def { font-size: 14px; color: #111827; margin: 2px 0; }
  .example { font-size: 13px; color: #6B7280; font-style: italic; margin: 2px 0; }
  .status { font-size: 11px; font-weight: 600; color: #9CA3AF; text-transform: uppercase; letter-spacing: 0.4px; }
  ul, ol { margin: 0 0 12px; padding-left: 22px; }
  li { font-size: 14px; margin: 0 0 4px; }
  pre { background: #F1F5F9; border-radius: 8px; padding: 12px; font-size: 12px; line-height: 1.4; white-space: pre-wrap; word-break: break-word; }
  table { border-collapse: collapse; margin: 0 0 12px; font-size: 13px; }
  th, td { border: 1px solid #E5E7EB; padding: 6px 8px; text-align: left; vertical-align: top; }
  th { background: #F9FAFB; font-weight: 600; }
  .answer { margin: 10px 0 14px; padding: 10px 14px; border: 1px solid #E5E7EB; border-radius: 10px; }
  .answer p, .answer .math-block { margin: 0; }
  code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
  blockquote { margin: 0 0 12px; padding: 8px 12px; border-left: 3px solid #E5E7EB; color: #6B7280; }
  .empty { font-size: 14px; color: #9CA3AF; }
  .math-block { margin: 12px 0; overflow-x: auto; text-align: center; }
  .math-inline { display: inline-block; vertical-align: middle; max-width: 100%; }
  .math-fallback { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; white-space: pre-wrap; }
`;

/** Render LaTeX to KaTeX HTML for print (same engine as in-chat math). */
function renderPrintMathHtml(latex: string, displayMode: boolean): string {
  const trimmed = latex.trim();
  if (!trimmed) return "";
  try {
    if (trimmed.length > 4000) {
      return `<code class="math-fallback">${escapeHtml(trimmed.slice(0, 200))}…</code>`;
    }
    const body = katex.renderToString(trimmed, {
      throwOnError: false,
      displayMode,
      strict: "ignore",
      output: "html",
      maxSize: 20,
      maxExpand: 500,
    });
    const cls = displayMode ? "math-block" : "math-inline";
    return `<span class="${cls}">${body}</span>`;
  } catch {
    return `<code class="math-fallback">${escapeHtml(trimmed)}</code>`;
  }
}

function isPrintMathFenceLang(lang: string): boolean {
  const l = lang.trim().toLowerCase();
  return isMathFenceLang(l) || l === "katex" || l === "asciimath";
}

function wrapPrintDocument(title: string, bodyHtml: string, katexCss: string, meta?: string): string {
  const safeTitle = escapeHtml(title.trim() || "Recall report");
  const metaBlock = meta?.trim()
    ? `<p class="meta">${escapeHtml(meta.trim())}</p>`
    : "";
  return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>${katexCss}
${PRINT_STYLES}</style>
</head>
<body>
  <h1>${safeTitle}</h1>
  ${metaBlock}
  ${bodyHtml}
</body>
</html>`;
}

/**
 * Convert markdown into structured print HTML (headings, lists, code, paragraphs).
 * Math fences and $...$ / \\(...\\) inline math use KaTeX — same as the chat UI —
 * instead of dumping raw LaTeX into <pre>. KaTeX's stylesheet is a vendored asset,
 * read here rather than carried in the JS bundle.
 */
export async function markdownToStructuredPrintHtml(title: string, markdown: string): Promise<string> {
  const body = structuredPrintBody(markdown);
  // Without the stylesheet KaTeX's markup still reads, unstyled; the export goes ahead.
  const katexCss = await readVendorLibrary("katexCss").catch(() => "");
  return wrapPrintDocument(title, body, katexCss);
}

/**
 * A paragraph's lines as one `<p>`: soft breaks join with a space; a line ending in two spaces
 * is a Markdown hard break, so the app shows the next line under it and so does the PDF.
 */
function paragraphHtml(lines: string[]): string {
  const runs: string[][] = [[]];
  for (const line of lines) {
    runs[runs.length - 1]!.push(line.trim());
    if (/ {2,}$/.test(line)) runs.push([]);
  }
  const html = runs.map((run) => run.join(" ").trim()).filter(Boolean).map(inlineMarkdownToHtml);
  return html.length ? `<p>${html.join("<br>")}</p>` : "";
}

function structuredPrintBody(markdown: string): string {
  const prepared = preprocessMarkdown(markdown.replace(/\r\n/g, "\n"));
  const lines = prepared.split("\n");
  const parts: string[] = [];
  let i = 0;
  let paragraph: string[] = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    const html = paragraphHtml(paragraph);
    paragraph = [];
    if (html) parts.push(html);
  };

  while (i < lines.length) {
    const line = lines[i] ?? "";
    const fence = fenceAfterLine(null, line);
    if (fence) {
      flushParagraph();
      const lang = parseFenceLang(readFenceMarker(line)?.info ?? "");
      i += 1;
      const codeLines: string[] = [];
      while (i < lines.length && fenceAfterLine(fence, lines[i] ?? "") != null) {
        codeLines.push(lines[i] ?? "");
        i += 1;
      }
      i += 1; // closing fence
      const body = codeLines.join("\n");
      if (isPrintMathFenceLang(lang)) {
        parts.push(renderPrintMathHtml(body, true));
      } else if (fenceIdForLang(lang) === "answer") {
        parts.push(answerToHtml(body));
      } else {
        const code = escapeHtml(body);
        const langAttr = lang ? ` class="language-${escapeHtml(lang)}"` : "";
        parts.push(`<pre><code${langAttr}>${code}</code></pre>`);
      }
      continue;
    }

    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      const level = Math.min(4, heading[1].length) + 1; // h2–h5 under document h1
      parts.push(`<h${level}>${inlineMarkdownToHtml(heading[2].trim())}</h${level}>`);
      i += 1;
      continue;
    }

    const quote = line.match(/^>\s?(.*)$/);
    if (quote) {
      flushParagraph();
      const quoteLines: string[] = [quote[1]];
      i += 1;
      while (i < lines.length && /^>\s?/.test(lines[i] ?? "")) {
        quoteLines.push((lines[i] ?? "").replace(/^>\s?/, ""));
        i += 1;
      }
      parts.push(`<blockquote><p>${inlineMarkdownToHtml(quoteLines.join(" "))}</p></blockquote>`);
      continue;
    }

    if (looksLikePipeRow(line)) {
      flushParagraph();
      const rows: string[] = [];
      while (i < lines.length && looksLikePipeRow(lines[i] ?? "")) {
        rows.push(lines[i] ?? "");
        i += 1;
      }
      parts.push(pipeTableToHtml(rows));
      continue;
    }

    if (/^\s*[-*+]\s+/.test(line)) {
      flushParagraph();
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i] ?? "")) {
        items.push((lines[i] ?? "").replace(/^\s*[-*+]\s+/, ""));
        i += 1;
      }
      parts.push(`<ul>${items.map((item) => `<li>${inlineMarkdownToHtml(item)}</li>`).join("")}</ul>`);
      continue;
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      flushParagraph();
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i] ?? "")) {
        items.push((lines[i] ?? "").replace(/^\s*\d+\.\s+/, ""));
        i += 1;
      }
      parts.push(`<ol>${items.map((item) => `<li>${inlineMarkdownToHtml(item)}</li>`).join("")}</ol>`);
      continue;
    }

    if (!line.trim()) {
      flushParagraph();
      i += 1;
      continue;
    }

    paragraph.push(line);
    i += 1;
  }
  flushParagraph();

  return parts.join("\n") || `<p class="empty"></p>`;
}

/** An answer card: its maths typeset, or its text when it is chemistry or a sentence. */
function answerToHtml(body: string): string {
  const { notation, body: answer } = splitAnswerNotation(body);
  const inner =
    notation === "chemistry"
      ? `<p>${escapeHtml(answer)}</p>`
      : answer.includes("$")
        ? `<p>${inlineMarkdownToHtml(answer)}</p>`
        : renderPrintMathHtml(answer, true);
  return `<div class="answer">${inner}</div>`;
}

function pipeTableToHtml(rows: string[]): string {
  const parsed = rows.map(splitPipeCells);
  const body = parsed.filter((cells) => !cells.every((c) => /^:?-+:?$/.test(c)));
  if (!body.length) return "";
  const header = body[0] ?? [];
  const rest = body.slice(1);
  const th = header.map((c) => `<th>${inlineMarkdownToHtml(c)}</th>`).join("");
  const tr = rest
    .map((cells) => `<tr>${cells.map((c) => `<td>${inlineMarkdownToHtml(c)}</td>`).join("")}</tr>`)
    .join("");
  return `<table><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table>`;
}

function splitPipeCells(row: string): string[] {
  const raw = row.trim();
  const inner = raw.startsWith("|") ? raw.slice(1) : raw;
  const noTrail = inner.endsWith("|") ? inner.slice(0, -1) : inner;
  return noTrail.split("|").map((cell) => cell.trim());
}

function inlineMarkdownToHtml(text: string): string {
  const segments = splitInlineMath(text);
  return segments
    .map((part) => {
      if (part.type === "math") {
        return renderPrintMathHtml(part.value, false);
      }
      return formatInlineText(part.value);
    })
    .join("");
}

/** Stands in for a code span while emphasis is read, so `proposal_id` keeps its underscore. */
const CODE_SLOT = "\uE000";

function formatInlineText(text: string): string {
  const codes: string[] = [];
  let out = escapeHtml(text).replace(/`([^`]+)`/g, (_match, code: string) => {
    codes.push(`<code>${code}</code>`);
    return `${CODE_SLOT}${codes.length - 1}${CODE_SLOT}`;
  });
  out = out.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, "$1");
  out = out.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  // Emphasis opens and closes at word edges, as in CommonMark: due_at stays a word.
  out = out.replace(/(^|[^\w])__(?!\s)([^_]+?)__(?!\w)/g, "$1<strong>$2</strong>");
  out = out.replace(/(^|[^\w*])\*(?![\s*])([^*]+?)\*(?![\w*])/g, "$1<em>$2</em>");
  out = out.replace(/(^|[^\w])_(?![\s_])([^_]+?)_(?!\w)/g, "$1<em>$2</em>");
  const slot = new RegExp(`${CODE_SLOT}(\\d+)${CODE_SLOT}`, "g");
  return out.replace(slot, (_match, index: string) => codes[Number(index)] ?? "");
}
