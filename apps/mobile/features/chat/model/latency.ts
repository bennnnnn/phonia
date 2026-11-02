// Types only: the reporter module itself still loads lazily after the first token.
import type { ChatPaintBucket, ChatTransport, ChatTtftBucket } from "@/features/chat/model/latencyReporter";
import { sampleChatEvent } from "@/features/chat/model/chatEventSample";

type PendingChatTtft = {
  turnId: string;
  startedAtMs: number;
  transport: ChatTransport;
  hasAttachment: boolean;
  /** Tap -> the frame that drew the user's bubble. */
  paintMs?: number;
};

let pending: PendingChatTtft | null = null;

/** Bucket user-bubble -> first-token latency without storing arbitrary timing values. */
export function chatTtftBucket(elapsedMs: number): ChatTtftBucket {
  const ms = Number.isFinite(elapsedMs) ? Math.max(0, elapsedMs) : 0;
  if (ms < 500) return "lt500";
  if (ms < 1_000) return "500_999";
  if (ms < 2_000) return "1000_1999";
  if (ms < 4_000) return "2000_3999";
  if (ms < 6_000) return "4000_5999";
  return "6000_plus";
}

/** Bucket tap -> bubble on screen: a frame is about 16 ms, so past a few is a wait before the paint. */
export function chatPaintBucket(elapsedMs: number): ChatPaintBucket {
  const ms = Number.isFinite(elapsedMs) ? Math.max(0, elapsedMs) : 0;
  if (ms < 50) return "lt50";
  if (ms < 100) return "50_99";
  if (ms < 250) return "100_249";
  if (ms < 500) return "250_499";
  if (ms < 1_000) return "500_999";
  return "1000_plus";
}

/**
 * Start at the tap on Send (`tappedAtMs`), before the bubble is painted, so
 * every wait the user sees is inside the sample: the paint, a picture check,
 * a location, file upload or new chat, the transport, backend prep and the model.
 *
 * `turnId` is the optimistic user-message id. Leftover SSE from a previous
 * chat must not stamp or consume a later send's sample.
 */
export function markChatTtftStart(
  turnId: string,
  tappedAtMs: number,
  hasAttachment: boolean,
): void {
  // A sampled turn only; any earlier unfinished sample is dropped either way.
  pending = null;
  if (!turnId || !sampleChatEvent()) return;
  pending = {
    turnId,
    startedAtMs: Number.isFinite(tappedAtMs) ? tappedAtMs : Date.now(),
    transport: "ws",
    hasAttachment,
  };
}

/** The frame that drew `turnId`'s bubble has run (first call only). */
export function markChatBubblePainted(turnId: string): void {
  if (!pending || pending.turnId !== turnId || pending.paintMs !== undefined) return;
  pending.paintMs = Math.max(0, Date.now() - pending.startedAtMs);
}

/** SSE is a fallback; the optimistic default is WebSocket until this is called. */
export function markChatTtftTransport(turnId: string | null | undefined, transport: ChatTransport): void {
  if (!pending || !turnId || pending.turnId !== turnId) return;
  pending.transport = transport;
}

/**
 * Record at most once, on the first actual answer token accepted for this
 * originating stream. Leftover parse of another chat's SSE must not match.
 */
export function markChatFirstToken(
  turnId: string | null | undefined,
  payloadType: string,
): void {
  if (payloadType !== "token" || !pending || !turnId || pending.turnId !== turnId) return;
  const sample = pending;
  pending = null;
  const elapsedMs = Math.max(0, Date.now() - sample.startedAtMs);

  // Reporter is intentionally lazy and fire-and-forget: loading analytics,
  // SecureStore, app metadata, and installation id happens only after the first
  // token is already on its way to the UI, so telemetry cannot worsen TTFT.
  void import("@/features/chat/model/latencyReporter")
    .then(({ reportChatTtft }) =>
      reportChatTtft({
        latencyBucket: chatTtftBucket(elapsedMs),
        transport: sample.transport,
        hasAttachment: sample.hasAttachment,
        ...(sample.paintMs === undefined ? {} : { paintBucket: chatPaintBucket(sample.paintMs) }),
      }),
    )
    .catch(() => {
      // Product telemetry is best-effort and must never affect chat.
    });
}

/** Drop an unfinished sample. Omit `turnId` to discard whatever is pending. */
export function clearPendingChatTtft(turnId?: string | null): void {
  if (turnId != null && pending?.turnId !== turnId) return;
  pending = null;
}
