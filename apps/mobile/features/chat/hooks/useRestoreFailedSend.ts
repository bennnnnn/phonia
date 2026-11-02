import { useCallback, type MutableRefObject } from "react";

import { useActionFeedbackOptional } from "@/contexts/ActionFeedbackContext";
import { useComposerDraftApi } from "@/features/chat/context/ComposerDraftContext";
import { discardDraftAttachment, type PendingAttachment } from "@/features/attachments/model/attachments";
import { shouldRestoreFailedSend } from "@/features/chat/model/composerThreadDraft";
import { clearPendingChatTtft } from "@/features/chat/model/latency";
import type { EditThread } from "@/features/chat/model/threadEdit";

/** One send, from the tap that started it. */
export type SendTurn = {
  text: string;
  composerText: string;
  attachment: PendingAttachment | null;
  threadKey: string;
  isCurrentSession: () => boolean;
  isCurrentView: () => boolean;
  /** A tapped line (a follow-up, a card's answer): the composer's draft and file never went with it. */
  leavesComposer?: boolean;
};

type Options = {
  token: string | null;
  editThread: EditThread;
  newMessageCountRef: MutableRefObject<number>;
  pendingAttachmentRef: MutableRefObject<PendingAttachment | null>;
  setPendingAttachment: (value: PendingAttachment | null) => void;
  stashAttachmentForThread: (key: string, openKey: string, attachment: PendingAttachment | null) => void;
  setPendingOutboundId: (id: string | null) => void;
  sendInFlightRef: MutableRefObject<boolean>;
  setSendPhase: (phase: "idle") => void;
  t: (key: string) => string;
};

/**
 * Takes the bubble back and returns the draft (text as typed, and file) to the
 * thread it was typed in. Newer text or a file already there stays put, and the
 * user is told this draft could not come back.
 */
export function useRestoreFailedSend({
  token,
  editThread,
  newMessageCountRef,
  pendingAttachmentRef,
  setPendingAttachment,
  stashAttachmentForThread,
  setPendingOutboundId,
  sendInFlightRef,
  setSendPhase,
  t,
}: Options) {
  const { setInput, inputRef, stashFailedDraftForThread, getThreadKey } = useComposerDraftApi();
  const feedback = useActionFeedbackOptional();
  return useCallback(
    (turn: SendTurn, optimisticId: string, attached: PendingAttachment | null) => {
      clearPendingChatTtft(optimisticId);
      if (!turn.isCurrentSession()) {
        discardDraftAttachment(null, attached);
        return;
      }
      // The attachment travels with the text: uploaded, it keeps its id for the next send.
      const stash = () => {
        stashFailedDraftForThread(turn.threadKey, turn.composerText);
        stashAttachmentForThread(turn.threadKey, getThreadKey(), attached);
      };
      if (!turn.isCurrentView()) {
        if (!turn.leavesComposer) stash();
        return;
      }
      setPendingOutboundId(null);
      editThread((prev) => prev.filter((m) => m.id !== optimisticId), "failed_send_withdrawn");
      newMessageCountRef.current = Math.max(0, newMessageCountRef.current - 1);
      if (turn.leavesComposer) {
        // Nothing of the composer's went: only the bubble comes back.
      } else if (getThreadKey() !== turn.threadKey) {
        stash();
      } else if (!pendingAttachmentRef.current && shouldRestoreFailedSend(inputRef.current, turn.composerText)) {
        setInput(turn.composerText);
        setPendingAttachment(attached);
      } else {
        discardDraftAttachment(token, attached);
        feedback?.error(t("chat.restore_draft_blocked"));
      }
      sendInFlightRef.current = false;
      setSendPhase("idle");
    },
    [
      stashFailedDraftForThread, stashAttachmentForThread, editThread, newMessageCountRef, getThreadKey,
      pendingAttachmentRef, inputRef, setInput, setPendingAttachment, token, setPendingOutboundId,
      sendInFlightRef, setSendPhase, feedback, t,
    ],
  );
}
