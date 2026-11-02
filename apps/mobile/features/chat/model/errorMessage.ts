import { UNAVAILABLE_CODE } from "@/lib/api/errorBody";

type ChatErrorKind =
  | "quota"
  | "model_unavailable"
  | "busy"
  | "send_rejected"
  | "attachment_rejected"
  /** Said and dismissed: nothing to retry or buy (a refused picture, a paid plan's cap). */
  | "notice"
  | "generic";

/**
 * The code a refusal is worded by. A `daily_limit` or `spend_cap` names its feature: a
 * picture's own cap is not the day's chat allowance running out, nor every message paused.
 */
export function refusalCode(code: string | undefined, feature: unknown): string | undefined {
  if (feature !== "image_generation") return code;
  if (code === "daily_limit") return "image_daily_limit";
  return code === "spend_cap" ? "image_spend_cap" : code;
}

/**
 * Today's global spend cap (modules/chat/turn_resources.py; a picture's in
 * modules/images/generation.py): its English showed in every language.
 */
const SPEND_CAP_KEYS: Readonly<Record<string, string>> = {
  spend_cap: "chat.spend_cap",
  image_spend_cap: "chat.image_spend_cap",
};

/**
 * A turn that failed for no reason the user can act on (the chat or its message gone, an
 * image service failure, anything unexpected), a deploy, a reply that did not save.
 */
const TURN_FAILURE_KEYS: Readonly<Record<string, string>> = {
  failed: "chat.error_generic",
  not_found: "chat.error_generic",
  server_restarting: "chat.server_restarting",
  reply_not_saved: "chat.reply_not_saved",
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
  const ownKey = TURN_FAILURE_KEYS[options.code ?? ""] ?? SPEND_CAP_KEYS[options.code ?? ""];
  if (ownKey) return { kind: "generic", message: options.t(ownKey) };
  if (options.code === "image_daily_limit") {
    // A free plan can buy more pictures; a paid one waits for tomorrow.
    return options.isPaid
      ? { kind: "notice", message: options.t("chat.image_daily_limit_paid") }
      : { kind: "quota", message: options.t("chat.image_daily_limit_free") };
  }
  if (options.code === "content_blocked") {
    return { kind: "notice", message: options.t("chat.image_content_blocked") };
  }
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
