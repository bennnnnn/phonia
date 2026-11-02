import { useCallback } from "react";

import { api, type Message } from "@/lib/api";
import { noteChatPageRead } from "@/features/chat/model/pageReads";
import {
  knownServerIds,
  pollDroppedTurn,
  type DroppedTurnResult,
} from "@/features/chat/model/turnReconcile";

type Options = {
  token: string | null;
  chatId: string | null;
  isCurrentView: () => boolean;
  /** The messages on screen now. */
  messages: () => Message[];
  /** The turn's attempt number, and whether it is still streaming. */
  attempt: () => number;
  streaming: () => boolean;
};

/**
 * Follows a turn the server took after its connection dropped: reload the chat
 * until the reply lands. The streaming bubble stays up meanwhile; Stop, a new
 * send or leaving the chat ends the wait without a settle.
 */
export function useDroppedTurnReconcile({ token, chatId, isCurrentView, messages, attempt, streaming }: Options) {
  return useCallback(
    (settle: (result: DroppedTurnResult) => void, polls?: number, pollMs?: (poll: number) => number) => {
      if (!token || !chatId) {
        settle({ state: "unknown", page: null });
        return;
      }
      const followed = attempt();
      void pollDroppedTurn({
        fetchPage: async (limit) => (await api.listMessages(token, chatId, { limit })).messages,
        known: knownServerIds(messages()),
        stillWaiting: () => isCurrentView() && attempt() === followed && streaming(),
        polls,
        pollMs,
      }).then((result) => {
        // The answered turn settles with the chat's newest page: a read of it like any other.
        if (result?.page) noteChatPageRead(chatId);
        if (result) settle(result);
      });
    },
    [token, chatId, isCurrentView, messages, attempt, streaming],
  );
}
