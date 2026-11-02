import type { Message } from "@/lib/api";
import { printHtmlToSharedPdf } from "@/features/chat/model/exportPdf";
import i18n from "@/lib/i18n";
import { markdownToStructuredPrintHtml } from "@/features/chat/model/printDocument";
import { NothingToExportError } from "@/features/chat/model/nothingToExport";
import { conversationMarkdownBody } from "@/features/chat/model/transcript";

async function exportMessageAsPdf(title: string, markdown: string): Promise<void> {
  const html = await markdownToStructuredPrintHtml(title, markdown);
  await printHtmlToSharedPdf(html, title);
}

/** Print the full thread (user + assistant turns) as a PDF. */
export async function exportConversationAsPdf(
  title: string | null,
  messages: Message[],
): Promise<void> {
  const heading = title?.trim() || i18n.t("chat.export_pdf_default_title");
  const body = conversationMarkdownBody(messages, "print");
  if (!body.trim()) throw new NothingToExportError();
  await exportMessageAsPdf(heading, body);
}
