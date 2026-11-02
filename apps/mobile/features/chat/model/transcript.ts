import { Message } from "@/lib/api";
import i18n from "@/lib/i18n";
import { markdownToDocumentText, type DocumentBlock, type DocumentTarget } from "@/lib/markdown/document";
import { isPdfContentType, parseUserMessageContent } from "@/lib/messageAttachments";

/**
 * What the user sent, as the chat shows it: their words, and each attachment by kind.
 * Never the server's markers (`[File: /attachments/…]`) or a file's extracted text.
 */
function userTurnText(content: string): string {
  const parsed = parseUserMessageContent(content);
  const attached = [
    ...parsed.images.map(() => i18n.t("share.attachment_photo")),
    ...parsed.files.map((file) =>
      isPdfContentType(file.contentType)
        ? i18n.t("share.attachment_pdf")
        : i18n.t("share.attachment_file"),
    ),
  ];
  if (attached.length === 0 && parsed.hasFileAttachment) {
    attached.push(i18n.t("share.attachment_file"));
  }
  return [parsed.caption, ...attached].filter((part) => part.trim()).join("\n");
}

function blockLabel(block: DocumentBlock): string {
  return i18n.t(`share.block_${block}`);
}

/** Markdown body of a chat (no title heading) — used by share and PDF export. */
export function conversationMarkdownBody(
  messages: Message[],
  target: DocumentTarget = "share",
): string {
  return messages
    .filter((m) => m.role !== "system")
    .map((m) => {
      const user = m.role === "user";
      const text = user
        ? userTurnText(m.content)
        : markdownToDocumentText(m.content, blockLabel, target);
      if (!text) return "";
      const role = i18n.t(user ? "share.role_user" : "share.role_assistant");
      return `**${role}:**\n${text}`;
    })
    .filter(Boolean)
    .join("\n\n");
}

/** Full markdown transcript including a title heading. */
export function conversationTranscript(title: string | null, messages: Message[]): string {
  const header = `# ${title?.trim() || i18n.t("share.default_title")}\n\n`;
  return header + conversationMarkdownBody(messages);
}
