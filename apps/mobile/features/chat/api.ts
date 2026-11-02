import { request, requestRevalidated } from "@/lib/api/client";
import { shareEmptyChatCheck } from "@/features/chat/model/draftLogic";
import { getDeviceTimezone } from "@/lib/deviceTimezone";
import type {
  Chat,
  ChatList,
  Feedback,
  Message,
  MessagePage,
  Page,
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

export const chatsApi = {
  createChat: (token: string, model = "auto") =>
    request<Chat>("/chats", token, {
      method: "POST",
      body: JSON.stringify({ model }),
    }),
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
  setArchive: (token: string, chatId: string, archived: boolean) =>
    request<Chat>(`/chats/${chatId}/archive`, token, {
      method: "PATCH",
      body: JSON.stringify({ archived }),
    }),
  deleteChat: (token: string, chatId: string) =>
    request<void>(`/chats/${chatId}`, token, { method: "DELETE" }),
  /** Archive, unarchive or delete up to 200 chats at once; `changed` is what the server did. */
  bulkChats: (token: string, action: "archive" | "unarchive" | "delete", chatIds: string[]) =>
    request<{ changed: string[] }>("/chats/bulk", token, {
      method: "POST",
      body: JSON.stringify({ action, chat_ids: chatIds }),
    }),
  archiveAllChats: (token: string) =>
    request<void>("/chats/archive-all", token, { method: "POST" }),
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
  /** Archived chats past the drawer's first page; `cursor` is `archived_next_cursor`. */
  listArchivedChats: (token: string, cursor: string) =>
    request<Page<Chat>>(`/chats/archived?cursor=${encodeURIComponent(cursor)}`, token),
  listMessages,
  listAllMessages: async (token: string, chatId: string): Promise<Message[]> => {
    const batch = 100;
    let before: string | undefined;
    let hasMore = true;
    let all: Message[] = [];
    while (hasMore) {
      const page = await listMessages(token, chatId, {
        limit: batch,
        before,
      });
      if (!before) {
        all = page.messages;
      } else {
        all = [...page.messages, ...all];
      }
      hasMore = page.has_more;
      if (hasMore && page.messages.length > 0) {
        before = page.messages[0].id;
      } else {
        break;
      }
    }
    return all;
  },
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
