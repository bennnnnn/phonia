import type { Chat, ChatList } from "@/lib/api";
import {
  activeChatsFromGroups,
  CHAT_DATE_SECTIONS,
  PINNED_CHAT_SECTION,
  type ChatListSectionKey,
} from "@/features/chat/model/listSections";

export function toggleChatSelection(selected: ReadonlySet<string>, chatId: string): Set<string> {
  const next = new Set(selected);
  if (next.has(chatId)) next.delete(chatId);
  else next.add(chatId);
  return next;
}

export function selectAllChatIds(chats: readonly Chat[]): Set<string> {
  return new Set(chats.map((chat) => chat.id));
}

export function clearChatSelection(): Set<string> {
  return new Set();
}

export function chatsFromSelection(groups: ChatList, selectedIds: ReadonlySet<string>): Chat[] {
  if (selectedIds.size === 0) return [];
  const listed = activeChatsFromGroups(groups).concat(groups.archived);
  return listed.filter((chat) => selectedIds.has(chat.id));
}

export function archiveBulkTargets(chats: readonly Chat[]): Chat[] {
  return chats.filter((chat) => !chat.archived);
}

/** What "Select all" picks: the chats on screen, never archived ones or a collapsed section. */
export function selectableChats(
  groups: ChatList,
  isSectionCollapsed: (key: ChatListSectionKey) => boolean,
): Chat[] {
  return [PINNED_CHAT_SECTION, ...CHAT_DATE_SECTIONS].flatMap((key) =>
    isSectionCollapsed(key) ? [] : groups[key],
  );
}

/** The server takes at most this many chats per bulk request. */
const BULK_CHAT_LIMIT = 200;

/** Run ``send`` once per part of at most 200 ids; the ids the server changed. A part that
 * fails changes none of its ids. */
export async function bulkInParts(
  ids: readonly string[],
  send: (part: string[]) => Promise<{ changed: string[] }>,
): Promise<Set<string>> {
  const changed = new Set<string>();
  for (let start = 0; start < ids.length; start += BULK_CHAT_LIMIT) {
    try {
      const result = await send(ids.slice(start, start + BULK_CHAT_LIMIT));
      for (const id of result.changed) changed.add(id);
    } catch {
      // This part's chats are restored by the caller; the next part still runs.
    }
  }
  return changed;
}
