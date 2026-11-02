// Types only: the reporter loads lazily once the turn has ended.
import type { ChatSendReadyBucket, ChatTurnOutcomeProperties } from "@/features/chat/model/latencyReporter";
import { sampleChatEvent } from "@/features/chat/model/chatEventSample";

/**
 * How each chat turn ended, as the metadata-only `chat_turn_outcome` event:
 * complete, stopped, interrupted or failed, the error code, the first tool it
 * showed working, and how soon after its last token Send worked again. Never
 * the prompt, the reply, a query or a message; every value comes from the
 * lists below or the server's own enumerations.
 */

/** Stream status phases that are real tool work (stream_status.StreamStatusPhase). */
const TOOL_PHASES = new Set([
  "searching",
  "calculating",
  "physics",
  "chemistry",
  "reading_files",
  "finding_photo",
  "image_gen",
]);

/**
 * Error frame codes the server sends once a turn has started (stream_events): the same
 * list as the server's `chat_turn_outcome` buckets (modules/analytics/service.py), which
 * the API's test_turn_outcome_codes.py holds to this one and to the codes a frame carries.
 * Seven of them were counted as "other".
 */
const ERROR_CODES = new Set([
  "quota_exceeded",
  "spend_cap",
  "model_unavailable",
  "unavailable",
  "busy",
  "attachment_rejected",
  "unknown_model",
  "rate_limited",
  "consent_required",
  "daily_limit",
  "content_blocked",
  "not_found",
  "failed",
  "reply_not_saved",
  "server_restarting",
]);

type Completion = ChatTurnOutcomeProperties["completion"];

// One turn streams at a time; `start` opens it and its first ending reports it.
let open = false;
let tool = "none";
let sampled = false;
let lastTokenAt: number | null = null;
let sendReadyMs: number | null = null;

/** The server took a turn (`start`). */
export function beginTurnOutcome(): void {
  open = true;
  tool = "none";
  sampled = sampleChatEvent();
  lastTokenAt = null;
  sendReadyMs = null;
}

/** A token arrived: the reply's last one so far. */
export function noteTurnToken(): void {
  if (open) lastTokenAt = Date.now();
}

/** `stream_end`: the text is all in and Send works again (the save follows). */
export function noteTurnSendReady(): void {
  if (!open || lastTokenAt === null || sendReadyMs !== null) return;
  sendReadyMs = Math.max(0, Date.now() - lastTokenAt);
}

export function sendReadyBucket(elapsedMs: number | null): ChatSendReadyBucket {
  if (elapsedMs === null || !Number.isFinite(elapsedMs)) return "none";
  if (elapsedMs < 100) return "lt100";
  if (elapsedMs < 250) return "100_249";
  if (elapsedMs < 500) return "250_499";
  if (elapsedMs < 1_000) return "500_999";
  if (elapsedMs < 2_000) return "1000_1999";
  return "2000_plus";
}

/** A `status` frame: the first tool phase is the turn's tool. */
export function noteTurnActivity(phase: string): void {
  if (open && tool === "none" && TOOL_PHASES.has(phase)) tool = phase;
}

/** The `done` frame's completion, as the event names it. */
export function completionFromDone(completion: string | undefined): Completion {
  if (completion === "user_stop") return "stopped";
  if (completion === "interrupted") return "interrupted";
  return "complete";
}

export function turnOutcomeProperties(
  completion: Completion,
  errorCode?: string,
): ChatTurnOutcomeProperties {
  const code = completion !== "error" ? "none" : errorCode && ERROR_CODES.has(errorCode) ? errorCode : "other";
  return { completion, error_code: code, tool, send_ready_bucket: sendReadyBucket(sendReadyMs) };
}

/** Report the open turn once (a later frame of the same turn reports nothing). */
export function reportTurnOutcome(completion: Completion, errorCode?: string): void {
  if (!open) return;
  open = false;
  const properties = turnOutcomeProperties(completion, errorCode);
  if (!sampled) return;
  void import("@/features/chat/model/latencyReporter")
    .then(({ reportChatTurnOutcome }) => reportChatTurnOutcome(properties))
    .catch(() => {
      // Product telemetry is best-effort and must never affect chat.
    });
}
