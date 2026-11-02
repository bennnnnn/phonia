import { parseUserMessageContent } from "@/lib/messageAttachments";

type ChatTitleDisplayOptions = {
  /** True while waiting for auto-generated title after first exchange. */
  generating?: boolean;
};

const TITLE_QUOTES = new Set([`"`, `'`, `\u201c`, `\u201d`, `\u2018`, `\u2019`]);
const TITLE_TRAIL_PUNCT = new Set([".", "!", "?", ",", ";", ":"]);

function stripEdgeQuotes(value: string): string {
  let start = 0;
  let end = value.length;
  while (start < end && TITLE_QUOTES.has(value[start]!)) start += 1;
  while (end > start && TITLE_QUOTES.has(value[end - 1]!)) end -= 1;
  return value.slice(start, end);
}

function stripTrailingPunct(value: string): string {
  let end = value.length;
  while (end > 0 && TITLE_TRAIL_PUNCT.has(value[end - 1]!)) end -= 1;
  return value.slice(0, end);
}

/** Strip wrapping quotes + trailing sentence punctuation until stable. */
function unwrapChatTitle(raw: string): string {
  let title = raw.trim();
  for (;;) {
    const prev = title;
    title = stripEdgeQuotes(title).trim();
    title = stripTrailingPunct(title).trim();
    title = stripEdgeQuotes(title).trim();
    if (title === prev) return title;
  }
}

/** Label for chat headers, drawer rows, and search results. */
export function displayChatTitle(
  title: string | null | undefined,
  options: ChatTitleDisplayOptions,
  t: (key: string) => string,
): string {
  const trimmed = title ? unwrapChatTitle(title) : "";
  if (trimmed) return trimmed;
  if (options.generating) return t("chat.title_generating");
  return t("common.untitled");
}

const PROVISIONAL_TITLE_MAX = 48;

function truncateTitle(title: string): string {
  if (title.length <= PROVISIONAL_TITLE_MAX) return title;
  return `${title.slice(0, PROVISIONAL_TITLE_MAX - 1).trimEnd()}…`;
}

/** Fallback from the first user line (tests). Drawer titles use the topic job. */
export function provisionalChatTitle(text: string | undefined): string | null {
  if (!text?.trim()) return null;
  const parsed = parseUserMessageContent(text);
  const caption = unwrapChatTitle(parsed.caption.split("\n")[0] ?? "");
  if (caption) return truncateTitle(caption);
  if (parsed.images.length > 0) return "Image";
  if (parsed.files.length > 0 || parsed.hasFileAttachment) return "File";
  const line = unwrapChatTitle(text.trim().split("\n")[0] ?? "");
  if (!line) return null;
  return truncateTitle(line);
}

/** Image/File only — never the user's first sentence (that is the topic job). */
export function provisionalAttachmentTitle(text: string | undefined): string | null {
  const label = provisionalChatTitle(text);
  if (label === "Image" || label === "File") return label;
  return null;
}

const PLACEHOLDER_TITLES = new Set(["untitled", "new chat", "chat", "conversation", "new conversation"]);

/** Empty or boring labels still need the topic job. */
export function chatNeedsGeneratedTitle(title: string | null | undefined): boolean {
  const trimmed = unwrapChatTitle(title ?? "").toLowerCase();
  return !trimmed || PLACEHOLDER_TITLES.has(trimmed);
}

/** Trim quotes and enforce max length before PATCH /chats/{id}. */
export function sanitizeManualChatTitle(raw: string): string | null {
  const title = unwrapChatTitle(raw);
  if (!title || title.length > 80) return null;
  return title;
}
