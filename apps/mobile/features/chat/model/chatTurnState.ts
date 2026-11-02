import type { Message } from "@/lib/api";
import { isAbortError } from "@/lib/api/abort";
import { ApiRequestError } from "@/lib/api/errorBody";
import { refusalCode } from "@/features/chat/model/errorMessage";
import { popLastAssistantMessage, restoreAssistantMessage } from "@/features/chat/model/regenerateLogic";
import type { PendingSend } from "@/features/chat/model/sendLogic";
import { mergeReconciledPage, SSE_DROPPED_TURN_POLLS } from "@/features/chat/model/turnReconcile";
import type { ChatWsFallbackSignal, ChatWsTransport } from "@/features/chat/model/wsTransport";
import { applyFrame } from "@/features/chat/model/chatTurnFrames";
import {
  canRegenerate,
  clearStreamingBubble,
  cue,
  dropUndispatchedRetry,
  keepStreamedBubble,
  messages,
  openStream,
  preservePartialStream,
  queueUnsaved,
  reportError,
  restoreRegenerateBackup,
  setRejected,
  type ChatTurnCommand,
  type ChatTurnEvent,
  type ChatTurnState,
  type ChatTurnStep,
  type Out,
} from "@/features/chat/model/chatTurnCore";

/** Stop may still have a final frame in flight; a fresh socket keeps it off the next turn. */
function leaveStoppedTurn(s: ChatTurnState, out: Out): void {
  if (!s.stoppedStreamedId) return;
  out.push({ type: "drop_socket" });
  s.stoppedStreamedId = null;
}

function onSend(s: ChatTurnState, out: Out, event: Extract<ChatTurnEvent, { type: "send" }>, now: number): void {
  const { content, options, retrying, clientMessageId } = event;
  cue(out, "reset");
  // The dots the composer raised at the tap are this send's: it takes them over.
  if (s.earlyDots !== null && s.earlyDots === s.attempt) s.earlyDots = null;
  const attempt = (s.attempt += 1);
  leaveStoppedTurn(s, out);
  // Its own bubble, or the one painted at the tap again if a reload took it away.
  const bubbleId = options?.skipUserBubble ? options.trackSendingMessageId : `local-${now}-${attempt}`;
  const trackedId = bubbleId ?? null;
  if (bubbleId) {
    const bubble: Message = {
      id: bubbleId,
      role: "user",
      content,
      model: null,
      local_image_uri: options?.localImageUri ?? null,
      local_file_uri: options?.localFileUri ?? null,
      local_file_name: options?.localFileName ?? null,
      local_file_content_type: options?.localFileContentType ?? null,
      created_at: new Date(now).toISOString(),
    };
    messages(out, (previous) => (previous.some((message) => message.id === bubbleId) ? previous : [...previous, bubble]));
  }
  const draft = options?.composerDraft;
  s.pending = {
    content,
    messageId: trackedId,
    retryingRejected: retrying != null,
    dispatched: false,
    // One name for every send of this message (a replay, Retry): the server runs it once.
    clientMessageId,
    options: {
      ...options,
      skipUserBubble: false,
      trackSendingMessageId: undefined,
      attachmentIds: options?.attachmentIds?.slice(),
      composerDraft: draft ? { text: draft.text, attachment: draft.attachment ? { ...draft.attachment } : null } : undefined,
      clientGeo: options?.clientGeo ? { ...options.clientGeo } : options?.clientGeo,
    },
  };
  s.ttftTurnId = trackedId;
  openStream(s, out, options?.attachmentIds?.length ? "reading_files" : undefined);
}

function onRegenerateUi(s: ChatTurnState, out: Out, current: Message[]): void {
  s.attempt += 1;
  s.pending = null;
  s.ttftTurnId = null;
  out.push({ type: "clear_ttft" });
  s.regenerating = true;
  s.regenerateBackup = popLastAssistantMessage(current).backup;
  out.push({ type: "pop_for_regenerate" });
  openStream(s, out);
}

function onStop(s: ChatTurnState, out: Out, now: number): void {
  cue(out, "stopped");
  out.push({ type: "outcome", outcome: "report", completion: "stopped" });
  s.attempt += 1;
  s.earlyDots = null;
  // A turn still waiting to go out (for its chat's page, or the socket) never will: its
  // bubble goes now, and its sender returns the draft unless the page read already took it.
  const unsent = s.pending?.dispatched === false ? s.pending : null;
  out.push({ type: "withdraw_unsent", chatId: s.chatId, pending: s.pending });
  if (unsent) messages(out, (previous) => previous.filter((message) => message.id !== unsent.messageId));
  s.pending = null;
  if (s.chatId) setRejected(s, s.chatId, []);
  s.authFallback = null;
  s.regenerating = false;
  out.push({ type: "clear_ttft", turnId: s.ttftTurnId });
  s.ttftTurnId = null;
  out.push({ type: "abort_sse" });
  out.push({ type: "cancel_socket", streamedChars: s.draft?.content.length });
  s.phase = "idle";
  s.sendingMessageId = null;
  const draft = s.draft;
  s.buffer = "";
  s.draft = null;
  // The server keeps the previous answer until it commits a replacement:
  // a stop with no replacement tokens restores that answer.
  const backup = s.regenerateBackup;
  s.regenerateBackup = null;
  const stoppedId = `streamed-${now}`;
  messages(out, (previous) => {
    const streamingMsg = previous.find((m) => m.id === "streaming");
    if (!streamingMsg) return previous;
    const content = draft?.content ?? streamingMsg.content;
    if (!content.trim()) return restoreAssistantMessage(previous, backup);
    return keepStreamedBubble(previous, stoppedId, content, draft);
  });
  // The server's late `done` reconciles this bubble instead of appending a duplicate.
  s.stoppedStreamedId = stoppedId;
}

function onViewChanged(s: ChatTurnState, out: Out, chatId: string | null, session: number): void {
  s.authFallback = null;
  s.attempt += 1;
  dropUndispatchedRetry(s, out);
  s.pending = null;
  // Rejected sends and held edits wait across chats and newer sends, never into another account.
  if (session !== s.session) {
    s.rejected = new Map();
    s.heldEdits = new Map();
  }
  s.session = session;
  s.chatId = chatId;
  const held = chatId ? s.heldEdits.get(chatId) : undefined;
  if (chatId && held) {
    const rest = new Map(s.heldEdits);
    rest.delete(chatId);
    s.heldEdits = rest;
    for (const update of held) messages(out, update);
  }
  s.buffer = "";
  s.firstReply = false;
  s.regenerateBackup = null;
  s.stoppedStreamedId = null;
  s.regenerating = false;
  s.ttftTurnId = null;
  out.push({ type: "clear_ttft" });
  s.draft = null;
  s.phase = "idle";
  s.sendingMessageId = null;
  s.earlyDots = null;
}

/** An edit naming its chat changes the list only while that chat is on screen. */
export function editLands(s: ChatTurnState, chatId: string | undefined): boolean {
  return chatId === undefined || chatId === s.chatId;
}

/**
 * The turn itself is unchanged; edits reach the list in the order they arrive. One made for
 * another chat waits for that chat (onViewChanged): a picture that finished after the user
 * left, or before its new chat's id reached the screen (a render later), or while a reopened
 * chat's page read was out.
 */
function onThreadEdit(s: ChatTurnState, out: Out, event: Extract<ChatTurnEvent, { type: "thread_edit" }>): void {
  const { update, chatId } = event;
  const apply = typeof update === "function" ? update : () => update;
  if (editLands(s, chatId)) messages(out, apply);
  else if (chatId) s.heldEdits = new Map(s.heldEdits).set(chatId, [...(s.heldEdits.get(chatId) ?? []), apply]);
}

/** The server took this send (`start`, or a token shown): a dropped connection is not a rejection. */
function serverTookSend(s: ChatTurnState, pending: PendingSend | null): boolean {
  return !s.regenerateBackup && (Boolean(pending?.accepted) || s.buffer.trim().length > 0);
}

function settleWithServerPage(s: ChatTurnState, out: Out, page: Message[]): void {
  out.push({ type: "clear_ttft", turnId: s.ttftTurnId });
  s.ttftTurnId = null;
  s.sendingMessageId = null;
  s.phase = "idle";
  s.buffer = "";
  s.draft = null;
  messages(out, (previous) => mergeReconciledPage(previous, page));
  cue(out, "complete");
  if (!s.firstReply) {
    s.firstReply = true;
    out.push({ type: "first_reply" });
  }
}

function settleDroppedSocketTurn(s: ChatTurnState, out: Out, pending: PendingSend | null, messageSaved: boolean, now: number): void {
  if (s.phase === "idle") return;
  s.phase = "idle";
  const hadContent = s.buffer.trim().length > 0;
  const draft = s.draft;
  const failedBackup = s.regenerateBackup;
  s.regenerateBackup = null;
  s.buffer = "";
  s.draft = null;
  s.sendingMessageId = null;
  if (!hadContent) {
    out.push({ type: "clear_ttft", turnId: s.ttftTurnId ?? pending?.messageId });
    s.ttftTurnId = null;
  }
  const keptId = `streamed-${now}`;
  messages(out, (previous) => {
    if (!previous.some((m) => m.id === "streaming")) return previous;
    if (hadContent) return keepStreamedBubble(previous, keptId, draft?.content, draft);
    return restoreAssistantMessage(previous, failedBackup);
  });
  cue(out, "error");
  if (hadContent) {
    reportError(out, { key: "chat.error_connection_lost" });
  } else if (!failedBackup) {
    if (pending && !messageSaved) {
      queueUnsaved(s, out, pending, "send_rejected");
      reportError(out, { key: "chat.error_unreachable", code: "send_rejected" });
    } else {
      reportError(out, { key: "chat.error_connection_lost" });
    }
  }
}

/**
 * What a refused SSE stream said (its `ApiRequestError`), reported as the socket's error frame
 * is: a 503 `unavailable` says Recall is unavailable, where it said "Couldn't reach the server".
 */
function refusalReport(error: unknown): { message?: string; code?: string } {
  if (!(error instanceof ApiRequestError) || !error.code) return {};
  return { message: error.detail || undefined, code: refusalCode(error.code, error.fields.feature) };
}

function settleFailedSend(
  s: ChatTurnState,
  out: Out,
  failure: { error: unknown; ttftTurnId: string | null; pending: PendingSend | null; messageSaved: boolean },
  now: number,
): void {
  const { error, ttftTurnId, pending, messageSaved } = failure;
  out.push({ type: "clear_ttft", turnId: ttftTurnId ?? pending?.messageId });
  s.ttftTurnId = null;
  s.sendingMessageId = null;
  s.phase = "idle";
  if (!preservePartialStream(s, out, now)) {
    clearStreamingBubble(s, out);
    // A private HTTP timeout may come after the server received the turn. Only caller
    // cancellation is silent; uncertain delivery stays out of the unsaved queue.
    if (pending && !messageSaved && !isAbortError(error)) {
      queueUnsaved(s, out, pending, "send_rejected");
      reportError(out, { key: "chat.error_unreachable", code: "send_rejected" });
      return;
    }
  }
  reportError(out, { key: "chat.error_unreachable", ...refusalReport(error) });
}

function onSocketFallback(s: ChatTurnState, out: Out, transport: ChatWsTransport, signal: ChatWsFallbackSignal, now: number): void {
  if (signal.reason === "unauthorized") {
    // The server refuses auth before it takes the turn: only this refusal is safe to replay over SSE.
    const fallback = s.authFallback;
    if (!fallback && signal.duringTurn) {
      applyFrame(s, out, signal.payload, s.ttftTurnId, now);
      return;
    }
    s.authFallback = null;
    if (fallback?.transport === transport) out.push({ type: "retry_fallback", fallback });
    return;
  }
  if (signal.reason === "closed_unread" && signal.duringTurn) {
    // Closed (idle, or over the socket cap) without reading this send: replay it, unseen.
    const fallback = s.authFallback;
    if (fallback?.transport === transport) {
      s.authFallback = null;
      out.push({ type: "retry_fallback", fallback });
      return;
    }
  }
  // A probe found the socket dead before `start`: the send may or may not have arrived.
  // A message carries its name, so the server runs a replay of it once.
  const armed = s.authFallback;
  const unacknowledged = signal.reason === "unresponsive" && signal.duringTurn && armed?.transport === transport;
  if (unacknowledged && armed?.idempotent) {
    s.authFallback = null;
    out.push({ type: "retry_fallback", fallback: armed });
    return;
  }
  if (signal.reason === "first_event_timeout" || unacknowledged) {
    // No event does not prove the server missed the request: keep the bubble, never replay.
    s.authFallback = null;
    s.pending = null;
    out.push({ type: "clear_ttft", turnId: s.ttftTurnId });
    s.ttftTurnId = null;
    s.sendingMessageId = null;
    s.buffer = "";
    restoreRegenerateBackup(s, out);
    reportError(out, { key: "chat.error_unreachable" });
    cue(out, "error");
    return;
  }
  if (!signal.duringTurn) return;
  const pending = s.pending;
  s.pending = null;
  if (serverTookSend(s, pending) && s.phase !== "idle") {
    // The server finishes a turn whose socket dropped (and saves it on a deploy).
    out.push({ type: "follow_dropped_turn", follow: { via: "socket", pending } });
    return;
  }
  settleDroppedSocketTurn(s, out, pending, false, now);
}

function onSendFailed(s: ChatTurnState, out: Out, error: unknown, ttftTurnId: string | null, now: number): void {
  const pending = s.pending;
  s.pending = null;
  if (!isAbortError(error) && serverTookSend(s, pending) && s.phase !== "idle") {
    // A dropped SSE stream stops its turn on the server, which saves at once.
    out.push({ type: "follow_dropped_turn", follow: { via: "sse", pending, error, ttftTurnId }, polls: SSE_DROPPED_TURN_POLLS });
    return;
  }
  settleFailedSend(s, out, { error, ttftTurnId, pending, messageSaved: false }, now);
}

function onRegenerateFailed(s: ChatTurnState, out: Out, error: unknown, now: number): void {
  s.phase = "idle";
  if (preservePartialStream(s, out, now)) s.regenerateBackup = null;
  else restoreRegenerateBackup(s, out);
  reportError(out, { key: "chat.error_unreachable", ...refusalReport(error) });
}

/** Typing dots under the bubble the composer just painted, before its send goes out. */
function onDotsBegin(s: ChatTurnState, out: Out): void {
  if (s.phase !== "idle") return;
  s.attempt += 1;
  s.earlyDots = s.attempt;
  leaveStoppedTurn(s, out);
  openStream(s, out);
}

/** The early dots come down: the send went to image generation, or nowhere. */
function onDotsCancelled(s: ChatTurnState, out: Out, attempt: number): void {
  if (s.earlyDots === attempt) s.earlyDots = null;
  // Not this send's any more: a Stop, another turn or another view took them down.
  if (s.attempt !== attempt) return;
  s.attempt += 1;
  clearStreamingBubble(s, out);
  s.phase = "idle";
}

/**
 * A reply past `stream_end` whose `done` never came (its connection gone quiet): the
 * server has the turn, so leave that connection and reload the chat until the saved
 * reply lands, as after a drop. A regenerated reply has no new message to find there;
 * it settles as a dropped one at once.
 */
function onUnconfirmedReply(s: ChatTurnState, out: Out, now: number): void {
  if (s.phase !== "finalizing") return;
  // A late `done` then reaches nothing: the socket and stream it would come on are closed.
  out.push({ type: "drop_socket" });
  out.push({ type: "abort_sse" });
  if (s.regenerateBackup) {
    settleDroppedSocketTurn(s, out, null, true, now);
    return;
  }
  out.push({ type: "follow_dropped_turn", follow: { via: "socket", pending: null } });
}

/** One step of the chat turn at `now`: the next state and what useChat must do, in order. */
export function reduceChatTurn(state: ChatTurnState, event: ChatTurnEvent, now: number): ChatTurnStep {
  const s = { ...state };
  const out: ChatTurnCommand[] = [];
  switch (event.type) {
    case "view_changed":
      onViewChanged(s, out, event.chatId, event.session);
      break;
    case "send":
      onSend(s, out, event, now);
      break;
    case "send_dispatched": {
      const retrying = event.retrying;
      // Retry stays offered while the handshake runs; it is used up only when sending begins.
      if (retrying && s.chatId) setRejected(s, s.chatId, (s.rejected.get(s.chatId) ?? []).filter((item) => item !== retrying));
      if (s.pending) s.pending = { ...s.pending, dispatched: true };
      break;
    }
    case "fallback_armed":
      s.authFallback = event.fallback;
      break;
    case "regenerate_ui":
      // Only from rest: during a reply it would cut that reply and start a second
      // stream (the button is hidden then, not refused).
      if (s.phase === "idle") onRegenerateUi(s, out, event.messages);
      break;
    case "regenerate_backup":
      s.regenerateBackup = event.backup;
      break;
    case "regenerate":
      if (!canRegenerate(s)) break;
      cue(out, "reset");
      if (s.stoppedStreamedId) {
        out.push({ type: "drop_socket" });
        s.stoppedStreamedId = null;
      }
      if (!s.regenerating) onRegenerateUi(s, out, event.messages);
      s.attempt += 1;
      break;
    case "regenerate_cancelled":
      restoreRegenerateBackup(s, out);
      break;
    case "stop":
      onStop(s, out, now);
      break;
    case "frame":
      applyFrame(s, out, event.payload, event.ttftTurnId, now);
      break;
    case "socket_fallback":
      onSocketFallback(s, out, event.transport, event.signal, now);
      break;
    case "send_failed":
      onSendFailed(s, out, event.error, event.ttftTurnId, now);
      break;
    case "regenerate_failed":
      onRegenerateFailed(s, out, event.error, now);
      break;
    case "dropped_turn": {
      const { follow, result } = event;
      if (result.state === "answered" && result.page) {
        settleWithServerPage(s, out, result.page);
        break;
      }
      // Offer again only what a reload showed is not in the chat.
      const messageSaved = result.state !== "missing";
      if (follow.via === "duplicate") {
        // Minutes without the message in the chat: that send never saved, and the server's
        // hold on its name can outlive a machine that died. Retry sends it under a new name.
        const renamed = follow.pending && { ...follow.pending, clientMessageId: undefined };
        settleDroppedSocketTurn(s, out, messageSaved ? follow.pending : renamed, messageSaved, now);
      } else if (follow.via === "socket") settleDroppedSocketTurn(s, out, follow.pending, messageSaved, now);
      else settleFailedSend(s, out, { error: follow.error, ttftTurnId: follow.ttftTurnId, pending: follow.pending, messageSaved }, now);
      break;
    }
    case "rejected_draft_restored":
      if (s.chatId) setRejected(s, s.chatId, (s.rejected.get(s.chatId) ?? []).slice(1));
      break;
    case "dots_begin":
      onDotsBegin(s, out);
      break;
    case "dots_cancelled":
      onDotsCancelled(s, out, event.attempt);
      break;
    case "send_waiting":
      s.sendingMessageId = event.messageId;
      break;
    case "unconfirmed_reply":
      onUnconfirmedReply(s, out, now);
      break;
    case "thread_edit":
      onThreadEdit(s, out, event);
      break;
  }
  return { state: s, commands: out };
}
