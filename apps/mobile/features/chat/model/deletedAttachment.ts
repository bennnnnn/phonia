import type { Message } from "@/lib/api";
import { stripAttachmentMarkers } from "@/lib/messageAttachments";

/**
 * The chat's rows once an attachment is deleted from Library: its markers go, and a
 * row they were all of goes too, as on the server. A row that changed drops its local
 * previews, which may have stood for the deleted file; the markers left draw the rest.
 */
export function withoutDeletedAttachment(messages: Message[], attachmentId: string): Message[] {
  let changed = false;
  const next: Message[] = [];
  for (const row of messages) {
    const content = stripAttachmentMarkers(row.content, attachmentId);
    if (content === null) {
      next.push(row);
      continue;
    }
    changed = true;
    if (!content) continue;
    next.push({
      ...row,
      content,
      local_image_uri: null,
      local_file_uri: null,
      local_file_name: null,
      local_file_content_type: null,
    });
  }
  return changed ? next : messages;
}
