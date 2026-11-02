import { useCallback, type MutableRefObject } from "react";

import { useComposerDraftApi } from "@/features/chat/context/ComposerDraftContext";
import { useActionFeedbackOptional } from "@/contexts/ActionFeedbackContext";
import type { SendTurn } from "@/features/chat/hooks/useRestoreFailedSend";
import type { DotsTicket, SendTurnStart } from "@/features/chat/hooks/useTurnStart";
import { uploadSendAttachment } from "@/features/chat/hooks/useSendAttachment";
import { buildPendingSendAfterCreate, type SendMessageOptions } from "@/features/chat/model/sendLogic";
import { clearPendingChatTtft } from "@/features/chat/model/latency";
import { resolveSendIntercept, type SendIntercept } from "@/features/chat/model/sendIntercept";
import { shouldRestoreFailedSend } from "@/features/chat/model/composerThreadDraft";
import { attachmentErrorMessage } from "@/features/attachments/model/attachmentErrors";
import type { PendingAttachment } from "@/features/attachments/model/attachments";
import { flushEmailDrafts } from "@/features/drafts/model/emailDraftFlush";
import type { ImageGenSubmit } from "@/features/images/hooks/useImageGeneration";
import { resolveClientGeoForQuery } from "@/features/chat/model/resolveClientGeoForQuery";
import type { Message, User } from "@/lib/api";

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
  messages: Message[];
  selectedModel: string;
  imageGenerating: boolean;
  onGenerateImage?: (request: ImageGenSubmit) => void;
  /**
   * False when the chat refused the send before showing it (say, a regenerate began), or Stop took it
   * back before it went out.
   */
  sendMessage: (text: string, opts?: SendMessageOptions) => Promise<boolean>;
  sendStart: SendTurnStart;
  updateUser: (patch: Partial<User>) => Promise<void>;
  /** The profile's location switch is already on: the turn need not wait for it to save. */
  locationEnabled: boolean;
  t: (key: string, options?: Record<string, unknown>) => string;
  pendingAttachmentRef: MutableRefObject<PendingAttachment | null>;
  setPendingAttachment: (value: PendingAttachment | null) => void;
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
 * Where a send goes once its bubble is painted: the server reads whether it is a
 * picture (POST /images/intent) while the bubble is already up, then a picture is
 * handed to image generation under that bubble, and anything else goes to chat
 * once its location, file and drafts are ready. Either way it waits on its
 * `dispatchGates` meanwhile. A send stopped or refused on the way takes its bubble
 * and dots back and returns the draft, so nothing is lost or left behind.
 */
export function useChatSendRoute({
  token,
  chatId,
  messages,
  selectedModel,
  imageGenerating,
  onGenerateImage,
  sendMessage,
  sendStart,
  updateUser,
  locationEnabled,
  t,
  pendingAttachmentRef,
  setPendingAttachment,
  setPendingOutboundId,
  sendInFlightRef,
  setSendPhase,
  restoreFailedSend,
  sendToNewChat,
}: Options) {
  const { setInput, inputRef, stashFailedDraftForThread, getThreadKey } = useComposerDraftApi();
  const feedback = useActionFeedbackOptional();

  /** A picture is drawn under the painted bubble; a request that fails to save comes back to the composer. */
  const handToImageGeneration = useCallback(
    (intercept: Extract<SendIntercept, { kind: "generate" }>, send: PaintedSend, drafts: Promise<boolean>) => {
      const restoreImageDraft = () => {
        if (!send.isCurrentSession() || send.leavesComposer) return;
        if (!send.isCurrentView() || getThreadKey() !== send.threadKey) {
          stashFailedDraftForThread(send.threadKey, send.composerText);
          return;
        }
        if (!pendingAttachmentRef.current && shouldRestoreFailedSend(inputRef.current, send.composerText)) {
          setInput(send.composerText);
          setPendingAttachment(send.attachment);
          return;
        }
        feedback?.error(t("chat.restore_draft_blocked"));
      };
      send.dots?.cancel();
      // A picture has no first token: its time-to-first-token sample is dropped.
      clearPendingChatTtft(send.optimisticId);
      onGenerateImage?.({
        prompt: intercept.prompt,
        userMessage: send.text,
        aspectRatio: null,
        referenceAttachment: intercept.reference?.attachment,
        referenceAttachmentIds: intercept.reference?.ids,
        persistenceReady: drafts,
        onPersistenceFailure: restoreImageDraft,
        userMessageId: send.optimisticId,
      });
      setPendingOutboundId(null);
      sendInFlightRef.current = false;
      setSendPhase("idle");
    },
    [
      getThreadKey, stashFailedDraftForThread, pendingAttachmentRef, inputRef, setInput, setPendingAttachment,
      feedback, t, onGenerateImage, setPendingOutboundId, sendInFlightRef, setSendPhase,
    ],
  );

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

      const deciding = resolveSendIntercept({
        text: send.text,
        attachment: attached,
        chatId,
        messages,
        canGenerate: Boolean(onGenerateImage),
        imageGenerating,
        token,
        isCurrentView: send.isCurrentView,
      });
      const intercept = deciding instanceof Promise ? await deciding : deciding;
      if (intercept.kind === "drop" || intercept.kind === "stale" || !stillSending()) return giveBack();
      if (intercept.kind === "generate") {
        if (!(await clearToHandOver())) return giveBack();
        return handToImageGeneration(intercept, send, drafts);
      }

      const authToken = token;
      if (!authToken) return giveBack();
      // The fix goes with the turn. The server reads one only from a user whose
      // location is on, so only switching it on has to save before the turn goes.
      const persistLocation = (patch: Partial<User>) => {
        const saving = updateUser(patch);
        if (!locationEnabled) return saving;
        void saving.catch(() => undefined);
      };
      const geo = await resolveClientGeoForQuery(authToken, send.text, t, persistLocation);
      if (!geo.ok || !stillSending()) return giveBack();
      // The fix is in: "Locating…" gives way to the upload, or to nothing.
      setSendPhase(attached ? "uploading" : "preparing");
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
        clientGeo: geo.clientGeo,
        model: selectedModel,
      });
      if (!chatId) return sendToNewChat(send, pending, giveBack);
      const sending = sendMessage(pending.text, pending);
      setPendingOutboundId(null);
      sendInFlightRef.current = false;
      setSendPhase("idle");
      if (!(await sending)) giveBack();
    },
    [
      chatId, messages, onGenerateImage, imageGenerating, token, sendStart, restoreFailedSend, handToImageGeneration,
      t, updateUser, locationEnabled, setSendPhase, feedback, selectedModel, sendToNewChat, sendMessage,
      setPendingOutboundId, sendInFlightRef,
    ],
  );
}
