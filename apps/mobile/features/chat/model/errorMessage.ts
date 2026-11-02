import { UNAVAILABLE_CODE } from "@/lib/api/errorBody";

type ChatErrorKind =
  | "quota"
  | "model_unavailable"
  | "busy"
  | "send_rejected"
  | "attachment_rejected"
  | "generic";

/**
 * A turn that failed for no reason the user can act on (the chat or its message gone,
 * anything unexpected), a deploy, a reply that did not save; and today's global spend cap
 * (modules/chat/turn_resources.py), whose English showed in every language.
 */
const TURN_FAILURE_KEYS: Readonly<Record<string, string>> = {
  failed: "chat.error_generic",
  not_found: "chat.error_generic",
  server_restarting: "chat.server_restarting",
  reply_not_saved: "chat.reply_not_saved",
  spend_cap: "chat.spend_cap",
};

export type ResolvedChatError = {
  kind: ChatErrorKind;
  message: string;
};

export function resolveChatError(options: {
  message: string;
  code?: string;
  isPaid: boolean;
  t: (key: string) => string;
}): ResolvedChatError {
  const text = options.message.trim();

  if (options.code === "attachment_rejected") {
    return { kind: "attachment_rejected", message: options.t("chat.attachment_rejected") };
  }
  if (options.code === "send_rejected") {
    return { kind: "send_rejected", message: options.t("chat.send_rejected") };
  }
  if (options.code === "busy") {
    return { kind: "busy", message: options.t("chat.busy") };
  }
  if (options.code === "model_unavailable") {
    return { kind: "model_unavailable", message: options.t("chat.model_unavailable") };
  }
  // Recall's database or Redis is down (the socket's frame, a 503's body): its own words,
  // translated, where the server's English showed.
  if (options.code === UNAVAILABLE_CODE) {
    return { kind: "generic", message: options.t("common.service_unavailable") };
  }
  // Over a request limit: the API's request limiter (core/rest_rate_limit.py), the socket's
  // frame flood. Its English showed, or "Couldn't reach the server" before the 429 named a code.
  if (options.code === "rate_limited") {
    return { kind: "generic", message: options.t("chat.rate_limited") };
  }
  // The turn's own failures (modules/chat/stream_events.py): their English showed.
  const ownKey = TURN_FAILURE_KEYS[options.code ?? ""];
  if (ownKey) return { kind: "generic", message: options.t(ownKey) };
  if (options.code === "quota_exceeded" || options.code === "daily_limit") {
    return {
      kind: "quota",
      message: options.t(options.isPaid ? "chat.quota_exceeded_pro" : "chat.quota_exceeded_free"),
    };
  }
  if (!text || text.startsWith("{") || text.startsWith("[")) {
    return { kind: "generic", message: options.t("chat.error_generic") };
  }
  return { kind: "generic", message: text };
}
