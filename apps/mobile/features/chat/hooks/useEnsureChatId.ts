import { useCallback, type Dispatch, type SetStateAction } from "react";
import type { useRouter } from "expo-router";

import type { useDraftChat } from "@/features/chat/hooks/useDraftChat";

type Options = {
  chatId: string | null;
  selectedModel: string;
  draft: Pick<
    ReturnType<typeof useDraftChat>,
    "creatingRef" | "prepareDraftChat" | "skipLoadForChatIdRef" | "draftChatIdRef" | "setDraftChatId"
  >;
  setChatId: Dispatch<SetStateAction<string | null>>;
  setChatTitle: Dispatch<SetStateAction<string | null>>;
  router: Pick<ReturnType<typeof useRouter>, "setParams">;
};

/** For a send that can outlive its view: a chat created after the user left is thrown away. */
type SendView = {
  isCurrent: () => boolean;
  discard: (id: string) => void;
  /** Runs once the new id is the open chat, before the route names it. */
  adopt: (id: string) => void;
};

/**
 * `ensureChatId()` is the open chat's id, or a new draft chat made the open one. It throws
 * when no chat can be created and is null when `view` moved on first.
 */
export function useEnsureChatId({ chatId, selectedModel, draft, setChatId, setChatTitle, router }: Options) {
  const { creatingRef, prepareDraftChat, skipLoadForChatIdRef, draftChatIdRef, setDraftChatId } = draft;
  return useCallback(async (view?: SendView): Promise<string | null> => {
    if (chatId) return chatId;
    creatingRef.current = true;
    try {
      const id = await prepareDraftChat(selectedModel);
      if (!id) throw new Error("Could not create chat");
      if (view && !view.isCurrent()) {
        if (draftChatIdRef.current === id) {
          draftChatIdRef.current = null;
          setDraftChatId(null);
        }
        view.discard(id);
        return null;
      }
      skipLoadForChatIdRef.current = id;
      setChatTitle(null);
      setChatId(id);
      draftChatIdRef.current = null;
      setDraftChatId(null);
      view?.adopt(id);
      router.setParams({ chatId: id });
      return id;
    } finally {
      creatingRef.current = false;
    }
  }, [chatId, creatingRef, prepareDraftChat, skipLoadForChatIdRef, draftChatIdRef, setDraftChatId, router, selectedModel, setChatId, setChatTitle]);
}
