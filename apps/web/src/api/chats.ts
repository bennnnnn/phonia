import { request } from "@/api/client";
import type { Chat, ChatList, Message, MessagePage } from "@/api/types";

function normalizeMessagePage(data: MessagePage | Message[]): MessagePage {
  if (Array.isArray(data)) return { messages: data, has_more: false };
  return data;
}

export const chatsApi = {
  createChat: (token: string, model = "auto") =>
    request<Chat>("/chats", token, {
      method: "POST",
      body: JSON.stringify({ model }),
    }),
  listChats: (token: string) => request<ChatList>("/chats", token),
  listMessages: async (
    token: string,
    chatId: string,
    opts?: { limit?: number; before?: string },
  ): Promise<MessagePage> => {
    const params = new URLSearchParams();
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    if (opts?.before) params.set("before", opts.before);
    const qs = params.toString();
    const data = await request<MessagePage | Message[]>(
      `/chats/${chatId}/messages${qs ? `?${qs}` : ""}`,
      token,
    );
    return normalizeMessagePage(data);
  },
};
