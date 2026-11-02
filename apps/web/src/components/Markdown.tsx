import { useMemo } from "react";
import { Marked } from "marked";
import DOMPurify from "dompurify";

import { prepareAssistantMarkdown } from "@/lib/assistantMarkdown";
import { renderFencedCodeHtml } from "@/lib/codeFenceHtml";

// Plain markdown rendering for assistant text (slice 1). No KaTeX, Mermaid,
// Vega, or HTML iframe — those rich fences come in a later slice. Known JSON
// fences (sources, places, graph, chart, …) are replaced with a short human
// label before parse so the bubble never dumps transport JSON.
//
// chat-ux-bans: assistant bodies are NOT folded (no Show more / Show less).
// The full body is rendered inline.
const parser = new Marked({ breaks: true, gfm: true });
parser.use({
  renderer: {
    code(token) {
      return renderFencedCodeHtml(token.text, token.lang);
    },
  },
});

const SANITIZE_CONFIG = {
  ALLOWED_TAGS: [
    "p", "br", "hr", "strong", "em", "del", "code", "pre",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "blockquote",
    "a", "span",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td",
    "img",
  ],
  ALLOWED_ATTR: [
    "href", "target", "rel",
    "src", "alt", "title",
    "colspan", "rowspan",
  ],
};

function isSafeHref(value: string): boolean {
  try {
    const parsed = new URL(value, "https://example.invalid");
    return (
      parsed.protocol === "http:" ||
      parsed.protocol === "https:" ||
      parsed.protocol === "mailto:"
    );
  } catch {
    return false;
  }
}

if (typeof window !== "undefined") {
  DOMPurify.addHook("afterSanitizeAttributes", (node) => {
    if (node.tagName === "A") {
      const href = node.getAttribute("href") ?? "";
      if (href && !isSafeHref(href)) {
        node.removeAttribute("href");
      } else {
        node.setAttribute("target", "_blank");
        node.setAttribute("rel", "noopener noreferrer");
      }
    }
    if (node.tagName === "IMG") {
      const src = node.getAttribute("src") ?? "";
      if (!src || !isSafeHref(src) || src.toLowerCase().startsWith("mailto:")) {
        node.removeAttribute("src");
      }
    }
  });
}

function renderMarkdown(markdown: string): string {
  const prepared = prepareAssistantMarkdown(markdown);
  const rawHtml = parser.parse(prepared, { async: false }) as string;
  return DOMPurify.sanitize(rawHtml, SANITIZE_CONFIG) as unknown as string;
}

export function Markdown({ content }: { content: string }) {
  const html = useMemo(() => renderMarkdown(content), [content]);
  return (
    <div
      className="markdown"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
