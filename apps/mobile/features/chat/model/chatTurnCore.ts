import type { Message } from "@/lib/api";
import type { StreamingDraft } from "@/features/chat/model/streamingDraftStore";
import { restoreAssistantMessage } from "@/features/chat/model/regenerateLogic";
import { replaceStreamingMessageWithPartial, withStreamingPlaceholder } from "@/features/chat/model/partialStream";
import type { PendingSend, RejectedSend, SendMessageOptions } from "@/features/chat/model/sendLogic";
import type { ChatSsePayload } from "@/features/chat/model/sse";
import type { TurnUsage } from "@/features/chat/model/socketReduce";
import type { ChatTurnOutcomeProperties } from "@/features/chat/model/latencyReporter";
import type { DroppedTurnResult } from "@/features/chat/model/turnReconcile";
import type { ChatWsFallbackSignal, ChatWsTransport, WsSendFallback } from "@/features/chat/model/wsTransport";
import type { ThreadEditSource, ThreadUpdate } from "@/features/chat/model/threadEdit";

/**
 * The chat turn as one state machine (code-health audit CLAR-04): a send or regenerate
 * opens a turn, socket and SSE frames move it, Stop, a failure or a new view closes it.
 * `reduceChatTurn` (chatTurnState.ts) is pure; useChat holds the state and runs the
 * commands it returns. The state lives outside React render state on purpose: every
 * token changes it, and a re-render per token is what the streaming draft store avoids.
 */
type ChatTurnPhase = "idle" | "streaming" | "finalizing";

/** A WebSocket send the server may still refuse before `start`; replayed over SSE then. */
type AuthFallback = WsSendFallback;

export type ChatTurnState = {
  /** The chat on screen, in which sign-in session; rejected sends are kept per chat. */
  chatId: string | null;
  session: number;
  /**
   * Edits made for a chat while another was on screen (a picture that finished after the
   * user left its chat, or before its new chat reached the screen), applied in order when
   * that chat is shown.
   */
  heldEdits: ReadonlyMap<string, readonly ((previous: Message[]) => Message[])[]>;
  phase: ChatTurnPhase;
  /** The optimistic user bubble still showing "Sending". */
  sendingMessageId: string | null;
  /** Bumped by each send, regenerate, Stop and new view; an older attempt's result is stale. */
  attempt: number;
  /** The send in flight until the server answers it. */
  pending: PendingSend | null;
  /** Sends the server never saved, per chat, kept until retried or stopped. */
  rejected: ReadonlyMap<string, readonly RejectedSend[]>;
  /** The reply streamed so far, and the streaming bubble's draft. */
  buffer: string;
  draft: StreamingDraft | null;
  /** The bubble Stop or an error committed; a late `done` reconciles it in place. */
  stoppedStreamedId: string | null;
  /** Regenerate shows; `regenerateBackup` is the answer it replaces until a new one lands. */
  regenerating: boolean;
  regenerateBackup: Message | null;
  /** The optimistic user message, for the first-token latency sample. */
  ttftTurnId: string | null;
  /** This view announced its first reply. */
  firstReply: boolean;
  authFallback: AuthFallback | null;
  /** The attempt whose typing dots went up at the tap, before its send was dispatched. */
  earlyDots: number | null;
};

/** What to do when a turn the server took is not found after its connection dropped. */
export type DroppedTurnFollow =
  | { via: "socket"; pending: PendingSend | null }
  /** The server answered `duplicate`: an earlier send of this message took the turn. */
  | { via: "duplicate"; pending: PendingSend | null }
  | { via: "sse"; pending: PendingSend | null; error: unknown; ttftTurnId: string | null };

export type ChatTurnEvent =
  | { type: "view_changed"; chatId: string | null; session: number }
  | { type: "send"; content: string; options?: SendMessageOptions; retrying?: RejectedSend; clientMessageId: string }
  /** Typing dots under a bubble the composer just painted, before its send goes out. */
  | { type: "dots_begin" }
  /** Those dots come down: the send went to image generation, or nowhere. */
  | { type: "dots_cancelled"; attempt: number }
  /** A send waits for the reply still saving; its bubble says "Sending". */
  | { type: "send_waiting"; messageId: string }
  /** A reply past `stream_end` whose `done` never came (its connection gone quiet). */
  | { type: "unconfirmed_reply" }
  | { type: "send_dispatched"; retrying?: RejectedSend }
  | { type: "fallback_armed"; fallback: AuthFallback }
  | { type: "regenerate_ui"; messages: Message[] }
  | { type: "regenerate_backup"; backup: Message }
  | { type: "regenerate"; messages: Message[] }
  | { type: "regenerate_cancelled" }
  | { type: "stop" }
  | { type: "frame"; payload: ChatSsePayload; ttftTurnId?: string | null }
  | { type: "socket_fallback"; transport: ChatWsTransport; signal: ChatWsFallbackSignal }
  | { type: "send_failed"; error: unknown; ttftTurnId: string | null }
  | { type: "regenerate_failed"; error?: unknown }
  | { type: "dropped_turn"; follow: DroppedTurnFollow; result: DroppedTurnResult }
  | { type: "rejected_draft_restored" }
  /** Any other change to the thread on screen (threadEdit.ts names every writer). */
  | {
      type: "thread_edit";
      source: ThreadEditSource;
      update: ThreadUpdate;
      /** The chat the edit belongs to: held while the screen shows another chat. */
      chatId?: string;
    };

export type ChatTurnCommand =
  | { type: "messages"; update: (previous: Message[]) => Message[] }
  /** Pops the last answer for Regenerate; a backup found in the newest list comes back as `regenerate_backup`. */
  | { type: "pop_for_regenerate" }
  | { type: "cue"; cue: "reset" | "activity" | "complete" | "error" | "stopped" }
  | { type: "outcome"; outcome: "begin" }
  | { type: "outcome"; outcome: "token" }
  | { type: "outcome"; outcome: "send_ready" }
  | { type: "outcome"; outcome: "activity"; phase: string }
  | { type: "outcome"; outcome: "report"; completion: ChatTurnOutcomeProperties["completion"]; code?: string }
  | { type: "first_token"; turnId: string | null | undefined; frame: string }
  | { type: "clear_ttft"; turnId?: string | null }
  | { type: "announce"; key: string }
  | { type: "consent_required" }
  /** The server's words when it sent some, else `key` translated. */
  | { type: "report_error"; message?: string; key: string; code?: string }
  | { type: "first_reply" }
  | { type: "todos_changed" }
  | { type: "usage"; usage: TurnUsage }
  | { type: "drop_socket" }
  | { type: "abort_sse" }
  | { type: "cancel_socket"; streamedChars?: number }
  | { type: "retry_fallback"; fallback: AuthFallback }
  | { type: "follow_dropped_turn"; follow: DroppedTurnFollow; polls?: number; pollMs?: (poll: number) => number }
  /**
   * Stop came before this send (null: a regeneration) went out: it stops waiting for the
   * opened chat's page (`openedPage.ts`) and is marked taken back, so its sender returns the draft.
   */
  | { type: "withdraw_unsent"; chatId: string | null; pending: PendingSend | null };

export type ChatTurnStep = { state: ChatTurnState; commands: ChatTurnCommand[] };

/** The handlers update a copy of the state and append the commands it implies, in order. */
export type Out = ChatTurnCommand[];

export function initialChatTurnState(chatId: string | null, session: number): ChatTurnState {
  return {
    chatId, session, heldEdits: new Map(), phase: "idle", sendingMessageId: null, attempt: 0, pending: null,
    rejected: new Map(),
    buffer: "", draft: null, stoppedStreamedId: null, regenerating: false, regenerateBackup: null,
    ttftTurnId: null, firstReply: false, authFallback: null, earlyDots: null,
  };
}

/** At rest, or the regenerate `regenerate_ui` already opened (the model picker's). */
export function canRegenerate(state: ChatTurnState): boolean {
  return state.phase === "idle" || state.regenerating;
}

/** The first send the server never saved in this chat, offered as Retry. */
export function headRejectedSend(state: ChatTurnState): RejectedSend | null {
  return state.chatId ? state.rejected.get(state.chatId)?.[0] ?? null : null;
}

export function messages(out: Out, update: (previous: Message[]) => Message[]): void {
  out.push({ type: "messages", update });
}

export function cue(out: Out, value: Extract<ChatTurnCommand, { type: "cue" }>["cue"]): void {
  out.push({ type: "cue", cue: value });
}

export function reportError(out: Out, error: { message?: string; key: string; code?: string }): void {
  out.push({ type: "report_error", ...error });
}

export function setRejected(s: ChatTurnState, chatId: string, queue: readonly RejectedSend[]): void {
  const next = new Map(s.rejected);
  if (queue.length > 0) next.set(chatId, queue);
  else next.delete(chatId);
  s.rejected = next;
}

/** The server never saved this send: drop its bubble and keep it as Retry. */
export function queueUnsaved(s: ChatTurnState, out: Out, pending: PendingSend, reason: RejectedSend["reason"]): void {
  if (!s.chatId) return;
  const rejected: RejectedSend = { ...pending, reason };
  const queue = s.rejected.get(s.chatId) ?? [];
  setRejected(s, s.chatId, rejected.retryingRejected ? [rejected, ...queue] : [...queue, rejected]);
  const id = rejected.messageId;
  if (id) messages(out, (previous) => previous.filter((message) => message.id !== id || message.role !== "user"));
}

/** A retry of a rejected send that never left the phone takes its bubble with it. */
export function dropUndispatchedRetry(s: ChatTurnState, out: Out): void {
  const retry = s.pending;
  if (retry?.retryingRejected && !retry.dispatched) {
    const id = retry.messageId;
    messages(out, (previous) => previous.filter((message) => message.id !== id));
  }
}

export function clearStreamingBubble(s: ChatTurnState, out: Out): void {
  s.draft = null;
  if (s.phase === "finalizing") s.phase = "streaming";
  messages(out, (previous) => previous.filter((message) => message.id !== "streaming"));
}

export function restoreRegenerateBackup(s: ChatTurnState, out: Out): void {
  s.regenerating = false;
  const backup = s.regenerateBackup;
  s.regenerateBackup = null;
  // Into the replacement's place, so a message sent meanwhile stays below it.
  messages(out, (previous) => restoreAssistantMessage(previous, backup));
  clearStreamingBubble(s, out);
  s.phase = "idle";
}

/** Keep what the user already saw as a stopped answer; false when nothing streamed. */
export function preservePartialStream(s: ChatTurnState, out: Out, now: number): boolean {
  const draft = s.draft;
  const partial = (draft?.content ?? s.buffer).trim();
  s.buffer = "";
  if (!partial) return false;
  const keptId = `streamed-${now}`;
  s.draft = null;
  messages(out, (previous) => replaceStreamingMessageWithPartial(previous, partial, draft, keptId));
  return true;
}

/**
 * The streaming bubble with what streamed so far, kept as a stopped answer under `id`.
 * `notSaved`: the reply came whole (`stream_end`) and its save failed, said on the reply.
 */
export function keepStreamedBubble(
  previous: Message[],
  id: string,
  content: string | undefined,
  draft: StreamingDraft | null,
  notSaved = false,
): Message[] {
  return previous.map((m) => (m.id === "streaming"
    ? {
        ...m,
        id,
        content: content ?? m.content,
        search_sources: draft?.search_sources ?? m.search_sources,
        ...(notSaved ? { replyNotSaved: true } : { generationStopped: true }),
      }
    : m));
}

/** Opens the streaming bubble: typing dots at once, without waiting for the server. */
export function openStream(s: ChatTurnState, out: Out, status?: string): void {
  s.phase = "streaming";
  s.sendingMessageId = null;
  s.buffer = "";
  s.draft = { content: "", status };
  messages(out, (previous) => withStreamingPlaceholder(previous));
}
