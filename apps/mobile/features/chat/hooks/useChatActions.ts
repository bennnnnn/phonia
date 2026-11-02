import { useCallback, useRef, useState } from "react";

import type { IconName } from "@/ui/icons/names";

import { api, type Message } from "@/lib/api";
import { patchCachedChatMessage } from "@/features/chat/model/messageCache";
import { NothingToExportError } from "@/features/chat/model/nothingToExport";
import { isShareCancelled } from "@/lib/shareCancelled";
import { useChatManagementActions } from "@/features/chat/hooks/useChatManagementActions";
import { fullEmailText } from "@/features/drafts/model/emailCompose";
import { replaceFirstClosedFenceBody } from "@/lib/mdFenceScan";
import type { EmailDraft } from "@/lib/richBlocks";
import { isServerMessageId } from "@/lib/serverMessageId";
import { useActionFeedbackOptional } from "@/contexts/actionFeedbackCore";
import { reportRecoverableError } from "@/lib/reportRecoverableError";
import { shareFailureKey } from "@/lib/shareUnavailable";
import { useLatestRef } from "@/lib/latestRef";
import type { EditThread } from "@/features/chat/model/threadEdit";

type Options = {
  token: string | null;
  chatId: string | null;
  chatTitle: string | null;
  messages: Message[];
  pinned: boolean;
  setPinned: React.Dispatch<React.SetStateAction<boolean>>;
  archived: boolean;
  setArchived: React.Dispatch<React.SetStateAction<boolean>>;
  setChatTitle: React.Dispatch<React.SetStateAction<string | null>>;
  editThread: EditThread;
  t: (key: string, options?: Record<string, unknown>) => string;
};

export function useChatActions({
  token,
  chatId,
  chatTitle,
  messages,
  pinned,
  setPinned,
  archived,
  setArchived,
  setChatTitle,
  editThread,
  t,
}: Options) {
  const feedback = useActionFeedbackOptional();
  const messagesRef = useLatestRef(messages);
  const emailSavesRef = useRef(new Map<string, Promise<boolean>>());
  const [menuVisible, setMenuVisible] = useState(false);
  const [shareVisible, setShareVisible] = useState(false);
  const [actionBanner, setActionBanner] = useState<{
    message: string;
    icon?: IconName;
  } | null>(null);

  const showActionBanner = useCallback(
    (message: string, icon?: IconName) => {
      setActionBanner({ message, icon });
    },
    [],
  );

  const dismissActionBanner = useCallback(() => setActionBanner(null), []);

  const closeMenu = useCallback(() => setMenuVisible(false), []);

  const handleFeedback = useCallback(
    (messageId: string, next: "up" | "down" | null) => {
      let previous: "up" | "down" | null = null;
      editThread(
        (prev) =>
          prev.map((mm) => {
            if (mm.id !== messageId) return mm;
            previous = mm.feedback ?? null;
            return { ...mm, feedback: next };
          }),
        "feedback",
      );
      if (token && chatId && isServerMessageId(messageId)) {
        void api.setMessageFeedback(token, chatId, messageId, next).catch(() => {
          editThread(
            (prev) => prev.map((mm) => (mm.id === messageId ? { ...mm, feedback: previous } : mm)),
            "feedback",
          );
          reportRecoverableError(feedback, t("chat.feedback_failed"));
        });
      }
    },
    [token, chatId, editThread, feedback, t],
  );

  const handleSaveEmailDraft = useCallback(
    (messageId: string, draft: EmailDraft): Promise<boolean> => {
      if (!token || !chatId || !isServerMessageId(messageId)) return Promise.resolve(false);
      const fenceBody = fullEmailText(draft);
      const message = messagesRef.current.find((m) => m.id === messageId);
      if (!message || message.role !== "assistant" ||
          replaceFirstClosedFenceBody(message.content, "email", fenceBody) == null) {
        return Promise.resolve(false);
      }
      // The card owns its unsaved fields. Never infer success from a React
      // state updater (which can run later or twice), or cache an unsaved edit.
      // Serialize writes so a slow earlier request cannot win on the server.
      const key = `${chatId}:${messageId}`;
      const pending = emailSavesRef.current.get(key) ?? Promise.resolve(true);
      const saving = pending.then(async () => {
        try {
        const updated = await api.updateMessageEmail(token, chatId, messageId, {
          to: draft.to,
          subject: draft.subject,
          body: draft.body,
        });
        editThread(
          (prev) => prev.map((mm) => (mm.id === messageId ? { ...mm, content: updated.content } : mm)),
          "email_draft_saved",
        );
        void patchCachedChatMessage(chatId, messageId, { content: updated.content });
        return true;
      } catch {
        reportRecoverableError(feedback, t("chat.email_card_save_failed"));
        return false;
      }
      });
      emailSavesRef.current.set(key, saving);
      void saving.then(() => {
        if (emailSavesRef.current.get(key) === saving) emailSavesRef.current.delete(key);
      });
      return saving;
    },
    [token, chatId, editThread, feedback, t, messagesRef],
  );

  /**
   * Every message in the chat. A failed read throws: the loaded page is not the whole
   * chat, and a PDF or share of it would pass for one (code-health audit CLAR-08).
   */
  const loadTranscriptMessages = useCallback(async () => {
    if (!token || !chatId) return messages;
    return api.listAllMessages(token, chatId);
  }, [token, chatId, messages]);

  const handleExportPdf = useCallback(async () => {
    showActionBanner(t("chat.status.preparing"), "file-text");
    try {
      // KaTeX, its stylesheet and expo-print load when a PDF is asked for, not with the chat.
      const [transcript, { exportConversationAsPdf }] = await Promise.all([
        loadTranscriptMessages(),
        import("@/features/chat/model/exportMessagePdf"),
      ]);
      dismissActionBanner();
      await exportConversationAsPdf(chatTitle, transcript);
    } catch (error) {
      dismissActionBanner();
      if (isShareCancelled(error)) return;
      reportRecoverableError(
        feedback,
        t(error instanceof NothingToExportError ? "chat.export_pdf_empty" : shareFailureKey(error, "chat.export_pdf_failed")),
      );
    }
  }, [chatTitle, dismissActionBanner, loadTranscriptMessages, showActionBanner, feedback, t]);

  const {
    renameVisible, setRenameVisible, renameText, setRenameText,
    openRename, confirmRename, togglePin, toggleArchive, confirmDelete,
  } = useChatManagementActions({
    token, chatId, chatTitle, pinned, archived, setPinned, setArchived,
    setChatTitle, closeMenu, dismissActionBanner, showActionBanner, t,
  });

  // The menu row plays the haptic; these handlers add none (one per tap).
  /** ⋮ Share opens the share sheet, which loads the transcript itself. */
  const onShareFromMenu = useCallback(() => {
    closeMenu();
    setShareVisible(true);
  }, [closeMenu]);
  const closeShare = useCallback(() => setShareVisible(false), []);

  const onExportPdfFromMenu = useCallback(() => {
    closeMenu();
    void handleExportPdf();
  }, [closeMenu, handleExportPdf]);

  const onRenameFromMenu = useCallback(() => {
    closeMenu();
    openRename();
  }, [closeMenu, openRename]);

  const onTogglePinFromMenu = useCallback(() => {
    closeMenu();
    void togglePin();
  }, [closeMenu, togglePin]);

  const onToggleArchiveFromMenu = useCallback(() => {
    closeMenu();
    void toggleArchive();
  }, [closeMenu, toggleArchive]);

  const onDeleteFromMenu = useCallback(() => {
    closeMenu();
    confirmDelete();
  }, [closeMenu, confirmDelete]);

  return {
    menuVisible,
    setMenuVisible,
    renameVisible,
    renameText,
    setRenameText,
    setRenameVisible,
    actionBanner,
    showActionBanner,
    dismissActionBanner,
    closeMenu,
    handleFeedback,
    handleSaveEmailDraft,
    shareVisible,
    closeShare,
    loadTranscriptMessages,
    handleExportPdf,
    openRename,
    confirmRename,
    togglePin,
    toggleArchive,
    confirmDelete,
    onShareFromMenu,
    onExportPdfFromMenu,
    onRenameFromMenu,
    onTogglePinFromMenu,
    onToggleArchiveFromMenu,
    onDeleteFromMenu,
  };
}
