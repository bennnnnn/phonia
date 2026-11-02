/**
 * The phone's half of docs/fixtures/error_codes.json (code-health audit DUP-10). The API
 * test writes each refusal from a real request; here each reaches its reader by `code`,
 * so rewording the server's English changes nothing the phone does.
 */
import fixture from "../../../../docs/fixtures/error_codes.json";
import { AttachmentError, presignFailure } from "@/features/attachments/model/attachmentErrors";
import { accountExistsProvider } from "@/features/auth/model/accountExists";
import { accountDeleteFailure } from "@/lib/accountDelete";
import { signInRefusalKey } from "@/features/auth/model/signInRefusal";
import { ApiRequestError } from "@/lib/api/client";
import { CONSENT_REQUIRED_CODE } from "@/lib/api/consentRefusal";
import { scanFailureMessage } from "@/features/scanner/model/scanReadError";
import { refusalCode, resolveChatError } from "@/features/chat/model/errorMessage";
import { memoryFailure, memoryFailureKey } from "@/features/memory/model/memoryFailure";
import {
  liveTalkErrorGate,
  liveTalkGateMessageKey,
  liveTalkSaveEndsCall,
} from "@/features/speech/model/liveTalkLogic";
import { voiceRefusalKey } from "@/features/speech/model/voiceRefusal";

jest.mock("@/lib/config", () => ({ getApiUrl: () => "http://test.local" }));
jest.mock("@/lib/auth", () => ({
  getSessionGeneration: () => 0,
  requireTokenSession: jest.fn(),
  SessionChangedError: class extends Error {},
  getRefreshToken: jest.fn(),
  setTokenPair: jest.fn(),
}));

type Refusal = { status: number; detail: unknown };
const refusals = fixture as Record<string, Refusal>;
const t = (key: string) => key;

function refused(name: string): ApiRequestError {
  const refusal = refusals[name];
  if (!refusal) throw new Error(`no ${name} in docs/fixtures/error_codes.json`);
  return new ApiRequestError(refusal.status, JSON.stringify({ detail: refusal.detail }));
}

it("reads every refusal's code and words from its body once", () => {
  for (const [name, refusal] of Object.entries(refusals)) {
    const error = refused(name);
    expect(error.message).not.toBe("");
    if (refusal.status !== 422) expect(error.code).toBe((refusal.detail as { code: string }).code);
  }
});

it("opens the consent screen on consent_required", () => {
  expect(refused("consent_required").code).toBe(CONSENT_REQUIRED_CODE);
});

it("offers the earlier way to sign in", () => {
  expect(accountExistsProvider(refused("account_exists"))).toBe("apple");
});

it.each([
  ["sign_in_rate_limited", "login.error_rate_limited"],
  // Dev login passes the request limiter: over its minute is the API's own coded 429.
  ["rate_limited", "login.error_rate_limited"],
  ["sign_in_unavailable", "login.error_unavailable"],
  // Dev login passes the request limiter: Redis down there is the API's own outage body.
  ["service_unavailable", "login.error_unavailable"],
  ["google_unavailable", "login.error_unavailable"],
  ["apple_unavailable", "login.error_unavailable"],
  ["google_token_invalid", "login.error_token_invalid"],
  ["apple_token_invalid", "login.error_token_invalid"],
  ["apple_key_unknown", "login.error_token_invalid"],
  ["google_email_unverified", "login.error_google_email_unverified"],
  ["apple_email_unverified", "login.error_apple_email_unverified"],
  ["google_email_missing", "login.error_google_email_missing"],
  ["apple_email_missing", "login.error_apple_email_missing"],
  ["apple_not_configured", "login.error_apple_not_configured"],
  ["dev_auth_disabled", "login.error_dev_disabled"],
])("words a refused sign-in: %s", (name, key) => {
  expect(signInRefusalKey(refused(name))).toBe(key);
});

it.each([
  ["scan_not_available", "chat.scan_unavailable"],
  ["scan_too_large", "chat.scan_too_large"],
  ["scan_rate_limited", "chat.scan_rate_limit"],
  ["scan_spend_cap", "chat.scan_spend_cap"],
  ["scan_invalid_image", null],
  // The request limiter's 429 and a refused refresh: their English showed.
  ["rate_limited", "chat.rate_limited"],
  ["refresh_rate_limited", "chat.rate_limited"],
  // A Redis outage said "Too many scans in a row", then "couldn't scan that photo".
  ["service_unavailable", "common.service_unavailable"],
])("words a refused scan: %s", (name, words) => {
  expect(scanFailureMessage(refused(name), t)).toBe(words);
});

it.each([
  ["presign_unsupported_type", "unsupported_type"],
  ["presign_too_large", "too_large"],
  ["presign_daily_limit", "daily_limit"],
])("names a refused upload: %s", (name, reason) => {
  const failure = presignFailure(refused(name));
  expect(failure).toBeInstanceOf(AttachmentError);
  expect((failure as AttachmentError).reason).toBe(reason);
});

it.each([
  ["image_daily_limit", false, "quota", "chat.image_daily_limit_free"],
  ["image_daily_limit", true, "notice", "chat.image_daily_limit_paid"],
  ["image_content_blocked", false, "notice", "chat.image_content_blocked"],
  // The day's spend cap: the server's English showed in every language. Redis down at its
  // read is the outage line; the outage answered the cap's 429, "temporarily unavailable".
  ["image_spend_cap", false, "generic", "chat.image_spend_cap"],
  ["service_unavailable", false, "generic", "common.service_unavailable"],
])("words a refused picture: %s (paid %s)", (name, isPaid, kind, words) => {
  const error = refused(name);
  // Every refusal from the picture endpoint is the picture's own (useChatImageGeneration).
  const code = refusalCode(error.code ?? undefined, "image_generation");
  expect(resolveChatError({ message: error.message, code, isPaid, t })).toEqual({ kind, message: words });
});

it.each([
  ["dictation_daily_limit", "chat.voice_daily_limit"],
  ["dictation_rate_limited", "chat.voice_rate_limited"],
  ["voice_spend_cap", "chat.voice_paused"],
  // Redis down at the spend read answered the cap's 429: "Voice input is paused".
  ["service_unavailable", "common.service_unavailable"],
  // The request limiter's 429 and a refused refresh said "Could not transcribe your
  // recording": a retry within the minute failed too.
  ["rate_limited", "chat.rate_limited"],
  ["refresh_rate_limited", "chat.rate_limited"],
])("words a refused dictation: %s", (name, words) => {
  expect(voiceRefusalKey(refused(name))).toBe(words);
});

// Every 503 said "Live talk isn't set up on this server yet", a Redis outage included.
it.each([
  ["service_unavailable", "outage", "common.service_unavailable"],
  ["live_talk_not_configured", "unconfigured", "chat.live_talk_not_configured"],
])("gates live talk on a refusal: %s", (name, gate, words) => {
  expect(liveTalkErrorGate(refused(name))).toBe(gate);
  expect(liveTalkGateMessageKey(liveTalkErrorGate(refused(name)))).toBe(words);
});

// Both said "Live talk isn't available in this version of the app. Update the app".
it.each([
  ["live_talk_upstream_failed", "connect_failed", "chat.live_talk_connect_failed"],
  ["live_talk_not_available", "off", "chat.live_talk_off"],
])("words a live talk start the app's age has nothing to do with: %s", (name, gate, words) => {
  expect(liveTalkErrorGate(refused(name))).toBe(gate);
  expect(liveTalkGateMessageKey(liveTalkErrorGate(refused(name)))).toBe(words);
});

// Every 403 opened the paywall, consent_required too, on top of the consent step.
it.each([
  ["live_talk_not_in_plan", "upgrade"],
  ["live_talk_consent_required", "consent"],
])("sends a refused live talk 403 by its code: %s", (name, gate) => {
  expect(liveTalkErrorGate(refused(name))).toBe(gate);
});

// Every 429 said "You've used this month's live talk minutes": a rate limit, the spend
// cap and a call's last save too.
it.each([
  ["live_talk_minutes_used", "limit", "chat.live_talk_limit_body"],
  ["live_talk_rate_limited", "rate_limited", "chat.live_talk_rate_limited"],
  ["live_talk_spend_cap", "paused", "chat.live_talk_paused"],
  ["live_talk_save_rate_limited", "rate_limited", "chat.live_talk_rate_limited"],
  ["live_talk_save_spend_cap", "paused", "chat.live_talk_paused"],
  ["live_talk_saves_used", "saves_used", "chat.live_talk_saves_used"],
  // The request limiter's 429: too many requests, as when it named no code.
  ["rate_limited", "rate_limited", "chat.live_talk_rate_limited"],
])("words a refused live talk 429 by its code: %s", (name, gate, words) => {
  expect(liveTalkErrorGate(refused(name))).toBe(gate);
  expect(liveTalkGateMessageKey(liveTalkErrorGate(refused(name)))).toBe(words);
});

// A save the plan or the session no longer allowed showed the server's English and kept
// the call open.
it.each([
  ["live_talk_save_not_in_plan", "upgrade"],
  ["live_talk_session_ended", "session_ended"],
])("ends the call on a save refused by its code: %s", (name, gate) => {
  expect(liveTalkErrorGate(refused(name))).toBe(gate);
  expect(liveTalkSaveEndsCall(liveTalkErrorGate(refused(name)))).toBe(true);
});

it.each([
  // Redis down at the write lock or the spend read: it said "Memory is being updated" or
  // "Memory couldn't be updated. Try again." (the cap's "paused" refusal).
  ["service_unavailable", "unavailable", "common.service_unavailable"],
  ["memory_busy", "busy", "memory.busy"],
  ["memory_spend_cap", "paused", "memory.paused"],
  // The request limiter's 429 says wait, as the memory routes' own limit does; it said the
  // action failed ("Couldn't save. Try again."), and a retry within the minute failed too.
  ["rate_limited", "limited", "memory.limited"],
  // The memory routes' own hourly limit.
  ["memory_rate_limited", "limited", "memory.limited"],
])("words a refused memory edit: %s", (name, failure, words) => {
  expect(memoryFailure(refused(name))).toBe(failure);
  expect(memoryFailureKey(memoryFailure(refused(name)), "memory.edit_failed")).toBe(words);
});

it("words a chat turn the API could not serve", () => {
  const error = refused("service_unavailable");
  expect(resolveChatError({ message: error.message, code: error.code ?? undefined, isPaid: false, t }))
    .toEqual({ kind: "generic", message: "common.service_unavailable" });
});

// Each 429 named no code: a refused Regenerate said "Couldn't reach the server"
// (chatTurnState's refusalReport). The request limiter's, the chat stream's own, and a
// refresh's, which fails every request that needs one until its wait ends (lib/api/client.ts).
it.each(["rate_limited", "chat_rate_limited", "refresh_rate_limited"])("words a chat turn over a limit: %s", (name) => {
  const error = refused(name);
  expect(resolveChatError({ message: error.detail, code: error.code ?? undefined, isPaid: false, t }))
    .toEqual({ kind: "generic", message: "chat.rate_limited" });
});

// The account delete refused while Redis is down (the usage carry-over, the session purge)
// said "Could not delete your account", not that Recall was unavailable for a moment.
it.each([
  ["service_unavailable", "unavailable"],
  ["rate_limited", "failed"],
])("words a refused account delete: %s", (name, failure) => {
  expect(accountDeleteFailure(refused(name))).toBe(failure);
});
