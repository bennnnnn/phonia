import type { ProductEventName } from "@/lib/api/analytics";
import { trackProductEvent } from "@/lib/productAnalytics";
import { CHAT_EVENT_SAMPLE_RATE } from "@/features/chat/model/chatEventSample";

export type ChatTtftBucket =
  | "lt500"
  | "500_999"
  | "1000_1999"
  | "2000_3999"
  | "4000_5999"
  | "6000_plus";

export type ChatPaintBucket = "lt50" | "50_99" | "100_249" | "250_499" | "500_999" | "1000_plus";

/** The reply's last token -> Send ready (`stream_end`); "none" when the turn ended another way. */
export type ChatSendReadyBucket =
  | "none"
  | "lt100"
  | "100_249"
  | "250_499"
  | "500_999"
  | "1000_1999"
  | "2000_plus";

export type ChatTransport = "ws" | "sse";

type Sample = {
  latencyBucket: ChatTtftBucket;
  transport: ChatTransport;
  hasAttachment: boolean;
  /** Tap -> bubble on screen, when the frame that drew it ran before the first token. */
  paintBucket?: ChatPaintBucket;
};

/** How a chat turn ended (`chat_turn_outcome`): enumerated values only, never text. */
export type ChatTurnOutcomeProperties = {
  completion: "complete" | "stopped" | "interrupted" | "error";
  error_code: string;
  tool: string;
  send_ready_bucket: ChatSendReadyBucket;
};

/** Loaded lazily by the chat model, after the moment it measures; sent with the next batch. */
function recordChatEvent(name: ProductEventName, properties: Record<string, string>): void {
  trackProductEvent(name, { ...properties, sample_rate: String(CHAT_EVENT_SAMPLE_RATE) });
}

/** Fire-and-forget caller; all work here happens after first-token delivery. */
export async function reportChatTtft(sample: Sample): Promise<void> {
  recordChatEvent("chat_ttft", {
    latency_bucket: sample.latencyBucket,
    transport: sample.transport,
    has_attachment: sample.hasAttachment ? "yes" : "no",
    ...(sample.paintBucket ? { paint_bucket: sample.paintBucket } : {}),
  });
}

/** Fire-and-forget caller; sent once the turn has ended. */
export async function reportChatTurnOutcome(properties: ChatTurnOutcomeProperties): Promise<void> {
  recordChatEvent("chat_turn_outcome", properties);
}
