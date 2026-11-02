import { useCallback, useEffect, useMemo, useState } from "react";

import { useActionFeedbackOptional } from "@/contexts/actionFeedbackCore";
import { getSessionGeneration } from "@/lib/auth";
import { useViewOwner } from "@/features/chat/hooks/useViewOwner";
import { insertChatGlobal, patchChatGlobal, removeChatGlobal } from "@/features/chat/drawer/drawer";
import {
  confirmAndDeleteChat,
  renameChat,
  setChatArchived,
  setChatPinned,
  type ChatOperationContext,
} from "@/features/chat/model/chatOperations";
import type { Chat } from "@/lib/api";
import type { IconName } from "@/ui/icons/names";
import { reportRecoverableError } from "@/lib/reportRecoverableError";

type Options = {
  token: string | null;
  chatId: string | null;
  chatTitle: string | null;
  pinned: boolean;
  archived: boolean;
  setPinned: React.Dispatch<React.SetStateAction<boolean>>;
  setArchived: React.Dispatch<React.SetStateAction<boolean>>;
  setChatTitle: React.Dispatch<React.SetStateAction<string | null>>;
  closeMenu: () => void;
  dismissActionBanner: () => void;
  showActionBanner: (message: string, icon?: IconName) => void;
  t: (key: string, options?: Record<string, unknown>) => string;
};

const DRAWER_LIST = { patch: patchChatGlobal, insert: insertChatGlobal, remove: removeChatGlobal };

/** The chat header's menu: the same operations as the drawer's row menu, on the open chat. */
export function useChatManagementActions({
  token, chatId, chatTitle, pinned, archived, setPinned, setArchived,
  setChatTitle, closeMenu, dismissActionBanner, showActionBanner, t,
}: Options) {
  const feedback = useActionFeedbackOptional();
  const session = getSessionGeneration();
  const signedIn = Boolean(token);
  const { view, owns } = useViewOwner(`${chatId}:${session}:${signedIn}`);
  const currentSession = useCallback(() => session === getSessionGeneration(), [session]);
  const currentView = useCallback(() => owns() && currentSession(), [owns, currentSession]);
  const [renameVisible, setRenameVisible] = useState(false);
  const [renameText, setRenameText] = useState("");
  useEffect(() => {
    setRenameVisible(false);
    setRenameText("");
    closeMenu();
    dismissActionBanner();
  }, [view, closeMenu, dismissActionBanner]);

  const operations = useMemo<ChatOperationContext | null>(
    () =>
      token
        ? {
            token,
            session,
            list: DRAWER_LIST,
            signedIn: currentSession,
            shown: currentView,
            mirror: (patch: Partial<Chat>) => {
              if (patch.title !== undefined) setChatTitle(patch.title);
              if (patch.pinned !== undefined) setPinned(patch.pinned);
              if (patch.archived !== undefined) setArchived(Boolean(patch.archived));
            },
            banner: showActionBanner,
            failure: (message: string) => reportRecoverableError(feedback, message),
            t,
          }
        : null,
    [token, session, currentSession, currentView, setChatTitle, setPinned, setArchived, showActionBanner, feedback, t],
  );
  const ref = useMemo(
    () => (chatId ? { id: chatId, title: chatTitle, pinned, archived } : null),
    [chatId, chatTitle, pinned, archived],
  );

  const openRename = useCallback(() => {
    if (!currentView()) return;
    setRenameText(chatTitle ?? "");
    setRenameVisible(true);
  }, [chatTitle, currentView]);

  const confirmRename = useCallback(async () => {
    if (!operations || !ref || !currentView()) return;
    if (renameChat(operations, ref, renameText)) setRenameVisible(false);
  }, [operations, ref, currentView, renameText]);

  const togglePin = useCallback(async () => {
    if (!operations || !ref || !currentView()) return;
    await setChatPinned(operations, ref, !ref.pinned);
  }, [operations, ref, currentView]);

  const toggleArchive = useCallback(async () => {
    if (!operations || !ref || !currentView()) return;
    await setChatArchived(operations, ref, !ref.archived);
  }, [operations, ref, currentView]);

  const confirmDelete = useCallback(() => {
    if (!operations || !chatId || !currentView()) return;
    confirmAndDeleteChat(operations, chatId);
  }, [operations, chatId, currentView]);

  return { renameVisible, setRenameVisible, renameText, setRenameText, openRename, confirmRename, togglePin, toggleArchive, confirmDelete };
}
