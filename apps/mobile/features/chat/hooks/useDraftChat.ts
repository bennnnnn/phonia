import { useCallback, useEffect, useRef, useState } from "react";
import { AppState } from "react-native";

import { useAccountSession } from "@/contexts/accountSession";
import { api } from "@/lib/api";
import { rememberCreatedChat } from "@/features/chat/model/chatListCache";
import { resolveActiveChatId } from "@/features/chat/model/draftLogic";
import { useLatestRef } from "@/lib/latestRef";
import { reportFailure } from "@/lib/sentry";

type Options = {
  chatId: string | null;
  /** The user has started a message (the composer holds text): make its chat now. */
  intent: boolean;
};

/**
 * The chat a new conversation sends into, made when the user starts writing, not when the
 * view opens. Every glance at a new chat used to insert a chat and open a socket, then read
 * a page and delete it twice on the way out (code-health audit NET-13). It is keyed on the
 * account, not the bearer token, which rotates hourly (NET-11).
 */
export function useDraftChat({ chatId, intent }: Options) {
  const { account, getToken } = useAccountSession();
  const [draftChatId, setDraftChatId] = useState<string | null>(null);
  const draftChatIdRef = useRef<string | null>(null);
  const draftCreatePromiseRef = useRef<Promise<string | null> | null>(null);
  const skipLoadForChatIdRef = useRef<string | null>(null);
  const creatingRef = useRef(false);
  const chatIdRef = useLatestRef(chatId);
  const intentRef = useLatestRef(intent);

  /** Delete a chat the user never wrote in: one request, a no-op once it holds a message. */
  const discardEmptyChat = useCallback(
    (id: string | null) => {
      const token = getToken();
      if (!token || !id) return;
      api.deleteChatIfEmpty(token, id).catch(() => {});
    },
    [getToken],
  );

  const clearDraftChat = useCallback(
    (id?: string | null) => {
      const toDiscard = id ?? draftChatIdRef.current;
      draftChatIdRef.current = null;
      draftCreatePromiseRef.current = null;
      setDraftChatId(null);
      discardEmptyChat(toDiscard);
    },
    [discardEmptyChat],
  );

  const prepareDraftChat = useCallback(
    async (model = "auto", opts?: { force?: boolean }): Promise<string | null> => {
      const token = getToken();
      if (!token) return null;
      if (opts?.force) {
        draftChatIdRef.current = null;
        setDraftChatId(null);
      }
      if (chatId && !opts?.force) return chatId;
      if (draftChatIdRef.current && !opts?.force) return draftChatIdRef.current;
      if (draftCreatePromiseRef.current) return draftCreatePromiseRef.current;

      const task = api
        .createChat(token, model)
        .then((chat) => {
          rememberCreatedChat(chat);
          draftChatIdRef.current = chat.id;
          setDraftChatId(chat.id);
          return chat.id;
        })
        .catch((error: unknown) => {
          // The send waiting on it gives its text back to the composer.
          reportFailure("chat_create", error);
          return null;
        })
        .finally(() => {
          draftCreatePromiseRef.current = null;
        });
      draftCreatePromiseRef.current = task;
      return task;
    },
    [getToken, chatId],
  );

  // The first keystroke makes the chat, so the send does not wait on it.
  useEffect(() => {
    if (!account || !intent || chatId || draftChatIdRef.current || draftCreatePromiseRef.current) return;
    void prepareDraftChat();
  }, [account, intent, chatId, prepareDraftChat]);

  // Leaving the app with nothing written drops the draft. `inactive` (Control Center, the
  // app switcher, a call) comes straight back, so it keeps it.
  useEffect(() => {
    const sub = AppState.addEventListener("change", (state) => {
      if (state !== "background" || intentRef.current || chatIdRef.current) return;
      if (draftChatIdRef.current) clearDraftChat();
    });
    return () => sub.remove();
  }, [clearDraftChat, chatIdRef, intentRef]);

  return {
    draftChatId,
    setDraftChatId,
    draftChatIdRef,
    draftCreatePromiseRef,
    skipLoadForChatIdRef,
    creatingRef,
    discardEmptyChat,
    clearDraftChat,
    prepareDraftChat,
    activeChatId: resolveActiveChatId(chatId, draftChatId),
  };
}
