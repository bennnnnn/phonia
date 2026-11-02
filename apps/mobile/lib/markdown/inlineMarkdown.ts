/**
 * Minimal inline-markdown tokenizer for rich-fence bodies.
 *
 * Full MarkdownContent runs the whole preprocess + rich-fence pipeline (heavy,
 * recursive risk inside a fence body). This handles only the inline emphasis
 * that matters in step/callout/collapsible/quote bodies — bold, italic, inline
 * code — so fence bodies can use **bold**, *italic*, and `code` without pulling
 * in the full renderer. Lists/headings inside a fence body are intentionally
 * out of scope.
 */
type InlineToken =
  | { type: "text"; value: string }
  | { type: "bold"; value: string }
  | { type: "italic"; value: string }
  | { type: "code"; value: string };

// Order matters: code first (so `**not bold**` inside code stays literal), then
// bold (`**`), then italic (`*`). Underscore italics are deliberately omitted to
// avoid breaking snake_case identifiers.
const INLINE_RE = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*\n]+\*)/g;

export function parseInlineMarkdown(text: string): InlineToken[] {
  if (!text) return [];
  const tokens: InlineToken[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  INLINE_RE.lastIndex = 0;
  while ((m = INLINE_RE.exec(text)) !== null) {
    const [full, code, bold, italic] = m;
    if (m.index > last) {
      tokens.push({ type: "text", value: text.slice(last, m.index) });
    }
    if (code) tokens.push({ type: "code", value: code.slice(1, -1) });
    else if (bold) tokens.push({ type: "bold", value: bold.slice(2, -2) });
    else if (italic) tokens.push({ type: "italic", value: italic.slice(1, -1) });
    last = m.index + full.length;
    if (full.length === 0) {
      INLINE_RE.lastIndex += 1; // guard against zero-width matches
    }
  }
  if (last < text.length) {
    tokens.push({ type: "text", value: text.slice(last) });
  }
  return tokens;
}
