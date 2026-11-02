import { CONSENT_REQUIRED_CODE } from "@/lib/api/consentRefusal";
import { isServiceUnavailable } from "@/lib/api/errorBody";

export type LiveTalkPhase = "idle" | "recording" | "thinking" | "speaking";

export type LiveTalkGate =
  | "ok"
  /** The plan does not include live talk (`not_in_plan`): the paywall. */
  | "upgrade"
  /** The account has not agreed to outside AI services (`consent_required`): the API
   *  client already sent it to the consent step (`lib/api/client.ts`), so nothing else. */
  | "consent"
  /** This month's minutes are used: the status says so, or the server's `live_talk_minutes_used`. */
  | "limit"
  /** Too many requests in a row (the speech limit, a save's, the API's own): wait a moment. */
  | "rate_limited"
  /** Voice is paused while provider spend is capped (`voice_spend_cap`). */
  | "paused"
  /** This call saved every turn it may (`live_talk_saves_used`): start a new one. */
  | "saves_used"
  /** A save named no live session (`live_talk_session_ended`): the call is over. */
  | "session_ended"
  /** This build has no WebRTC: only an update brings live talk. */
  | "unavailable"
  /** The server has live talk switched off (`enabled: false`, `not_available`). */
  | "off"
  /** The realtime provider failed, or the connection to it never came up: try again. */
  | "connect_failed"
  | "offline"
  | "unconfigured"
  /** Recall is down for now (its database or Redis, a deploy): try again in a moment. */
  | "outage"
  | "mic_permission"
  /** The microphone gave no audio (in use, or missing): the device, not the app's age. */
  | "mic_unavailable";

/** Live talk for this user: `remaining` / `limit` are whole minutes this month. */
export type LiveTalkStatus = {
  enabled: boolean;
  entitled: boolean;
  remaining: number;
  limit: number;
  remaining_seconds?: number;
  limit_seconds?: number;
  /** The server refuses a session when fewer seconds than this are left. */
  min_session_seconds?: number;
  /** When the monthly minutes renew (ISO, UTC). */
  resets_at?: string | null;
};

/** Fallback session cap when the server did not say (it reserves at mint). */
export const LIVE_TALK_MAX_SESSION_MS = 15 * 60 * 1000;

/** Hang up when the session's reserved minutes run out. */
export function liveTalkSessionLimitMs(maxDurationSeconds: number | null | undefined): number {
  if (typeof maxDurationSeconds === "number" && maxDurationSeconds > 0) {
    return Math.min(maxDurationSeconds * 1000, LIVE_TALK_MAX_SESSION_MS);
  }
  return LIVE_TALK_MAX_SESSION_MS;
}
/** Local tail after `output_audio_buffer.stopped` before the mic reopens. */
export const LIVE_TALK_PLAYBACK_TAIL_MS = 500;
/** Ignore connect/track-start noise before the first real user utterance. */
export const LIVE_TALK_CONNECT_WARMUP_MS = 1_500;
/** If session.created never arrives, start accepting user turns after this. */
export const LIVE_TALK_SESSION_READY_FALLBACK_MS = 2_500;

type LiveTalkOrbAction = "begin" | "finishListen" | "cancelThink" | "none";

type LiveTalkOrbMode = "listen" | "speak" | "think" | "idle";

/** Visual language for the orb — no on-screen Listening/Speaking copy. */
export function liveTalkOrbMode(phase: LiveTalkPhase): LiveTalkOrbMode {
  if (phase === "recording") return "listen";
  if (phase === "speaking") return "speak";
  if (phase === "thinking") return "think";
  return "idle";
}

/** Orb tap: start/stop a listen or cancel a wait. Mute is the mic control, not the orb. */
export function liveTalkOrbAction(phase: LiveTalkPhase): LiveTalkOrbAction {
  if (phase === "thinking") return "cancelThink";
  if (phase === "speaking") return "none";
  if (phase === "recording") return "finishListen";
  return "begin";
}

export function liveTalkMuteA11yKey(
  muted: boolean,
): "chat.live_talk_mute_a11y" | "chat.live_talk_unmute_a11y" {
  return muted ? "chat.live_talk_unmute_a11y" : "chat.live_talk_mute_a11y";
}

/** Mic + close sit beside an empty composer; typing takes the full row. */
export function liveTalkShowsSideChrome(draft: string): boolean {
  return draft.trim().length === 0;
}

type LiveTalkPhaseA11yKey =
  | "chat.live_talk_listening_a11y"
  | "chat.live_talk_thinking_a11y"
  | "chat.live_talk_speaking_a11y";

/**
 * What a screen reader hears for each phase. The orb shows no Listening or
 * Speaking copy (FEATURES §3); a blind user still needs to know which it is.
 */
export function liveTalkPhaseA11yKey(phase: LiveTalkPhase): LiveTalkPhaseA11yKey | null {
  if (phase === "recording") return "chat.live_talk_listening_a11y";
  if (phase === "thinking") return "chat.live_talk_thinking_a11y";
  if (phase === "speaking") return "chat.live_talk_speaking_a11y";
  return null;
}

export function liveTalkOrbA11yKey(phase: LiveTalkPhase): LiveTalkPhaseA11yKey | "chat.live_talk_a11y" {
  return liveTalkPhaseA11yKey(phase) ?? "chat.live_talk_a11y";
}

/** The orb's action while it waits for a reply; no other phase has one to read out. */
export function liveTalkOrbA11yHintKey(phase: LiveTalkPhase): "chat.live_talk_cancel_a11y" | null {
  return phase === "thinking" ? "chat.live_talk_cancel_a11y" : null;
}

export function liveTalkGate(status: LiveTalkStatus | null, isOffline: boolean): LiveTalkGate {
  if (isOffline) return "offline";
  if (!status || !status.enabled) return "off";
  if (!status.entitled || status.limit <= 0) return "upgrade";
  const secondsLeft = status.remaining_seconds ?? status.remaining * 60;
  if (secondsLeft <= 0 || secondsLeft < (status.min_session_seconds ?? 1)) return "limit";
  return "ok";
}

/** Keep an in-flight WebRTC session only if this open() is still the current one. */
export function liveTalkShouldAttachSession(startedGen: number, currentGen: number): boolean {
  return startedGen === currentGen;
}

/** Close Live Talk when the user opens a different chat from the drawer. */
export function liveTalkShouldCloseOnChatChange(
  boundChatId: string | null,
  nextChatId: string | null,
): boolean {
  return Boolean(boundChatId) && nextChatId !== boundChatId;
}

/**
 * Background: flush and hang up so Realtime billing cannot continue. iOS reports
 * "inactive" for Control Center, a notification pulled down and its own microphone
 * prompt, which ended a first call before the user could answer it; leaving the
 * app still passes through "background".
 */
export function liveTalkShouldCloseOnAppState(state: string): boolean {
  return state === "background";
}

/** react-native-webrtc may deliver data-channel payloads as a string or bytes. */
export function liveTalkDataChannelText(data: unknown): string | null {
  if (typeof data === "string") return data;
  if (data instanceof ArrayBuffer) {
    return new TextDecoder().decode(data);
  }
  if (ArrayBuffer.isView(data)) {
    return new TextDecoder().decode(data);
  }
  return null;
}

/** react-native-webrtc rejects a denied microphone with a plain `{ name, message }`. */
const MIC_DENIED_NAMES = new Set(["NotAllowedError", "SecurityError", "PermissionDeniedError"]);

/** The device refused the microphone; an API error (it has a status) never is. */
function isMicPermissionDenied(error: object): boolean {
  const { name, message } = error as { name?: unknown; message?: unknown };
  if (typeof name === "string" && MIC_DENIED_NAMES.has(name)) return true;
  return typeof message === "string" && /permission denied|not allowed/i.test(message);
}

/**
 * What each 429 live talk can get says, by its code. Every 429 said this month's minutes
 * were used: a rate limit, the spend cap, a call's last save. Only the mint's
 * `live_talk_minutes_used` means that.
 */
const LIVE_TALK_429S: ReadonlyMap<unknown, LiveTalkGate> = new Map<unknown, LiveTalkGate>([
  ["live_talk_minutes_used", "limit"],
  // The mint's per-minute limit, and a save's.
  ["speech_rate_limited", "rate_limited"],
  ["rate_limited", "rate_limited"],
  ["voice_spend_cap", "paused"],
  ["live_talk_saves_used", "saves_used"],
]);

/**
 * The realtime provider failed: the server's 502 when it minted no key, and the phone's own
 * SDP exchange with the provider (`realtimeSdp.ts`), whose status is the provider's, not Recall's.
 */
export const LIVE_TALK_UPSTREAM_FAILED = "upstream_failed";

export function liveTalkErrorGate(error: unknown): LiveTalkGate {
  // The one case an update fixes: this build has no WebRTC.
  if (error instanceof Error && error.message === "webrtc_unavailable") {
    return "unavailable";
  }
  // It said "update the app" too; an update changes nothing about the microphone.
  if (error instanceof Error && error.message === "microphone_unavailable") {
    return "mic_unavailable";
  }
  if (!error || typeof error !== "object") return "connect_failed";
  const { status, code } = error as { status?: unknown; code?: unknown };
  if (status === undefined && isMicPermissionDenied(error)) {
    return "mic_permission";
  }
  if (code === LIVE_TALK_UPSTREAM_FAILED) return "connect_failed";
  if (code === "not_available") return "off";
  // Every 403 opened the paywall, `consent_required` too, on top of the consent step.
  if (code === "not_in_plan") return "upgrade";
  if (code === CONSENT_REQUIRED_CODE) return "consent";
  if (code === "live_talk_session_ended") return "session_ended";
  // The API's own request limit names no code: too many requests, never the month's minutes.
  if (status === 429) return LIVE_TALK_429S.get(code) ?? "rate_limited";
  // Only the server's `not_configured` says live talk is not set up. Every 503 said so,
  // a Redis or database outage too; any other 503, and a gateway's 502 or 504, is one.
  if (status === 503) return code === "not_configured" ? "unconfigured" : "outage";
  if (isServiceUnavailable(error)) return "outage";
  // No answer from Recall, a connection that never came up, an answer it could not use.
  return "connect_failed";
}

type SaidGate = Exclude<LiveTalkGate, "ok" | "upgrade" | "consent" | "mic_permission">;

/** Every gate said as an error has its own line: an unknown one said "update the app". */
const GATE_MESSAGE_KEYS: Readonly<Record<SaidGate, string>> = {
  limit: "chat.live_talk_limit_body",
  rate_limited: "chat.live_talk_rate_limited",
  paused: "chat.live_talk_paused",
  saves_used: "chat.live_talk_saves_used",
  session_ended: "chat.live_talk_session_ended",
  unavailable: "chat.live_talk_unavailable_body",
  off: "chat.live_talk_off",
  connect_failed: "chat.live_talk_connect_failed",
  offline: "chat.offline_body",
  outage: "common.service_unavailable",
  unconfigured: "chat.live_talk_not_configured",
  mic_unavailable: "chat.live_talk_mic_unavailable",
};

/** The line a gate says as a recoverable error; upgrade, consent and the microphone open their own. */
export function liveTalkGateMessageKey(gate: LiveTalkGate): string {
  return (GATE_MESSAGE_KEYS as Partial<Record<LiveTalkGate, string>>)[gate] ?? "chat.live_talk_failed";
}

/**
 * An error during a call, in the phone's words: it showed the provider's English ("Realtime
 * voice data channel failed"). A lost connection could not connect; any other error failed
 * this reply, and the call goes on.
 */
export function liveTalkCallErrorKey(fatal: boolean | undefined): string {
  return fatal ? liveTalkGateMessageKey("connect_failed") : "chat.error_generic";
}

/**
 * A save refused with a 429, or because the plan, the session or the server no longer
 * allows the call, ends it in that refusal's own words. Left open, the voice provider kept
 * running (and charging) until the reserved minutes ran out, while no turn saved.
 */
const SAVE_ENDS_CALL: ReadonlySet<LiveTalkGate> = new Set<LiveTalkGate>([
  "limit", "rate_limited", "paused", "saves_used", "upgrade", "consent", "session_ended", "off",
]);

export function liveTalkSaveEndsCall(gate: LiveTalkGate): boolean {
  return SAVE_ENDS_CALL.has(gate);
}

/** Any other refused save, in the phone's words: it showed the server's English. */
export function liveTalkSaveFailedKey(gate: LiveTalkGate): string {
  return gate === "outage" ? liveTalkGateMessageKey(gate) : "chat.live_talk_save_failed";
}

/** Capture stays off while the assistant is playing so speaker echo cannot VAD. */
export function liveTalkLocalMicEnabled(userMuted: boolean, assistantSpeaking: boolean, bargeIn = false): boolean {
  return !userMuted && (bargeIn || !assistantSpeaking);
}

/** Manual `response.create` only after an accepted user utterance. */
export function liveTalkShouldCreateResponse(input: {
  sessionReadyForTurns: boolean;
  assistantSpeaking: boolean;
  userMuted: boolean;
  acceptedUserUtterance: boolean;
}): boolean {
  return (
    input.sessionReadyForTurns &&
    input.acceptedUserUtterance &&
    !input.assistantSpeaking &&
    !input.userMuted
  );
}

function liveTalkNormalizeTranscript(text: string): string {
  return text
    .toLowerCase()
    .replace(/[.!?,;:'"()[\]{}]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** The text of a Realtime transcript event: a whole `transcript`, else a `delta`. */
export function liveTalkTranscriptText(event: Record<string, unknown>): string {
  const transcript = event.transcript;
  if (typeof transcript === "string") return transcript.trim();
  const delta = event.delta;
  if (typeof delta === "string") return delta;
  return "";
}

const SILENCE_HALLUCINATIONS = new Set([
  "thank you for watching",
  "thanks for watching",
  "please subscribe",
  "subscribe",
]);

/** Whisper-style captions the transcriber invents from silence. */
export function isLiveTalkSilenceHallucination(text: string): boolean {
  return SILENCE_HALLUCINATIONS.has(liveTalkNormalizeTranscript(text));
}

/** Speaker bleed often transcribes as a short slice of the last assistant line. */
export function isLikelyAssistantEcho(userText: string, lastAssistantText: string): boolean {
  const user = liveTalkNormalizeTranscript(userText);
  const assistant = liveTalkNormalizeTranscript(lastAssistantText);
  if (!user) return true;
  if (!assistant) return false;
  return assistant.includes(user);
}
