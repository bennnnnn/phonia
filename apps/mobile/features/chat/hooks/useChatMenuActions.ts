import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { useActionFeedbackOptional } from "@/contexts/actionFeedbackCore";
import { api, Chat } from "@/lib/api";
import { getSessionGeneration } from "@/lib/auth";
import { useLatestRef } from "@/lib/latestRef";
import { useViewOwner } from "@/features/chat/hooks/useViewOwner";
import { getCachedChat } from "@/features/chat/model/chatListCache";
import {
  confirmAndDeleteChat,
  renameChat,
  setChatArchived,
  setChatPinned,
  type ChatOperationContext,
} from "@/features/chat/model/chatOperations";
import type { IconName } from "@/ui/icons/names";
import { reportRecoverableError } from "@/lib/reportRecoverableError";

type Params = {
  token: string | null;
  isDrawerOpen: boolean;
  patchChatInGroups: (chatId: string, patch: Partial<Chat>) => void;
  insertChatInGroups: (chat: Chat) => void;
  removeChatFromGroupsById: (chatId: string) => void;
};

/** Row-menu, rename sheet, and single-chat actions for the drawer. */
export function useChatMenuActions({
  token, isDrawerOpen, patchChatInGroups, insertChatInGroups, removeChatFromGroupsById,
}: Params) {
  const { t } = useTranslation();
  const feedback = useActionFeedbackOptional();
  const session = getSessionGeneration();
  const { view, owns, mounted } = useViewOwner(`${session}:${isDrawerOpen}`);
  // The menu, rename sheet and share sheet each belong to the view they opened in.
  const [menu, setMenu] = useState<{ chat: Chat; view: object } | null>(null);
  const [rename, setRename] = useState<{ chat: Chat; view: object } | null>(null);
  const [renameText, setRenameText] = useState("");
  const [share, setShare] = useState<{ chat: Chat; view: object } | null>(null);
  const menuChat = menu?.view === view ? menu.chat : null;
  const renameTarget = rename?.view === view ? rename.chat : null;
  const shareChat = share?.view === view ? share.chat : null;
  const shareRef = useLatestRef(shareChat);
  const [actionBanner, setActionBanner] = useState<{ message: string; icon?: IconName } | null>(null);
  const current = useCallback(() => mounted() && session === getSessionGeneration(), [mounted, session]);
  const currentView = useCallback(() => current() && isDrawerOpen && owns(), [current, isDrawerOpen, owns]);
  useEffect(() => {
    setMenu(null);
    setRename(null);
    setActionBanner(null);
    setShare(null);
  }, [session, isDrawerOpen]);

  const showActionBanner = useCallback((message: string, icon?: IconName) => {
    if (current()) setActionBanner({ message, icon });
  }, [current]);
  const dismissActionBanner = useCallback(() => setActionBanner(null), []);
  const closeMenu = useCallback(() => setMenu(null), []);
  const showRowMenu = useCallback((chat: Chat) => {
    if (currentView()) setMenu({ chat, view });
  }, [currentView, view]);
  const closeRename = useCallback(() => setRename(null), []);

  const openShareChat = useCallback(() => {
    if (!menuChat || !currentView()) return;
    const chat = getCachedChat(menuChat.id) ?? menuChat;
    closeMenu();
    setShare({ chat, view });
  }, [menuChat, currentView, closeMenu, view]);
  const closeShare = useCallback(() => setShare(null), []);
  /** Private history reaches the share sheet only while the drawer and account are unchanged. */
  const loadShareMessages = useCallback(async () => {
    const chat = shareRef.current;
    if (!token || !chat || !currentView()) throw new Error("share_closed");
    const msgs = await api.listAllMessages(token, chat.id);
    if (!currentView() || shareRef.current !== chat) throw new Error("share_closed");
    return msgs;
  }, [token, currentView, shareRef]);

  const openRenameFromMenu = useCallback(() => {
    if (!menuChat || !currentView()) return;
    const chat = getCachedChat(menuChat.id) ?? menuChat;
    setRename({ chat, view });
    setRenameText(chat.title ?? "");
    closeMenu();
  }, [menuChat, currentView, closeMenu, view]);

  const operations = useMemo<ChatOperationContext | null>(
    () =>
      token
        ? {
            token,
            session,
            list: { patch: patchChatInGroups, insert: insertChatInGroups, remove: removeChatFromGroupsById },
            signedIn: current,
            shown: currentView,
            banner: showActionBanner,
            failure: (message: string) => reportRecoverableError(feedback, message),
            t,
          }
        : null,
    [token, session, patchChatInGroups, insertChatInGroups, removeChatFromGroupsById, current, currentView, showActionBanner, feedback, t],
  );

  const confirmRename = useCallback(async () => {
    if (!operations || !renameTarget || !currentView()) return;
    const chat = getCachedChat(renameTarget.id) ?? renameTarget;
    if (renameChat(operations, chat, renameText)) closeRename();
  }, [operations, renameTarget, currentView, renameText, closeRename]);

  const togglePinChat = useCallback(async () => {
    if (!operations || !menuChat || !currentView()) return;
    const chat = getCachedChat(menuChat.id) ?? menuChat;
    if (chat.archived) return;
    closeMenu();
    await setChatPinned(operations, chat, !chat.pinned);
  }, [operations, menuChat, currentView, closeMenu]);

  const toggleArchiveChat = useCallback(async () => {
    if (!operations || !menuChat || !currentView()) return;
    const chat = getCachedChat(menuChat.id) ?? menuChat;
    closeMenu();
    await setChatArchived(operations, chat, !chat.archived);
  }, [operations, menuChat, currentView, closeMenu]);

  const confirmDeleteChat = useCallback(() => {
    if (!operations || !menuChat || !currentView()) return;
    const chat = menuChat;
    closeMenu();
    confirmAndDeleteChat(operations, chat.id, getCachedChat(chat.id) ?? chat);
  }, [operations, menuChat, currentView, closeMenu]);

  return {
    menuChat,
    renameVisible: renameTarget !== null,
    renameText, setRenameText, actionBanner, dismissActionBanner, showActionBanner,
    closeMenu, showRowMenu, openRenameFromMenu, confirmRename,
    shareChat, openShareChat, closeShare, loadShareMessages,
    togglePinChat, toggleArchiveChat, confirmDeleteChat, closeRename,
  };
}
