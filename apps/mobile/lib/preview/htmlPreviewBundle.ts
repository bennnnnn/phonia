/**
 * Bundle same-reply ```html + ```css + ```javascript fences into one document
 * for the sandboxed HTML preview. Relative href/src that match a sibling file
 * are inlined; leftover CSS/JS are appended. No network, no folders, no
 * execution outside the existing WebView sandbox.
 */

import { scanFences } from "@/lib/mdFenceScan";
import { inlineScript } from "@/lib/preview/previewSandbox";

const HTML_PREVIEW_MAX_FILES = 8;
const HTML_PREVIEW_MAX_FILE_CHARS = 80_000;

type PreviewKind = "html" | "css" | "js";

export type PreviewFile = {
  kind: PreviewKind;
  name: string;
  content: string;
};

const DEFAULT_NAME: Record<PreviewKind, string> = {
  html: "index.html",
  css: "styles.css",
  js: "app.js",
};

const EXT_FOR_KIND: Record<PreviewKind, readonly string[]> = {
  html: [".html", ".htm"],
  css: [".css"],
  js: [".js"],
};

function kindForLang(lang: string): PreviewKind | null {
  const l = lang.toLowerCase();
  if (l === "html" || l === "htm" || l === "markup") return "html";
  if (l === "css") return "css";
  if (l === "js" || l === "javascript") return "js";
  return null;
}

function firstToken(text: string): { token: string; rest: string } {
  let i = 0;
  while (i < text.length && text.charCodeAt(i) > 32) i += 1;
  return { token: text.slice(0, i), rest: text.slice(i).trim() };
}

/** Language tag from a fence info string (`html index.html` → `html`). */
export function fenceLangFromInfo(info: string): string {
  const raw = info.trim();
  if (!raw) return "";
  const { token } = firstToken(raw);
  let end = token.length;
  for (let i = 0; i < token.length; i += 1) {
    const ch = token[i];
    if (ch === "{" || ch === "[" || ch === ":") {
      end = i;
      break;
    }
  }
  return token.slice(0, end).toLowerCase();
}

function basenameHint(raw: string): string {
  let name = raw.trim();
  const slash = Math.max(name.lastIndexOf("/"), name.lastIndexOf("\\"));
  if (slash >= 0) name = name.slice(slash + 1);
  return name;
}

function isSafeFilename(name: string): boolean {
  if (name.length < 1 || name.length > 64) return false;
  if (name === "." || name === "..") return false;
  for (let i = 0; i < name.length; i += 1) {
    const c = name.charCodeAt(i);
    const ok =
      (c >= 48 && c <= 57) ||
      (c >= 65 && c <= 90) ||
      (c >= 97 && c <= 122) ||
      c === 46 ||
      c === 45 ||
      c === 95;
    if (!ok) return false;
  }
  return true;
}

function hasExt(name: string, exts: readonly string[]): boolean {
  const lower = name.toLowerCase();
  return exts.some((ext) => lower.endsWith(ext));
}

export function sanitizePreviewFilename(raw: string, kind: PreviewKind): string | null {
  const name = basenameHint(raw);
  if (!isSafeFilename(name)) return null;
  if (!hasExt(name, EXT_FOR_KIND[kind])) return null;
  return name;
}

function uniqueName(kind: PreviewKind, used: Set<string>, preferred: string | null): string {
  const base = preferred ?? DEFAULT_NAME[kind];
  if (!used.has(base.toLowerCase())) return base;
  const dot = base.lastIndexOf(".");
  const stem = dot > 0 ? base.slice(0, dot) : base;
  const ext = dot > 0 ? base.slice(dot) : "";
  for (let n = 2; n < 20; n += 1) {
    const candidate = `${stem}-${n}${ext}`;
    if (!used.has(candidate.toLowerCase())) return candidate;
  }
  return `${stem}-${used.size}${ext}`;
}

/**
 * State for an incremental preview-file scan. While a reply streams, content
 * grows append-only, so each flush rescans just the new suffix (from the
 * opener of the fence that was still open at the last scan) instead of
 * splitting and scanning the whole message every time.
 */
export type PreviewScanState = {
  /** Markdown the scan is based on. */
  source: string;
  /** Char offset to resume from — always at a line start. */
  resumeFrom: number;
  files: PreviewFile[];
  /** The last file came from a fence the line still being written may change (open, or
   *  closed on that line) — it is replaced by the rescan from `resumeFrom` on the next advance. */
  trailingOpen: boolean;
};

type CollectResult = {
  files: PreviewFile[];
  /**
   * Where the next scan starts: the opener of a fence still open (of any language) or
   * closed on the line still being written, else the start of that line (`markdown.length`
   * once the text ends a line). The line may yet become a fence opener or stop being a closer.
   */
  openFenceStart: number;
  trailingOpen: boolean;
};

/**
 * Collect html/css/js fences from `markdown`, appending to `files`/`used`. Fences are read
 * as the renderer reads them (`scanFences`, no regex on the body): an ```html example inside
 * a ```markdown fence is that fence's text, and a ``` line closes only its own fence.
 */
function collectPreviewFilesInto(
  markdown: string,
  files: PreviewFile[],
  used: Set<string>,
): CollectResult {
  const lastLineStart = markdown.lastIndexOf("\n") + 1;
  let openFenceStart = lastLineStart;
  let trailingOpen = false;
  for (const span of scanFences(markdown, true)) {
    // Mid-stream, the next scan resumes at this opener: a scan that started inside
    // the fence would read its closer as an opener.
    const unsettled = !span.closed || span.end > lastLineStart;
    if (unsettled) openFenceStart = Math.min(openFenceStart, span.start);
    if (files.length >= HTML_PREVIEW_MAX_FILES) break;
    const kind = kindForLang(fenceLangFromInfo(span.info));
    if (kind == null) continue;
    const { rest } = firstToken(span.info);
    const hinted = rest ? sanitizePreviewFilename(firstToken(rest).token, kind) : null;
    const content = span.body.replace(/\n$/, "");
    if (!content.trim()) continue;
    // An open fence's partial file is replaced, not duplicated, by the next scan.
    trailingOpen = unsettled;
    const clipped =
      content.length > HTML_PREVIEW_MAX_FILE_CHARS
        ? content.slice(0, HTML_PREVIEW_MAX_FILE_CHARS)
        : content;
    const name = uniqueName(kind, used, hinted);
    used.add(name.toLowerCase());
    files.push({ kind, name, content: clipped });
  }
  return { files, openFenceStart, trailingOpen };
}

/**
 * Advance an incremental scan for grown `markdown`. Append-only growth
 * rescans only the suffix; a non-extending change (new stream, rewrite)
 * resets and scans from scratch.
 */
export function advancePreviewFilesScan(
  prev: PreviewScanState | null,
  markdown: string,
): PreviewScanState {
  let base = prev ?? { source: "", resumeFrom: 0, files: [] as PreviewFile[], trailingOpen: false };
  if (markdown === base.source) return base;
  if (base.resumeFrom > 0 && !markdown.startsWith(base.source.slice(0, base.resumeFrom))) {
    base = { source: "", resumeFrom: 0, files: [], trailingOpen: false };
  }
  const files = base.trailingOpen ? base.files.slice(0, -1) : base.files.slice();
  const used = new Set(files.map((file) => file.name.toLowerCase()));
  const result = collectPreviewFilesInto(markdown.slice(base.resumeFrom), files, used);
  const previous = prev?.files ?? [];
  return {
    source: markdown,
    resumeFrom: base.resumeFrom + result.openFenceStart,
    // Prose streaming past the last fence changes no file: the same array keeps the
    // preview-files context still, so closed HTML blocks do not render again each flush.
    files: sameFiles(previous, result.files) ? previous : result.files,
    trailingOpen: result.trailingOpen,
  };
}

function sameFiles(a: readonly PreviewFile[], b: readonly PreviewFile[]): boolean {
  return (
    a.length === b.length &&
    a.every((file, index) => {
      const other = b[index];
      return (
        file === other ||
        (file.kind === other.kind && file.name === other.name && file.content === other.content)
      );
    })
  );
}

function attrValue(tag: string, attr: string): string | null {
  const needle = `${attr}=`;
  const lower = tag.toLowerCase();
  const at = lower.indexOf(needle);
  if (at < 0) return null;
  let i = at + needle.length;
  while (i < tag.length && (tag[i] === " " || tag[i] === "\t")) i += 1;
  if (i >= tag.length) return null;
  const quote = tag[i];
  if (quote === '"' || quote === "'") {
    const end = tag.indexOf(quote, i + 1);
    if (end < 0) return null;
    return tag.slice(i + 1, end).trim();
  }
  let end = i;
  while (end < tag.length && tag.charCodeAt(end) > 32 && tag[end] !== ">") end += 1;
  return tag.slice(i, end).trim();
}

function findTag(html: string, tagName: string, from: number): { start: number; end: number } | null {
  const open = `<${tagName}`;
  const lower = html.toLowerCase();
  let i = from;
  while (i < html.length) {
    const at = lower.indexOf(open, i);
    if (at < 0) return null;
    const after = html[at + open.length] ?? "";
    const afterCode = after.charCodeAt(0);
    const nameContinues =
      (afterCode >= 65 && afterCode <= 90) ||
      (afterCode >= 97 && afterCode <= 122) ||
      (afterCode >= 48 && afterCode <= 57);
    if (nameContinues) {
      i = at + open.length;
      continue;
    }
    const gt = html.indexOf(">", at);
    if (gt < 0) return null;
    return { start: at, end: gt + 1 };
  }
  return null;
}

function lookupFile(files: Map<string, PreviewFile>, href: string): PreviewFile | undefined {
  const name = basenameHint(href).toLowerCase();
  if (!name || name.includes(":") || name === "." || name === "..") return undefined;
  return files.get(name);
}

function insertBeforeClose(html: string, tag: string, snippet: string): string {
  const close = `</${tag}>`;
  const at = html.toLowerCase().lastIndexOf(close);
  if (at < 0) return html + snippet;
  return html.slice(0, at) + snippet + html.slice(at);
}

function escapeStyle(source: string): string {
  return inlineScript(source).split("</style").join("<\\/style").split("</STYLE").join("<\\/STYLE");
}

/** Inline sibling CSS/JS into an HTML entry. Identity when there are no extras. */
export function bundleHtmlPreview(entryHtml: string, files: PreviewFile[]): string {
  if (!files.some((f) => f.kind === "css" || f.kind === "js")) {
    return entryHtml;
  }
  const byName = new Map<string, PreviewFile>();
  for (const file of files) {
    byName.set(file.name.toLowerCase(), file);
  }
  const used = new Set<string>();
  let html = entryHtml;

  let search = 0;
  for (let guard = 0; guard < 32; guard += 1) {
    const tag = findTag(html, "link", search);
    if (!tag) break;
    const raw = html.slice(tag.start, tag.end);
    const href = attrValue(raw, "href");
    const rel = (attrValue(raw, "rel") ?? "").toLowerCase();
    const file = href ? lookupFile(byName, href) : undefined;
    if (file && file.kind === "css" && (rel === "stylesheet" || rel === "")) {
      const style = `<style>\n${escapeStyle(file.content)}\n</style>`;
      html = html.slice(0, tag.start) + style + html.slice(tag.end);
      used.add(file.name.toLowerCase());
      search = tag.start + style.length;
      continue;
    }
    search = tag.end;
  }

  search = 0;
  for (let guard = 0; guard < 32; guard += 1) {
    const tag = findTag(html, "script", search);
    if (!tag) break;
    const raw = html.slice(tag.start, tag.end);
    const src = attrValue(raw, "src");
    const file = src ? lookupFile(byName, src) : undefined;
    if (file && file.kind === "js") {
      let end = tag.end;
      const lower = html.toLowerCase();
      const closeAt = lower.indexOf("</script", tag.end);
      if (closeAt >= 0) {
        const closeGt = html.indexOf(">", closeAt);
        if (closeGt >= 0) end = closeGt + 1;
      }
      const script = `<script>\n${inlineScript(file.content)}\n</script>`;
      html = html.slice(0, tag.start) + script + html.slice(end);
      used.add(file.name.toLowerCase());
      search = tag.start + script.length;
      continue;
    }
    search = tag.end;
  }

  const unusedCss = files.filter((f) => f.kind === "css" && !used.has(f.name.toLowerCase()));
  const unusedJs = files.filter((f) => f.kind === "js" && !used.has(f.name.toLowerCase()));
  const styles = unusedCss
    .map((f) => `<style>\n${escapeStyle(f.content)}\n</style>`)
    .join("\n");
  const scripts = unusedJs
    .map((f) => `<script>\n${inlineScript(f.content)}\n</script>`)
    .join("\n");
  return appendUnused(html, styles, scripts);
}

function appendUnused(html: string, styles: string, scripts: string): string {
  let out = html;
  if (styles) {
    if (out.toLowerCase().includes("</head>")) {
      out = insertBeforeClose(out, "head", styles);
    } else if (out.toLowerCase().includes("<html")) {
      out = insertBeforeClose(out, "html", `<head>${styles}</head>`);
    } else {
      out = `${styles}\n${out}`;
    }
  }
  if (scripts) {
    if (out.toLowerCase().includes("</body>")) {
      out = insertBeforeClose(out, "body", scripts);
    } else {
      out = `${out}\n${scripts}`;
    }
  }
  return out;
}

export function previewHasSiblingAssets(files: PreviewFile[]): boolean {
  return files.some((f) => f.kind === "css" || f.kind === "js");
}
