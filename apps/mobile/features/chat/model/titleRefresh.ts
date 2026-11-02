import type { Chat } from "@/lib/api";
import { chatNeedsGeneratedTitle, provisionalAttachmentTitle } from "@/features/chat/model/title";

type FirstReplyTitlePlan = {
  insert: Chat | null;
  fetch: boolean;
  poll: boolean;
};

/** New chat closes the per-chat socket, so stream `done` never inserts the row. */
export function shouldInsertDrawerRowOnLeave(
  messages: readonly { role: string }[],
): boolean {
  return messages.some((m) => m.role === "user");
}

/**
 * First assistant reply used to GET /chats/{id} just to insert the drawer row.
 * Home send already has the POST /chats body. Do not stamp the first user
 * line as the title — the topic job writes a real one; poll until it lands.
 * Attachment-only turns may show Image/File while that job runs.
 */
export function firstReplyTitlePlan(
  created: Chat | undefined,
  listed: Chat | undefined,
  firstUserText?: string,
): FirstReplyTitlePlan {
  const chat = listed ?? created;
  if (!chat) return { insert: null, fetch: true, poll: true };
  if (chat.title && (listed || !chatNeedsGeneratedTitle(chat.title))) {
    return { insert: chat, fetch: false, poll: false };
  }
  const overlay = provisionalAttachmentTitle(firstUserText);
  return {
    insert: overlay ? { ...chat, title: overlay } : chat,
    fetch: false,
    poll: true,
  };
}
