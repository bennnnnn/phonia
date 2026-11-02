import { isServiceUnavailable } from "@/lib/api/errorBody";

/**
 * A transcription the server refused, in the words for that refusal: the day's voice
 * input used up, too many recordings in a row, too many requests, voice paused while
 * spend is capped, or Recall down for now. Anything else keeps the dictation's own message.
 */

const VOICE_REFUSALS: Readonly<Record<string, string>> = {
  daily_limit: "chat.voice_daily_limit",
  speech_rate_limited: "chat.voice_rate_limited",
  voice_spend_cap: "chat.voice_paused",
  // Any request over a limit (the API's request limiter, a refused refresh): it said "Could
  // not transcribe your recording", and a retry within the minute failed too. Not the
  // recordings' own limit, so not "Too many recordings".
  rate_limited: "chat.rate_limited",
};

/** The refusal's code, read off any error that carries one. */
function errorCode(error: unknown): string {
  const code = error && typeof error === "object" && "code" in error ? error.code : null;
  return typeof code === "string" ? code : "";
}

/** The i18n key for a refused transcription, or undefined when it was not one of these. */
export function voiceRefusalKey(error: unknown): string | undefined {
  // A Redis outage said "Too many recordings in a row", then "Could not transcribe".
  return VOICE_REFUSALS[errorCode(error)] ?? (isServiceUnavailable(error) ? "common.service_unavailable" : undefined);
}
