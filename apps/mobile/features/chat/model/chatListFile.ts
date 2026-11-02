import type { Chat, ChatList } from "@/lib/api";
import { cacheFile } from "@/lib/cache/cacheFile";
import { emptyChatList } from "@/features/chat/model/listSections";

const chatListFile = cacheFile("cached-chat-list.json");

/** Tagged with the account that read it, so a file a failed sign-out left behind
 * is never shown to the next account. */
type StoredChatList = { user_id: string; list: ChatList };

const GROUPS = ["pinned", "today", "yesterday", "last_7_days", "this_month", "older", "archived"] as const;

function readChat(value: unknown): Chat | null {
  if (typeof value !== "object" || value === null) return null;
  const { id, title, model, pinned, archived, created_at: createdAt, updated_at: updatedAt } =
    value as Record<string, unknown>;
  if (
    typeof id !== "string" ||
    (title !== null && typeof title !== "string") ||
    typeof model !== "string" ||
    typeof pinned !== "boolean" ||
    (archived !== undefined && typeof archived !== "boolean") ||
    typeof createdAt !== "string" ||
    typeof updatedAt !== "string"
  ) {
    return null;
  }
  const chat: Chat = { id, title, model, pinned, created_at: createdAt, updated_at: updatedAt };
  if (archived !== undefined) chat.archived = archived;
  return chat;
}

function readList(value: unknown): ChatList | null {
  if (typeof value !== "object" || value === null) return null;
  const groups = value as Record<string, unknown>;
  const list = emptyChatList();
  for (const group of GROUPS) {
    const rows = groups[group];
    if (!Array.isArray(rows)) return null;
    list[group] = rows.map(readChat).filter((chat): chat is Chat => chat !== null);
  }
  return list;
}

/** The drawer list this account read last, for a cold start to paint at once.
 * Null when there is none, it is unreadable, or another account wrote it. */
export async function readStoredChatList(userId: string): Promise<ChatList | null> {
  const raw = await chatListFile.read();
  if (raw === null) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return null;
    const { user_id: owner, list } = parsed as Record<string, unknown>;
    return owner === userId ? readList(list) : null;
  } catch {
    return null;
  }
}

export function writeStoredChatList(userId: string, list: ChatList): Promise<void> {
  const stored: StoredChatList = { user_id: userId, list };
  return chatListFile.write(JSON.stringify(stored));
}

export function clearStoredChatList(): Promise<void> {
  return chatListFile.clear();
}
