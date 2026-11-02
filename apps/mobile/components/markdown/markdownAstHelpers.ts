import { citationAuthor, isStandaloneUrl } from "@/lib/richBlocks";

export type AstNode = {
  key: string;
  type?: string;
  content?: string;
  markup?: string;
  attributes?: Record<string, string>;
  children?: AstNode[];
  sourceType?: string;
};

export type AstParent = {
  type: string;
  attributes?: { start?: number; class?: string };
};

export function parentHasType(parent: unknown, type: string): boolean {
  return Array.isArray(parent) && parent.some((node) => node?.type === type);
}

export function immediateAncestorType(parent: unknown): string | undefined {
  if (!Array.isArray(parent) || parent.length === 0) return undefined;
  const first = parent[0] as { type?: string } | undefined;
  return typeof first?.type === "string" ? first.type : undefined;
}

/** Numbers carry order/rank semantics; nested unordered items stay bullets. */
export function shouldNumberListItem(parent: unknown): boolean {
  return immediateAncestorType(parent) === "ordered_list";
}

function isListNodeType(type: string | undefined): boolean {
  return type === "bullet_list" || type === "ordered_list" || type === "list";
}

/** Parent topics with sub-items should not also wear a disc — that reads as two
 *  layers of the same marker (Strengths •, then • Personalized). */
export function listItemHasNestedList(node: AstNode): boolean {
  for (const child of node.children ?? []) {
    if (isListNodeType(child.type)) return true;
    for (const grand of child.children ?? []) {
      if (isListNodeType(grand.type)) return true;
    }
  }
  return false;
}

/** A list item that opens with a bold title on its own line (`**Read widely**`, a break). */
export function listItemOpensWithTitle(node: AstNode): boolean {
  const leaves: AstNode[] = [];
  const walk = (n: AstNode) => {
    if (leaves.length >= 2) return;
    const kids = n.children ?? [];
    if (n.type === "strong" || n.type === "hardbreak" || kids.length === 0) {
      if (n.type !== "text" || n.content) leaves.push(n);
      return;
    }
    kids.forEach(walk);
  };
  walk(node);
  return leaves[0]?.type === "strong" && leaves[1]?.type === "hardbreak";
}

/** The largest number an ordered list shows: its start plus its item count. */
export function listLargestNumber(parent: unknown): number {
  if (!Array.isArray(parent) || parent.length === 0) return 1;
  const list = parent[0] as {
    attributes?: { start?: number };
    children?: unknown[];
  };
  const start =
    typeof list.attributes?.start === "number" ? list.attributes.start : 1;
  return start + Math.max(0, (list.children?.length ?? 1) - 1);
}

/** Body-size digit and period widths in Source Sans 3 (tabular). */
const DIGIT_WIDTH = 8;
const PERIOD_WIDTH = 4;
/** The column 1–99 fit in at the default text size. */
const MIN_NUMBER_COLUMN = 22;

/**
 * Width of a numbered list's marker column: every item in the list uses the
 * width of its largest number at the reader's text size, so "9." and "10."
 * (and "100.") keep their text on one edge.
 */
export function numberColumnWidth(largest: number, fontScale: number): number {
  const digits = String(Math.max(1, Math.floor(largest))).length;
  const needed =
    Math.ceil((digits * DIGIT_WIDTH + PERIOD_WIDTH) * Math.max(1, fontScale)) +
    2;
  return Math.max(MIN_NUMBER_COLUMN, needed);
}

/** Source Sans 3's line box: (ascender 1024 + descender 400) / 1000 em. */
const BODY_LINE_RATIO = 1.424;
const BODY_FONT_SIZE = 16;
const BULLET_SIZE = 6;
/** The disc stops growing here, like a control beside a 44pt target. */
const BULLET_SCALE_MAX = 1.5;

/**
 * The list disc at the reader's text size: a little larger with the text, and
 * centered on the first line, which grows with it. A fixed 8pt drop sat high
 * once the line box was taller than 22pt.
 */
export function bulletDiscMetrics(fontScale: number): {
  size: number;
  top: number;
} {
  const scale = Math.max(1, fontScale);
  const size = Math.round(BULLET_SIZE * Math.min(scale, BULLET_SCALE_MAX));
  const line = BODY_FONT_SIZE * scale * BODY_LINE_RATIO;
  return { size, top: Math.max(0, Math.round((line - size) / 2)) };
}

/**
 * The last item of its list ends flush: the list's own block gap is the space
 * under it, so a list ends like every other block (an item gap on top of it
 * made ~20pt).
 */
export function isLastListItem(parent: unknown, index: number): boolean {
  if (!Array.isArray(parent) || parent.length === 0) return false;
  const list = parent[0] as { children?: unknown[] };
  const count = list.children?.length ?? 0;
  return count > 0 && index === count - 1;
}

/** `node` is a block of the markdown root, after every other one. */
export function isLastRootBlock(node: unknown, ancestors: unknown): boolean {
  if (!Array.isArray(ancestors) || ancestors.length !== 1) return false;
  const blocks = (ancestors[0] as AstNode | undefined)?.children ?? [];
  return blocks.length > 0 && blocks[blocks.length - 1] === node;
}

export function listItemDisplayNumber(parent: unknown, index: number): number {
  if (!Array.isArray(parent) || parent.length === 0) return index + 1;
  const list = parent[0] as { attributes?: { start?: number } };
  const start = list.attributes?.start;
  if (typeof start === "number") return start + index;
  return index + 1;
}

export function inTableCell(parent: unknown): boolean {
  return parentHasType(parent, "td") || parentHasType(parent, "th");
}

export function inTableHeader(parent: unknown): boolean {
  return parentHasType(parent, "th");
}

const HEADING_TYPES = [
  "heading1",
  "heading2",
  "heading3",
  "heading4",
  "heading5",
  "heading6",
] as const;

export function inHeading(parent: unknown): boolean {
  return HEADING_TYPES.some((type) => parentHasType(parent, type));
}

/**
 * The AST fields the render rules read from a node and its children, as one
 * string: two nodes with the same source, in the same place, draw the same.
 */
export function astSource(node: AstNode): string {
  const fields = [node.type, node.content, node.markup, JSON.stringify(node.attributes ?? {})];
  return `${fields.join("\u0001")}[${(node.children ?? []).map(astSource).join("\u0002")}]`;
}

export function astText(node: AstNode): string {
  if (node.content) return node.content;
  return (node.children ?? []).map(astText).join("");
}

/**
 * A blockquote is a quote card only when an earlier line is the quotation and
 * the last line is `— Name`, `– Name` or `-- Name`.
 *
 * `author` is set when that line is its own block (QuoteBlock prints it).
 * It is null when the line already sits inside the quotation paragraph.
 */
export function blockquoteCitation(
  node: AstNode,
): { author: string | null; bodyCount: number } | null {
  const children = node.children ?? [];
  let last = -1;
  for (let i = children.length - 1; i >= 0; i -= 1) {
    if (astTextWithBreaks(children[i]!).trim()) {
      last = i;
      break;
    }
  }
  if (last < 0) return null;
  const lines = nonBlankLines(astTextWithBreaks(children[last]!));
  const author = citationAuthor(lines[lines.length - 1] ?? "");
  if (!author) return null;
  // Dash lines in a row are a list or a dialogue (`– fast` / `– cheap`), not a
  // quotation and its author.
  const quoteLines = nonBlankLines(astTextWithBreaks(node));
  if (citationAuthor(quoteLines[quoteLines.length - 2] ?? "")) return null;
  const quoteInLast = lines.slice(0, -1).join("\n").trim();
  const prior = children
    .slice(0, last)
    .some((child) => astTextWithBreaks(child).trim().length > 0);
  if (!quoteInLast && !prior) return null;
  if (!quoteInLast) return { author, bodyCount: last };
  return { author: null, bodyCount: last + 1 };
}

function nonBlankLines(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

/**
 * Inside a blockquote drawn as indented prose: its text takes the quieter
 * ink. A quote card (a citation) keeps body ink.
 */
export function inPlainBlockquote(parent: unknown): boolean {
  if (!Array.isArray(parent)) return false;
  const quote = parent.find(
    (node) => (node as AstNode | undefined)?.type === "blockquote",
  );
  return quote ? blockquoteCitation(quote as AstNode) === null : false;
}

export function unwrapSingle(node: AstNode): AstNode {
  let current = node;
  while ((current.children?.length ?? 0) === 1) {
    const only = current.children?.[0];
    if (!only || only.type === "text" || only.type === "strong") break;
    current = only;
  }
  return current;
}

/** The bold heading that opens a paragraph, if the paragraph starts with one. */
export function openingStrong(node: AstNode | undefined): AstNode | null {
  if (!node) return null;
  if (node.type === "strong") return node;
  const kids = node.children ?? [];
  return node.type === "textgroup" && kids.length === 1
    ? openingStrong(kids[0])
    : null;
}

/** Like `astText`, but soft/hard breaks and block siblings become newlines. */
export function astTextWithBreaks(node: AstNode): string {
  if (node.type === "softbreak" || node.type === "hardbreak") return "\n";
  if (node.content) return node.content;
  const kids = node.children ?? [];
  if (kids.length === 0) return "";
  const block =
    node.type === "blockquote" ||
    node.type === "bullet_list" ||
    node.type === "ordered_list" ||
    node.type === "list";
  return kids.map(astTextWithBreaks).join(block ? "\n" : "");
}

function collectHtmlInline(nodes: AstNode[] | undefined): string[] {
  const out: string[] = [];
  for (const node of nodes ?? []) {
    if (node.sourceType === "html_inline" || node.type === "html_inline") {
      if (node.content) out.push(node.content);
    }
    out.push(...collectHtmlInline(node.children));
  }
  return out;
}

function isTaskCheckboxChecked(html: string): boolean {
  return /\bchecked(?:\s|=|>|\/)/i.test(html);
}

export function taskChecked(node: AstNode): boolean | null {
  const cls = node.attributes?.class ?? "";
  if (!cls.includes("task-list-item")) return null;
  const checkbox = collectHtmlInline(node.children).find((html) =>
    html.includes("task-list-item-checkbox"),
  );
  if (!checkbox) return false;
  return isTaskCheckboxChecked(checkbox);
}

/**
 * The item's list holds an open task (`- [ ]`), so it is a checklist and a
 * done item is a ticked box. A list of done items only is a run of
 * verified checks (`- [x] For x = 2: …`), which keeps its trailing tick.
 */
export function listHasOpenTask(parent: unknown): boolean {
  if (!Array.isArray(parent) || parent.length === 0) return false;
  const list = parent[0] as AstNode;
  return (list.children ?? []).some((item) => taskChecked(item) === false);
}

export function detectStandaloneLink(node: AstNode): string | null {
  let kids = node.children ?? [];
  // markdown-display flattens inlines then wraps them in `textgroup`.
  while (
    kids.length === 1 &&
    (kids[0].type === "inline" || kids[0].type === "textgroup")
  ) {
    kids = kids[0].children ?? [];
  }
  if (kids.length === 1 && kids[0].type === "link") {
    const href = kids[0].attributes?.href;
    return href && isStandaloneUrl(href) ? href : null;
  }
  if (kids.length === 1 && kids[0].type === "text") {
    return isStandaloneUrl(kids[0].content ?? "");
  }
  return null;
}
