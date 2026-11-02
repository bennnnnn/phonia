import { useCallback, type RefObject } from "react";
import { randomUUID } from "expo-crypto";

import type { Message } from "@/lib/api";
import { clientGeoWsFields, type ClientGeo } from "@/features/chat/model/clientGeo";
import { canRegenerate, headRejectedSend, type ChatTurnEvent, type ChatTurnState } from "@/features/chat/model/chatTurnCore";
import { whenOpenedPageSettled } from "@/features/chat/model/openedPage";
import type { ComposerSendDraft, PendingSend, RejectedSend, SendMessageOptions } from "@/features/chat/model/sendLogic";
import type { useChatTransport } from "@/features/chat/hooks/useChatTransport";

type Options = {
  token: string | null;
  chatId: string | null;
  isCurrentView: () => boolean;
  /** The turn machine (useChat holds it) and one step of it. */
  turn: RefObject<ChatTurnState>;
  step: (event: ChatTurnEvent) => void;
  messagesRef: RefObject<Message[]>;
  transport: Pick<ReturnType<typeof useChatTransport>, "connect" | "sendViaSse" | "regenerateViaSse" | "currentSocket">;
  onUnreachable: () => void;
};

/**
 * What the user does to a turn: send, retry a rejected send, regenerate, stop. Each
 * steps the turn machine, then talks to the server over the socket or, when the socket
 * is not open, over SSE; an attempt the user has since replaced goes no further.
 */
export function useChatTurnActions({ token, chatId, isCurrentView, turn, step, messagesRef, transport, onUnreachable }: Options) {
  const { connect, sendViaSse, regenerateViaSse, currentSocket } = transport;

  /**
   * Connect for a turn. A turn on a chat whose page is still being read waits for it
   * (`openedPage.ts`; `turn` is the send, null for a regeneration): false when it must
   * not go out.
   */
  const ensureConnected = useCallback(async (pending: PendingSend | null) => {
    const opened = whenOpenedPageSettled(chatId, pending);
    try {
      await connect();
    } catch {
      onUnreachable();
    }
    return opened;
  }, [chatId, connect, onUnreachable]);

  /**
   * False when refused before anything showed, or stopped before it went out: the caller
   * then takes the bubble back and returns the draft. Past that, whatever ends the turn
   * owns its bubble.
   */
  const dispatchSend = useCallback(async (
    content: string,
    options?: SendMessageOptions,
    retrying?: RejectedSend,
  ): Promise<boolean> => {
    const current = turn.current;
    // Dots the composer raised at the tap are this send's own: they do not make it busy.
    const ownDots = current.earlyDots !== null && current.earlyDots === current.attempt;
    if (!token || !chatId || !isCurrentView() || (current.phase !== "idle" && !ownDots)) return false;
    // One name for every send of this message (a replay, Retry): the server runs it once.
    const clientMessageId = retrying?.clientMessageId ?? randomUUID();
    step({ type: "send", content, options, retrying, clientMessageId });
    const { attempt, ttftTurnId, pending } = turn.current;
    // It must not go: the opened-page read took it back (its chat is gone, or the view
    // left), or Stop did, and then the caller returns the draft (false).
    if (!(await ensureConnected(pending)) || !isCurrentView() || turn.current.attempt !== attempt) {
      return pending?.takenBack !== "stop";
    }
    step({ type: "send_dispatched", retrying });
    const sseOptions = {
      attachmentIds: options?.attachmentIds,
      model: options?.model,
      clientGeo: options?.clientGeo,
      ttftTurnId,
      clientMessageId,
    };
    const socket = currentSocket();
    if (!socket?.isOpen() || socket.shouldUseSse()) {
      await sendViaSse(content, sseOptions);
      return true;
    }
    step({
      type: "fallback_armed",
      fallback: { transport: socket, retry: () => sendViaSse(content, sseOptions), idempotent: true },
    });
    socket.sendMessage({
      content,
      attachment_ids: options?.attachmentIds ?? [],
      model: options?.model ?? null,
      client_message_id: clientMessageId,
      ...clientGeoWsFields(options?.clientGeo),
    });
    return true;
  }, [token, chatId, isCurrentView, turn, step, ensureConnected, sendViaSse, currentSocket]);

  const sendMessage = useCallback(
    (content: string, options?: SendMessageOptions) => dispatchSend(content, options),
    [dispatchSend],
  );

  const retryRejectedSend = useCallback(async (): Promise<boolean> => {
    if (!token || !chatId || !isCurrentView() || turn.current.phase !== "idle") return false;
    const rejected = headRejectedSend(turn.current);
    if (!rejected || rejected.reason !== "send_rejected") return false;
    const attempt = turn.current.attempt + 1;
    await dispatchSend(rejected.content, rejected.options, rejected);
    return isCurrentView() && turn.current.attempt === attempt;
  }, [token, chatId, isCurrentView, turn, dispatchSend]);

  const restoreRejectedAttachmentDraft = useCallback((restore: (draft: ComposerSendDraft) => boolean): boolean => {
    if (!token || !chatId || !isCurrentView() || turn.current.phase !== "idle") return false;
    const rejected = headRejectedSend(turn.current);
    if (!rejected || rejected.reason !== "attachment_rejected") return false;
    const original = rejected.options.composerDraft ?? { text: rejected.content, attachment: null };
    const attachment = original.attachment ? { ...original.attachment } : null;
    // The server rejected this reference: a local file uploads again on send, or is replaced.
    if (attachment) delete attachment.existingAttachmentId;
    if (!restore({ text: original.text, attachment })) return false;
    step({ type: "rejected_draft_restored" });
    return true;
  }, [token, chatId, isCurrentView, turn, step]);

  const beginRegenerateUi = useCallback(() => {
    if (!isCurrentView()) return;
    // Refused mid-reply: the caller stops before it asks for anything.
    if (turn.current.phase !== "idle") return () => false;
    step({ type: "regenerate_ui", messages: messagesRef.current });
    const { attempt } = turn.current;
    return () => isCurrentView() && turn.current.attempt === attempt;
  }, [isCurrentView, step, messagesRef, turn]);

  const cancelRegenerateUi = useCallback(() => {
    if (isCurrentView()) step({ type: "regenerate_cancelled" });
  }, [isCurrentView, step]);

  const regenerateResponse = useCallback(async (model?: string | null, clientGeo?: ClientGeo | null) => {
    if (!token || !chatId || !isCurrentView() || !canRegenerate(turn.current)) return;
    step({ type: "regenerate", messages: messagesRef.current });
    const { attempt } = turn.current;
    if (!(await ensureConnected(null))) return;
    if (!isCurrentView() || turn.current.attempt !== attempt) return;
    const socket = currentSocket();
    if (!socket?.isOpen() || socket.shouldUseSse()) {
      await regenerateViaSse(model, clientGeo);
      return;
    }
    step({ type: "fallback_armed", fallback: { transport: socket, retry: () => regenerateViaSse(model, clientGeo) } });
    socket.sendRegenerate({ model: model ?? null, ...clientGeoWsFields(clientGeo) });
  }, [token, chatId, isCurrentView, step, messagesRef, turn, ensureConnected, regenerateViaSse, currentSocket]);

  const stopGeneration = useCallback(() => {
    if (isCurrentView()) step({ type: "stop" });
  }, [isCurrentView, step]);

  return {
    sendMessage,
    retryRejectedSend,
    restoreRejectedAttachmentDraft,
    beginRegenerateUi,
    cancelRegenerateUi,
    regenerateResponse,
    stopGeneration,
  };
}
