import { useEffect } from "react";

import type { Message } from "@/lib/api";
import { getCachedChat } from "@/features/chat/model/chatListCache";
import {
  isSettledThread,
  keepCachedChatPage,
  markCachedChatPageStale,
} from "@/features/chat/model/messageCache";

/** The server read the shown thread rests on; none until this open's read lands. */
export type ChatPageSync = {
  chatId: string;
  /**
   * Null when this open's page landed after a turn that went out first and was
   * left unmerged (it may hold that turn): the chat is read again once no turn
   * is under way.
   */
  fetchedAt: number | null;
};

type Options = {
  chatId: string | null;
  /** The chat the route names; while it differs from `chatId` the view is between two chats. */
  routeChatId: string | undefined;
  messages: Message[];
  /** A reply is streaming or finalizing. */
  busy: boolean;
  hasMoreOlder: boolean;
  /** The thread is a window around an older message (a search hit), not the newest page. */
  hasMoreNewer: boolean;
  sync: ChatPageSync | null;
  /** Reads the chat and merges it into the view, setting `sync` when it does (`silentRefetchChat`). */
  resync: (chatId: string, cancelled: () => boolean, opts: { force: boolean }) => Promise<void>;
};

/**
 * Keeps the open chat's page in step with what it shows: each finished turn,
 * follow-up questions, feedback or edit is kept once the thread settles, so
 * the next open paints it at once. Until then the kept page is marked stale and
 * the next open reads the chat. A view left without a read to rest on (its page
 * unmerged) reads the chat once the turn that went first is over, again if the
 * thread changes while that read is out, until one lands.
 */
export function useChatPageCacheWriter({
  chatId, routeChatId, messages, busy, hasMoreOlder, hasMoreNewer, sync, resync,
}: Options) {
  useEffect(() => {
    if (!chatId || chatId !== routeChatId) return;
    if (
      busy || hasMoreNewer || sync?.chatId !== chatId || sync.fetchedAt === null || !isSettledThread(messages)
    ) {
      markCachedChatPageStale(chatId);
      return;
    }
    keepCachedChatPage(chatId, messages, hasMoreOlder, sync.fetchedAt, getCachedChat(chatId)?.updated_at);
  }, [chatId, routeChatId, messages, busy, hasMoreOlder, hasMoreNewer, sync]);

  const unmergedChatId = sync?.fetchedAt === null ? sync.chatId : null;
  useEffect(() => {
    if (!unmergedChatId || unmergedChatId !== chatId || chatId !== routeChatId || busy) return;
    let cancelled = false;
    // A read that `messages` changed under is dropped (silentRefetchChat): this effect then runs again.
    void resync(unmergedChatId, () => cancelled, { force: true });
    return () => {
      cancelled = true;
    };
  }, [unmergedChatId, chatId, routeChatId, busy, messages, resync]);
}
