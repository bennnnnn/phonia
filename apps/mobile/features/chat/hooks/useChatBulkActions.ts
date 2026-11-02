import { useCallback } from "react";
import { useTranslation } from "react-i18next";

import { useActionFeedbackOptional } from "@/contexts/actionFeedbackCore";
import { api, Chat } from "@/lib/api";
import { getSessionGeneration } from "@/lib/auth";
import { useViewOwner } from "@/features/chat/hooks/useViewOwner";
import { beginChatMutation } from "@/features/chat/model/mutationLock";
import { clearCachedChatMessages } from "@/features/chat/model/messageCache";
import { getCachedChat } from "@/features/chat/model/chatListCache";
import { emitAppEvent } from "@/lib/appEvents";
import { abandonActiveChatIfDeleted } from "@/features/chat/drawer/drawer";
import { bulkInParts } from "@/features/chat/drawer/drawerChatSelection";
import { notifyDestructive } from "@/lib/haptics";
import type { IconName } from "@/ui/icons/names";
import { reportRecoverableError } from "@/lib/reportRecoverableError";
import { confirmDialog } from "@/ui/overlay/dialogs";

type Params = {
  token: string | null;
  isDrawerOpen: boolean;
  insertChatInGroups: (chat: Chat) => void;
  removeChatFromGroupsById: (chatId: string) => void;
  reloadChats: () => void;
  showActionBanner: (message: string, icon?: IconName) => void;
};

/** Multi-select bulk delete for the drawer's selection mode. */
export function useChatBulkActions({
  token, isDrawerOpen, insertChatInGroups, removeChatFromGroupsById, reloadChats, showActionBanner,
}: Params) {
  const { t } = useTranslation();
  const feedback = useActionFeedbackOptional();
  const session = getSessionGeneration();
  const signedIn = Boolean(token);
  const { owns } = useViewOwner(`${session}:${isDrawerOpen}:${signedIn}`);
  const currentSession = useCallback(() => session === getSessionGeneration(), [session]);
  const currentView = useCallback(
    () => owns() && isDrawerOpen && currentSession(),
    [isDrawerOpen, owns, currentSession],
  );

  const bulkDeleteChats = useCallback(
    (chats: Chat[], onSuccess?: () => void) => {
      const targets = chats.map((chat) => ({ ...chat }));
      if (!token || !currentView() || targets.length === 0) return;
      void confirmDialog({
        title: t("drawer.bulk_delete_confirm_title"),
        message: t("drawer.bulk_delete_confirm_body", { count: targets.length }),
        cancelLabel: t("common.cancel"),
        confirmLabel: t("common.delete"),
        destructive: true,
      }).then(async (ok) => {
        if (!ok) return;
        if (!currentView()) return;
        const release = beginChatMutation(session, targets.map((chat) => chat.id));
        if (!release) return;
        const snapshots = targets.map((chat) => ({ ...(getCachedChat(chat.id) ?? chat) }));
        try {
          for (const chat of targets) removeChatFromGroupsById(chat.id);
          const deleted = await bulkInParts(
            targets.map((chat) => chat.id),
            (part) => api.bulkChats(token, "delete", part),
          );
          if (!currentSession()) return;
          const deletedIds: string[] = [];
          for (const chat of snapshots) {
            if (!deleted.has(chat.id)) insertChatInGroups(chat);
            else {
              removeChatFromGroupsById(chat.id);
              deletedIds.push(chat.id);
              void clearCachedChatMessages(chat.id);
            }
          }
          if (deletedIds.length > 0) {
            emitAppEvent("chatsDeleted", { chatIds: deletedIds });
            abandonActiveChatIfDeleted(deletedIds);
          }
          if (deletedIds.length !== targets.length) {
            reloadChats();
            if (currentView()) reportRecoverableError(feedback, t("chat.delete_failed"));
          } else if (currentView()) {
            notifyDestructive();
            showActionBanner(t("drawer.bulk_deleted_toast", { count: deletedIds.length }), "trash");
            onSuccess?.();
          }
        } finally { release(); }
      });
    },
    [token, currentView, t, session, removeChatFromGroupsById, currentSession, insertChatInGroups, reloadChats, feedback, showActionBanner],
  );

  return { bulkDeleteChats };
}
