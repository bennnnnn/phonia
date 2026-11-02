import { request, requestRevalidated } from "@/lib/api/client";
import { ApiRequestError } from "@/lib/api/errorBody";
import { shareEmptyChatCheck } from "@/features/chat/model/draftLogic";
import { getDeviceTimezone } from "@/lib/deviceTimezone";
import type {
  Chat,
  ChatList,
  Feedback,
  Message,
  MessagePage,
} from "@/lib/api/types";

function normalizeMessagePage(data: MessagePage | Message[]): MessagePage {
  if (Array.isArray(data)) {
    return { messages: data, has_more: false };
  }
  return data;
}

/** The newest page, or the page `before` or `after` a message, or the window `around` one. */
async function listMessages(
  token: string,
  chatId: string,
  opts?: { limit?: number; before?: string; after?: string; around?: string },
): Promise<MessagePage> {
  const params = new URLSearchParams();
  if (opts?.limit != null) params.set("limit", String(opts.limit));
  if (opts?.before) params.set("before", opts.before);
  if (opts?.after) params.set("after", opts.after);
  if (opts?.around) params.set("around", opts.around);
  const qs = params.toString();
  const path = `/chats/${chatId}/messages${qs ? `?${qs}` : ""}`;
  // The newest page is read again on every visit; another, seldom.
  const data = opts?.before || opts?.after || opts?.around
    ? await request<MessagePage | Message[]>(path, token)
    : await requestRevalidated<MessagePage | Message[]>(path, token);
  return normalizeMessagePage(data);
}

/**
 * GET /chats, grouped by day in the phone's zone, the one it files a chat it inserts
 * itself in: the profile's copy of the zone lags a flight until the next sync. A new
 * zone is a new path, so the list kept for the old one is never revalidated for it.
 */
function chatListPath(cursor?: string): string {
  const params = new URLSearchParams();
  if (cursor) params.set("cursor", cursor);
  params.set("client_timezone", getDeviceTimezone());
  return `/chats?${params.toString()}`;
}

const ALL_MESSAGES_BATCH = 100;
// A walk restarted this often by regenerates keeps the newest messages it has read.
const ALL_MESSAGES_RESTARTS = 2;

function isInvalidCursor(error: unknown): boolean {
  return error instanceof ApiRequestError && error.code === "invalid_cursor";
}

/** Every message, oldest first, read a page at a time back from the newest (copy and
 * share). A regenerate during the walk removes the message the next page is anchored on
 * (422 `invalid_cursor`): the walk starts again from the newest page, and after
 * `ALL_MESSAGES_RESTARTS` such restarts returns the messages it has. */
async function listAllMessages(token: string, chatId: string): Promise<Message[]> {
  let all: Message[] = [];
  let before: string | undefined;
  let restarts = 0;
  for (;;) {
    let page: MessagePage;
    try {
      page = await listMessages(token, chatId, { limit: ALL_MESSAGES_BATCH, before });
    } catch (error) {
      if (!before || !isInvalidCursor(error)) throw error;
      if (restarts >= ALL_MESSAGES_RESTARTS) return all;
      restarts += 1;
      all = [];
      before = undefined;
      continue;
    }
    all = before ? [...page.messages, ...all] : page.messages;
    if (!page.has_more || page.messages.length === 0) return all;
    before = page.messages[0].id;
  }
}

export const chatsApi = {
  createChat: (token: string) => request<Chat>("/chats", token, { method: "POST" }),
  getChat: (token: string, chatId: string) =>
    request<Chat>(`/chats/${chatId}`, token),
  renameChat: (token: string, chatId: string, title: string) =>
    request<Chat>(`/chats/${chatId}`, token, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),
  setPin: (token: string, chatId: string, pinned: boolean) =>
    request<Chat>(`/chats/${chatId}/pin`, token, {
      method: "PATCH",
      body: JSON.stringify({ pinned }),
    }),
  deleteChat: (token: string, chatId: string) =>
    request<void>(`/chats/${chatId}`, token, { method: "DELETE" }),
  /** Delete up to 200 chats at once; `changed` is what the server did. */
  bulkChats: (token: string, action: "delete", chatIds: string[]) =>
    request<{ changed: string[] }>("/chats/bulk", token, {
      method: "POST",
      body: JSON.stringify({ action, chat_ids: chatIds }),
    }),
  deleteAllChats: (token: string) =>
    request<void>("/chats", token, { method: "DELETE" }),
  /** One request: the server keeps a chat that holds any message (a turn left mid-stream). */
  deleteChatIfEmpty: (token: string, chatId: string) =>
    shareEmptyChatCheck(chatId, () =>
      request<void>(`/chats/${chatId}?if_empty=true`, token, { method: "DELETE" }),
    ),
  listChats: (token: string) => requestRevalidated<ChatList>(chatListPath(), token),
  /** The dated chats after the first page; `cursor` is the list's `next_cursor`. */
  listOlderChats: (token: string, cursor: string) =>
    request<ChatList>(chatListPath(cursor), token),
  listMessages,
  listAllMessages,
  setMessageFeedback: (
    token: string,
    chatId: string,
    messageId: string,
    feedback: Feedback,
  ) =>
    request<Message>(`/chats/${chatId}/messages/${messageId}/feedback`, token, {
      method: "PATCH",
      body: JSON.stringify({ feedback }),
    }),
  updateMessageEmail: (
    token: string,
    chatId: string,
    messageId: string,
    draft: { to?: string; subject?: string; body: string },
  ) =>
    request<Message>(`/chats/${chatId}/messages/${messageId}/email`, token, {
      method: "PATCH",
      body: JSON.stringify({
        to: draft.to ?? "",
        subject: draft.subject ?? "",
        body: draft.body,
      }),
    }),
};
