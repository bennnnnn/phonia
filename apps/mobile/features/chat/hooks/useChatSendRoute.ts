import { useCallback, type MutableRefObject } from "react";

import { useActionFeedbackOptional } from "@/contexts/ActionFeedbackContext";
import type { SendTurn } from "@/features/chat/hooks/useRestoreFailedSend";
import type { DotsTicket, SendTurnStart } from "@/features/chat/hooks/useTurnStart";
import { uploadSendAttachment } from "@/features/chat/hooks/useSendAttachment";
import { buildPendingSendAfterCreate, type SendMessageOptions } from "@/features/chat/model/sendLogic";
import { attachmentErrorMessage } from "@/features/attachments/model/attachmentErrors";
import type { PendingAttachment } from "@/features/attachments/model/attachments";
import { flushEmailDrafts } from "@/features/drafts/model/emailDraftFlush";

/** A send whose bubble, and typing dots when they could go up, are on screen. */
export type PaintedSend = SendTurn & {
  optimisticId: string;
  /** The typing dots that went up with the bubble; null when none could. */
  dots: DotsTicket | null;
  /** The composer view at the tap; a new chat's send is dropped if the view moves on first. */
  version: number;
};

type SendPhase = "idle" | "preparing" | "uploading" | "creating";
type PendingChatSend = ReturnType<typeof buildPendingSendAfterCreate>;

type Options = {
  token: string | null;
  chatId: string | null;
  /**
   * False when the chat refused the send before showing it (say, a regenerate began), or Stop took it
   * back before it went out.
   */
  sendMessage: (text: string, opts?: SendMessageOptions) => Promise<boolean>;
  sendStart: SendTurnStart;
  t: (key: string, options?: Record<string, unknown>) => string;
  setPendingOutboundId: (id: string | null) => void;
  sendInFlightRef: MutableRefObject<boolean>;
  setSendPhase: (phase: SendPhase) => void;
  /** Takes the bubble back and returns the draft to the thread it was typed in. */
  restoreFailedSend: (turn: SendTurn, optimisticId: string, attached: PendingAttachment | null) => void;
  /** A send for a chat that does not exist yet: it creates one and waits for its id. */
  sendToNewChat: (send: PaintedSend, pending: PendingChatSend, giveBack: () => void) => Promise<void>;
};

/**
 * Everything a painted send waits on before it is handed over, in one place. With
 * no dots at the tap the last reply was still saving (after its `stream_end`): the
 * send goes after that reply's `done`. Another wait joins this list as one more
 * promise.
 */
function dispatchGates(send: PaintedSend, sendStart: SendTurnStart): Promise<unknown> {
  const gates: Promise<void>[] = [];
  if (!send.dots) gates.push(sendStart.whenReplySettled(send.optimisticId));
  return Promise.all(gates);
}

/**
 * Where a send goes once its bubble is painted: to chat, once its file and drafts are
 * ready, waiting on its `dispatchGates` meanwhile. A send stopped or refused on the way takes its bubble
 * and dots back and returns the draft, so nothing is lost or left behind.
 */
export function useChatSendRoute({
  token,
  chatId,
  sendMessage,
  sendStart,
  t,
  setPendingOutboundId,
  sendInFlightRef,
  setSendPhase,
  restoreFailedSend,
  sendToNewChat,
}: Options) {
  const feedback = useActionFeedbackOptional();

  return useCallback(
    async (send: PaintedSend) => {
      const drafts = flushEmailDrafts();
      // Started now, so a bubble that waits says "Sending" from the first beat.
      const gates = dispatchGates(send, sendStart);
      let attached = send.attachment;
      const giveBack = () => {
        send.dots?.cancel();
        restoreFailedSend(send, send.optimisticId, attached);
      };
      const stillSending = () => send.isCurrentView() && (send.dots?.current() ?? true);
      /** The last check before either hand-over: every gate open, and the send still stands. */
      const clearToHandOver = async () => {
        await gates;
        return stillSending();
      };

      const authToken = token;
      if (!authToken || !stillSending()) return giveBack();
      let attachmentIds: string[] | undefined;
      if (attached) {
        try {
          ({ ids: attachmentIds, attachment: attached } = await uploadSendAttachment(authToken, attached));
        } catch (error) {
          giveBack();
          if (send.isCurrentView()) feedback?.error(attachmentErrorMessage(error, t));
          return;
        }
      }
      if (!(await drafts) || !(await clearToHandOver())) return giveBack();

      const pending = buildPendingSendAfterCreate({
        text: send.text,
        composerText: send.composerText,
        attached,
        attachmentIds,
        optimisticId: send.optimisticId,
      });
      if (!chatId) return sendToNewChat(send, pending, giveBack);
      const sending = sendMessage(pending.text, pending);
      setPendingOutboundId(null);
      sendInFlightRef.current = false;
      setSendPhase("idle");
      if (!(await sending)) giveBack();
    },
    [
      chatId, token, sendStart, restoreFailedSend, t, setSendPhase, feedback, sendToNewChat,
      sendMessage,
      setPendingOutboundId, sendInFlightRef,
    ],
  );
}
