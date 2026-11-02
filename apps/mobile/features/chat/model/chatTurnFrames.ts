import { CONSENT_REQUIRED_CODE } from "@/lib/api/consentRefusal";
import { phaseStartedAt } from "@/lib/streamStatusLabel";
import { withStreamingPlaceholder } from "@/features/chat/model/partialStream";
import type { RejectedSend } from "@/features/chat/model/sendLogic";
import type { ChatSsePayload } from "@/features/chat/model/sse";
import {
  applyRelatedPrompts,
  applyStreamEndModel,
  buildDoneMergeInput,
  mergeDoneIntoMessages,
  relatedPromptsFromEvent,
  shouldIgnoreStoppedStreamEvent,
} from "@/features/chat/model/socketReduce";
import { refusalCode } from "@/features/chat/model/errorMessage";
import { completionFromDone } from "@/features/chat/model/turnOutcome";
import { DUPLICATE_TURN_POLLS, duplicateTurnPollMs } from "@/features/chat/model/turnReconcile";
import {
  clearStreamingBubble,
  cue,
  headRejectedSend,
  keepStreamedBubble,
  messages,
  queueUnsaved,
  reportError,
  restoreRegenerateBackup,
  type ChatTurnState,
  type Out,
} from "@/features/chat/model/chatTurnCore";

/** Errors whose own action (upgrade, change model) stands in for Retry. */
const OWN_RECOVERY_CODES = new Set(["quota_exceeded", "model_unavailable"]);

/** Why a failed send can be offered again: the server says its message is not in the chat. */
function unsavedReason(payload: ChatSsePayload): RejectedSend["reason"] | null {
  if (payload.code === "attachment_rejected") return "attachment_rejected";
  if (payload.code === "busy") return "send_rejected";
  const ownRecovery = OWN_RECOVERY_CODES.has(payload.code ?? "");
  return payload.user_message_saved === false && !ownRecovery ? "send_rejected" : null;
}

function onDone(s: ChatTurnState, out: Out, payload: ChatSsePayload, now: number): void {
  s.pending = null;
  s.regenerating = false;
  s.authFallback = null;
  s.regenerateBackup = null;
  s.ttftTurnId = null;
  s.sendingMessageId = null;
  const stoppedId = s.stoppedStreamedId;
  s.stoppedStreamedId = null;
  if (!stoppedId) {
    cue(out, "complete");
    out.push({ type: "announce", key: "chat.reply_ready" });
    // A stopped turn was reported when the user tapped Stop.
    out.push({ type: "outcome", outcome: "report", completion: completionFromDone(payload.completion) });
  }
  s.phase = "idle";
  s.buffer = "";
  const draft = s.draft;
  s.draft = null;
  messages(out, (previous) => mergeDoneIntoMessages(previous, buildDoneMergeInput(payload, draft, now, stoppedId)));
  if (!s.firstReply) {
    s.firstReply = true;
    out.push({ type: "first_reply" });
  }
  // Rows the turn wrote: one reload (code-health audit NET-14).
  if (payload.todos_changed) out.push({ type: "todos_changed" });
  if (payload.usage) out.push({ type: "usage", usage: payload.usage });
}

function onError(s: ChatTurnState, out: Out, payload: ChatSsePayload, ttftTurnId: string | null | undefined, now: number): void {
  // After `stream_end` only the save was left: the reply came whole and failed to save.
  const saveFailed = s.phase === "finalizing";
  cue(out, "error");
  const frameCode = typeof payload.code === "string" ? payload.code : undefined;
  const code = frameCode === undefined ? undefined : refusalCode(frameCode, payload.feature);
  // The event counts the server's own code: a picture's `daily_limit`, not the phone's wording.
  out.push({ type: "outcome", outcome: "report", completion: "error", code: frameCode });
  // No consent to outside AI: the consent screen opens, the unsaved message waits as Retry.
  if (payload.code === CONSENT_REQUIRED_CODE) out.push({ type: "consent_required" });
  // Only an unsaved message is offered as Retry (resend); a saved one keeps Regenerate.
  const pending = s.pending;
  s.pending = null;
  out.push({ type: "clear_ttft", turnId: ttftTurnId ?? pending?.messageId });
  s.ttftTurnId = null;
  const reason = unsavedReason(payload);
  if (pending && reason) queueUnsaved(s, out, pending, reason);
  s.regenerating = false;
  s.authFallback = null;
  s.stoppedStreamedId = null;
  s.sendingMessageId = null;
  s.phase = "idle";
  const draft = s.draft;
  const partial = (draft?.content ?? s.buffer).trim();
  s.buffer = "";
  if (s.regenerateBackup) {
    restoreRegenerateBackup(s, out);
  } else if (partial) {
    // Keep what the user already saw (as Stop and a dropped connection do), said on the
    // reply itself when it came whole, where it outlasts the banner the next turn clears.
    const keptId = `streamed-${now}`;
    s.draft = null;
    messages(out, (previous) => (previous.some((m) => m.id === "streaming")
      ? keepStreamedBubble(previous, keptId, partial, draft, saveFailed)
      : previous));
    s.stoppedStreamedId = keptId;
  } else {
    clearStreamingBubble(s, out);
  }
  const queuedReason = pending && reason ? headRejectedSend(s)?.reason : undefined;
  reportError(out, { message: payload.message, key: "chat.error_generic", code: queuedReason ?? code });
}

/**
 * `duplicate`: an earlier send of this message reached the server, which runs that
 * turn. Follow it until its reply lands (minutes, for a long turn); no second turn
 * is asked for. Not found in the chat, it is offered again under a new name.
 */
function onDuplicate(s: ChatTurnState, out: Out): void {
  if (s.phase === "idle") return;
  const pending = s.pending;
  s.pending = null;
  s.authFallback = null;
  out.push({
    type: "follow_dropped_turn",
    follow: { via: "duplicate", pending },
    polls: DUPLICATE_TURN_POLLS,
    pollMs: duplicateTurnPollMs,
  });
}

/** Applies one socket or SSE frame; late deltas after Stop and unknown types change nothing. */
export function applyFrame(
  s: ChatTurnState,
  out: Out,
  payload: ChatSsePayload,
  ttftTurnId: string | null | undefined,
  now: number,
): void {
  if (shouldIgnoreStoppedStreamEvent(payload.type, s.phase !== "idle")) return;
  switch (payload.type) {
    case "start":
      cue(out, "activity");
      out.push({ type: "outcome", outcome: "begin" });
      // The server took the turn: from here a drop is reconciled, never sent twice.
      if (s.pending) s.pending = { ...s.pending, accepted: true };
      s.authFallback = null;
      s.sendingMessageId = null;
      s.phase = "streaming";
      s.buffer = "";
      // Keep the instant local status instead of blanking it until the first status frame.
      s.draft = {
        content: "",
        status: s.draft?.status,
        statusDetail: s.draft?.statusDetail,
        statusStartedAt: s.draft?.statusStartedAt,
      };
      messages(out, (previous) => withStreamingPlaceholder(previous));
      return;
    case "status":
      cue(out, "activity");
      if (typeof payload.phase !== "string") return;
      out.push({ type: "outcome", outcome: "activity", phase: payload.phase });
      s.draft = {
        content: s.buffer,
        search_sources: s.draft?.search_sources,
        status: payload.phase,
        statusDetail: typeof payload.detail === "string" && payload.detail ? payload.detail : undefined,
        statusStartedAt: phaseStartedAt(s.draft, payload.phase, payload.elapsed_ms, now),
      };
      return;
    case "token":
      cue(out, "activity");
      s.pending = null;
      out.push({ type: "first_token", turnId: ttftTurnId, frame: payload.type });
      out.push({ type: "outcome", outcome: "token" });
      s.buffer += payload.content ?? "";
      s.draft = { content: s.buffer, search_sources: s.draft?.search_sources, status: undefined, statusDetail: undefined };
      return;
    case "stream_end": {
      s.pending = null;
      out.push({ type: "outcome", outcome: "send_ready" });
      s.phase = "finalizing";
      // The reply is whole: a label from its last step must not outlive it.
      if (s.draft?.status !== undefined) s.draft = { content: s.draft.content, search_sources: s.draft.search_sources };
      const model = payload.resolved_model;
      if (typeof model === "string" && model) messages(out, (previous) => applyStreamEndModel(previous, model));
      return;
    }
    case "done":
      onDone(s, out, payload, now);
      return;
    case "related_prompts": {
      if (typeof payload.message_id !== "string") return;
      const messageId = payload.message_id;
      const prompts = relatedPromptsFromEvent(payload);
      if (prompts) messages(out, (previous) => applyRelatedPrompts(previous, messageId, prompts));
      return;
    }
    case "error":
      onError(s, out, payload, ttftTurnId, now);
      return;
    case "duplicate":
      onDuplicate(s, out);
      return;
    // `reasoning` is not the answer; the `thinking` status says the model is working.
  }
}
