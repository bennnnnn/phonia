import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { Message } from "@/lib/api";
import { getSessionGeneration } from "@/lib/auth";
import { useChatTransport } from "@/features/chat/hooks/useChatTransport";
import { useChatTurnActions } from "@/features/chat/hooks/useChatTurnActions";
import { useDroppedTurnReconcile } from "@/features/chat/hooks/useDroppedTurnReconcile";
import { useStreamingDraftPublisher } from "@/features/chat/hooks/useStreamingDraftPublisher";
import { useThreadEdits } from "@/features/chat/hooks/useThreadEdits";
import { useTurnStart } from "@/features/chat/hooks/useTurnStart";
import { headRejectedSend, initialChatTurnState, type ChatTurnEvent } from "@/features/chat/model/chatTurnCore";
import { runChatTurnCommands, type ChatTurnEffects } from "@/features/chat/model/chatTurnEffects";
import { createTurnEffectsSlot } from "@/features/chat/model/turnEffectsSlot";
import { reduceChatTurn } from "@/features/chat/model/chatTurnState";
import { popLastAssistantMessage } from "@/features/chat/model/regenerateLogic";
import type { RejectedSend } from "@/features/chat/model/sendLogic";
import type { TurnUsage } from "@/features/chat/model/socketReduce";
import { createStreamCueGate } from "@/features/chat/model/streamFeedback";

type UseChatOptions = {
  /** Called with the new title when the server sends one after first reply */
  onFirstReply?: () => void;
  /** Called when the server or socket reports an error */
  onError?: (message: string, code?: string) => void;
  /** Refresh lists/reminders after chat may have synced todos */
  onTodosSync?: () => void;
  /** The day's usage a finished turn reports. */
  onUsage?: (usage: TurnUsage) => void;
};

/**
 * The chat on screen and its turn. The turn is the state machine in chatTurnState.ts;
 * this hook holds it, runs the commands each step returns and mirrors what the screen
 * shows into React state (code-health audit CLAR-04). It is the thread's one owner: every
 * other writer changes the list through `editThread`, a step of the same machine.
 */
export function useChat(token: string | null, chatId: string | null, options: UseChatOptions = {}) {
  const { t } = useTranslation();
  const [messages, setMessages] = useState<Message[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const [sendingMessageId, setSendingMessageId] = useState<string | null>(null);
  const [rejectedSend, setRejectedSend] = useState<RejectedSend | null>(null);
  const [cue] = useState(createStreamCueGate);
  const publishDraft = useStreamingDraftPublisher();
  const authenticated = token != null;
  const sessionGeneration = getSessionGeneration();
  const turn = useRef(initialChatTurnState(chatId, sessionGeneration));
  const messagesRef = useRef(messages);
  // A -> B -> A is a new view: callbacks for the first A stay detached.
  const viewIdentity = useMemo(() => ({ chatId, authenticated, sessionGeneration }), [chatId, authenticated, sessionGeneration]);
  const view = useRef({ mounted: true, identity: viewIdentity });
  const [effects] = useState(() => createTurnEffectsSlot<ChatTurnEffects>(runChatTurnCommands));
  const isCurrentView = useCallback(
    () => view.current.mounted && view.current.identity === viewIdentity && getSessionGeneration() === viewIdentity.sessionGeneration,
    [viewIdentity],
  );

  /** One step of the turn: reduce, run what it asks for, show what changed. */
  const step = useCallback((event: ChatTurnEvent) => {
    const previous = turn.current;
    const next = reduceChatTurn(previous, event, Date.now());
    turn.current = next.state;
    effects.run(next.commands);
    const shown = turn.current;
    if (shown.phase !== previous.phase) {
      setStreaming(shown.phase !== "idle");
      setFinalizing(shown.phase === "finalizing");
    }
    if (shown.sendingMessageId !== previous.sendingMessageId) setSendingMessageId(shown.sendingMessageId);
    const head = headRejectedSend(shown);
    if (head !== headRejectedSend(previous)) setRejectedSend(head);
    if (shown.draft !== previous.draft) publishDraft(shown.draft);
  }, [effects, publishDraft]);

  const transport = useChatTransport({
    chatId,
    isCurrentView,
    ttftTurnId: () => turn.current.ttftTurnId,
    onPayload: (boundChatId, payload, ttftTurnId) => {
      if (isCurrentView() && boundChatId === chatId) step({ type: "frame", payload, ttftTurnId });
    },
    onFallback: (socket, signal) => {
      if (!isCurrentView() || transport.currentSocket() !== socket || signal.reason === "connect_timeout") return;
      step({ type: "socket_fallback", transport: socket, signal });
    },
    onSendFailure: (error, ttftTurnId) => step({ type: "send_failed", error, ttftTurnId }),
    onRegenerateFailure: (error) => step({ type: "regenerate_failed", error }),
  });
  const { connect, sendViaSse, regenerateViaSse, currentSocket, detach } = transport;
  const followDroppedTurn = useDroppedTurnReconcile({
    token,
    chatId,
    isCurrentView,
    messages: () => messagesRef.current,
    attempt: () => turn.current.attempt,
    streaming: () => turn.current.phase !== "idle",
  });

  /** Regenerate pops the last answer; a newer list's answer is the one kept to restore. */
  const popForRegenerate = useCallback(() => {
    messagesRef.current = popLastAssistantMessage(messagesRef.current).messages;
    setMessages((previous) => {
      const latest = popLastAssistantMessage(previous);
      const backup = latest.backup;
      if (backup) turn.current = reduceChatTurn(turn.current, { type: "regenerate_backup", backup }, Date.now()).state;
      messagesRef.current = latest.messages;
      return latest.messages;
    });
  }, []);

  useLayoutEffect(() => {
    messagesRef.current = messages;
    view.current.identity = viewIdentity;
  }, [messages, viewIdentity]);
  useLayoutEffect(() => {
    effects.attach({
      t,
      setMessages,
      popForRegenerate,
      cue,
      onError: options.onError,
      onFirstReply: options.onFirstReply,
      onTodosSync: options.onTodosSync,
      onUsage: options.onUsage,
      dropSocket: transport.dropSocket,
      abortSse: transport.abortSse,
      cancelSocket: transport.cancelSocket,
      followDroppedTurn: (follow, polls, pollMs) =>
        followDroppedTurn((result) => step({ type: "dropped_turn", follow, result }), polls, pollMs),
    });
  }, [
    t, popForRegenerate, cue, options.onError, options.onFirstReply, options.onTodosSync, options.onUsage,
    transport.dropSocket, transport.abortSse, transport.cancelSocket, followDroppedTurn, step, effects,
  ]);

  useEffect(() => {
    const current = view.current;
    current.mounted = true;
    return () => { current.mounted = false; };
  }, []);

  // A new chat or account: the transport detaches (SSE drains, as a WebSocket close would).
  useEffect(() => {
    detach();
    step({ type: "view_changed", chatId, session: sessionGeneration });
  }, [viewIdentity, chatId, sessionGeneration, detach, step]);

  const editThread = useThreadEdits({ chatId, isCurrentView, step, turn });

  const onUnreachable = useCallback(() => effects.current?.onError?.(t("chat.error_unreachable")), [effects, t]);
  const actions = useChatTurnActions({
    token, chatId, isCurrentView, turn, step, messagesRef, transport: { connect, sendViaSse, regenerateViaSse, currentSocket }, onUnreachable,
  });
  const sendStart = useTurnStart({ canStart: Boolean(token && chatId), isCurrentView, turn, step, streaming, finalizing });

  return { messages, editThread, streaming, finalizing, sendingMessageId, rejectedSend, ...actions, sendStart, connect };
}
