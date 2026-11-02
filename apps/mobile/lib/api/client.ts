import { ApiRequestError, readErrorBody, readRetryAfter, UNAVAILABLE_STATUSES } from "@/lib/api/errorBody";
import { isAbortError } from "@/lib/api/abort";
import { abortError, serverUnreachableError, untilAborted, withDeadline } from "@/lib/api/deadline";
import { getApiUrl } from "@/lib/config";
import {
  getRefreshToken,
  getSessionGeneration,
  requireTokenSession,
  SessionChangedError,
  setTokenPair,
} from "@/lib/auth";

import { reportConnectionAnswered, reportConnectionFailure } from "@/lib/api/connectionFailures";
import { newRequestId, REQUEST_ID_HEADER, responseRequestId } from "@/lib/api/requestId";
import { CONSENT_REQUIRED_CODE, notifyConsentRequired } from "@/lib/api/consentRefusal";
import type { AuthResult, User } from "@/lib/api/types";
import { deviceSessionFields } from "@/lib/deviceSession";
import { noteApiFailure } from "@/lib/sentry";

let onUnauthorized: (() => void) | null = null;
let onTokenRefresh: ((accessToken: string, user?: User) => void) | null = null;

export function setUnauthorizedHandler(fn: (() => void) | null): void {
  onUnauthorized = fn;
}

export function notifyUnauthorized(generation = getSessionGeneration()): void {
  if (generation === getSessionGeneration()) onUnauthorized?.();
}

/** A 403 `consent_required` for this account opens the consent screen again.
 * The body is cloned before the caller reads its own copy for the error it throws. */
async function readConsentRefusal(response: Response, generation: number): Promise<void> {
  try {
    const body = await response.clone().text();
    if (generation === getSessionGeneration() && readErrorBody(body).code === CONSENT_REQUIRED_CODE) {
      notifyConsentRequired();
    }
  } catch {
    /* an unreadable body is an ordinary 403 */
  }
}

export function setTokenRefreshHandler(
  fn: ((accessToken: string, user?: User) => void) | null,
): void {
  onTokenRefresh = fn;
}

function requireSession(generation: number): void {
  if (generation !== getSessionGeneration()) throw new SessionChangedError();
}

function requireNotAborted(signal?: AbortSignal | null): void {
  if (signal?.aborted) throw abortError();
}

/**
 * Decode JWT expiry only as a latency hint. Authentication still belongs to
 * the server; unreadable/opaque tokens keep the existing request-then-401
 * behavior instead of being rejected by the client.
 */
export function accessTokenNeedsRefresh(
  token: string,
  nowMs: number = Date.now(),
  skewMs = 30_000,
): boolean {
  try {
    const parts = token.split(".");
    if (parts.length !== 3 || parts.some((part) => !part)) return false;
    const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = payload.padEnd(Math.ceil(payload.length / 4) * 4, "=");
    const claims: unknown = JSON.parse(atob(padded));
    if (typeof claims !== "object" || claims === null || !("exp" in claims)) return false;
    const exp = (claims as { exp?: unknown }).exp;
    if (typeof exp !== "number" || !Number.isFinite(exp)) return false;
    return exp * 1000 <= nowMs + Math.max(0, skewMs);
  } catch {
    return false;
  }
}

export const AUTH_FETCH_TIMEOUT_MS = 15_000;

/** A fetch outside a session (sign-in, sign-out) that gives up after 15 s without
 * headers; `init.signal` aborts it too. The caller bounds the body it reads. It carries
 * a call id like every call to the API (`requestId.ts`). */
export async function fetchWithTimeout(url: string, init: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), AUTH_FETCH_TIMEOUT_MS);
  const forwardAbort = () => controller.abort();
  init.signal?.addEventListener("abort", forwardAbort, { once: true });
  if (init.signal?.aborted) controller.abort();
  const headers = { ...(init.headers as Record<string, string> | undefined), [REQUEST_ID_HEADER]: newRequestId() };
  try {
    return await fetch(url, { ...init, headers, signal: controller.signal });
  } catch (error) {
    if (isAbortError(error)) throw serverUnreachableError();
    throw error;
  } finally {
    clearTimeout(timeout);
    init.signal?.removeEventListener("abort", forwardAbort);
  }
}

let refreshInFlight: { generation: number; promise: Promise<string | null> } | null = null;

/**
 * The access token this sign-in's last refresh returned. A 401 for a token it has
 * since replaced is sent again with it, not answered with a refresh of its own: on a
 * busy server the 401s of requests sent together land seconds apart, and each one
 * after the first refresh finished started another (six 401s, five refreshes).
 */
let lastRefreshed: { generation: number; token: string; user: User | null } | null = null;

/** This sign-in's refresh token was refused (401, or none stored): asking again cannot help. */
let refreshRejected: number | null = null;

/**
 * The account the refresh that issued `token` answered with, or null for any other token.
 * At launch an expired token is refreshed first, and that answer is the account /auth/me
 * would read: most launches come more than the token's hour after the last.
 */
export function refreshedAccount(token: string | null): User | null {
  const last = lastRefreshed;
  return token && last?.generation === getSessionGeneration() && last.token === token ? last.user : null;
}

/**
 * A refresh the server turned away with a `Retry-After` (its per-account limit's 429, a 503):
 * until then a request that needs one fails with that refusal instead of asking again.
 * Each request used to ask: ten refreshes in 20 s against a limit that said "60 s".
 */
let refreshRefused: { generation: number; until: number; error: ApiRequestError } | null = null;

/** A refused response as the error a caller throws, with its `Retry-After`. */
async function refusal(response: Response): Promise<ApiRequestError> {
  return new ApiRequestError(
    response.status,
    await response.text(),
    readRetryAfter(responseHeader(response, "retry-after")),
    responseRequestId(response),
  );
}

/** The token this sign-in's last refresh put in place of `token`, if it did. */
function replacedToken(token: string, generation: number): string | null {
  const last = lastRefreshed;
  return last?.generation === generation && last.token !== token ? last.token : null;
}

/** Share refresh within one session. Only an absent/rejected refresh credential
 * returns null; outages and secure storage failures must not sign the user out.
 * One deadline covers the whole refresh, its body and secure storage included: a
 * stalled one used to hold every request behind it until the app was killed. At
 * the deadline it fails, and the next request starts a new one. */
async function refreshAccessToken(): Promise<string | null> {
  const generation = getSessionGeneration();
  if (refreshInFlight?.generation === generation) return refreshInFlight.promise;
  if (refreshRejected === generation) return null;
  const refused = refreshRefused;
  if (refused?.generation === generation && Date.now() < refused.until) throw refused.error;
  const promise = withDeadline(AUTH_FETCH_TIMEOUT_MS, null, async (signal) => {
    const refreshToken = await getRefreshToken();
    requireSession(generation);
    if (!refreshToken) {
      refreshRejected = generation;
      return null;
    }
    const response = await fetchApi("/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken, ...deviceSessionFields() }),
      signal,
    }, generation);
    requireSession(generation);
    if (response.status === 401) {
      refreshRejected = generation;
      return null;
    }
    if (!response.ok) {
      const error = await refusal(response);
      if (error.retryAfterMs) refreshRefused = { generation, until: Date.now() + error.retryAfterMs, error };
      throw error;
    }
    const data = (await response.json()) as AuthResult;
    requireSession(generation);
    if (!data || typeof data.access_token !== "string" || !data.access_token ||
      typeof data.refresh_token !== "string" || !data.refresh_token) {
      throw new Error("Recall returned an invalid sign-in response. Please try again.");
    }
    const saved = await setTokenPair(data.access_token, data.refresh_token, generation);
    requireSession(generation);
    if (!saved) throw new SessionChangedError();
    lastRefreshed = { generation, token: data.access_token, user: data.user ?? null };
    refreshRefused = null;
    onTokenRefresh?.(data.access_token, data.user);
    return data.access_token;
  }, serverUnreachableError);
  refreshInFlight = { generation, promise };
  try {
    return await promise;
  } finally {
    // An old account's completion must not release a newer account's refresh.
    if (refreshInFlight?.promise === promise) refreshInFlight = null;
  }
}

/**
 * `token`, or a refreshed one when it is about to expire: the same single-flight refresh
 * a request makes. A long-lived WebSocket kept the token it was made with, so a return
 * after an hour authenticated with an expired one and fell back to SSE for good
 * (code-health audit NET-12); it reads its token through this before it connects.
 */
export async function freshAccessToken(token: string | null): Promise<string | null> {
  if (!token || !accessTokenNeedsRefresh(token)) return token;
  const generation = getSessionGeneration();
  const refreshed = await refreshAccessToken();
  return generation === getSessionGeneration() ? (refreshed ?? token) : null;
}

/** `pushToken` is this device's Expo push token: the server forgets it with the session, so
 * the signed-out account's reminders stop reaching this lock screen. */
export async function logoutSession(
  token: string,
  refreshToken: string | null,
  pushToken: string | null = null,
): Promise<void> {
  try {
    await fetchWithTimeout(apiUrl("/auth/logout"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        refresh_token: refreshToken,
        ...(pushToken ? { expo_push_token: pushToken } : {}),
      }),
    });
  } catch {
    /* Server revocation is best-effort; local credential removal is independent. */
  }
}

export { ApiRequestError };

export function apiUrl(path: string) {
  return `${getApiUrl()}${path}`;
}

/**
 * `fetch` to our API. One that finds no API (no answer, or a 502, 503 or 504) asks the
 * connection check to look (lib/api/connectionFailures.ts); a cancel or a timeout, any other
 * status, and a request of an account signed out since do not. One answered (a 2xx or 304)
 * says when it was sent: sent after an outage was seen, it is the API back.
 */
async function fetchApi(path: string, init: RequestInit, generation: number): Promise<Response> {
  const sentAt = Date.now();
  const requestId = newRequestId();
  let unreachable = false;
  let answered = false;
  let status: number | null = null;
  try {
    const headers = { ...(init.headers as Record<string, string> | undefined), [REQUEST_ID_HEADER]: requestId };
    const response = await fetch(apiUrl(path), { ...init, headers });
    status = response.status;
    unreachable = UNAVAILABLE_STATUSES.has(response.status);
    answered = response.ok || response.status === 304;
    return response;
  } catch (error) {
    unreachable = !init.signal?.aborted && !isAbortError(error);
    throw error;
  } finally {
    if (unreachable && generation === getSessionGeneration()) reportConnectionFailure();
    if (answered) reportConnectionAnswered(sentAt);
    // A call the API failed (no answer, or a 5xx) leaves a crumb with its id: the next
    // report sent says which call it was. An expected refusal (401, 404, 409) does not.
    else if (unreachable || (status !== null && status >= 500)) {
      noteApiFailure(init.method ?? "GET", path, status, requestId);
    }
  }
}

export async function request<T>(
  path: string,
  token: string,
  init?: RequestInit,
  allowRefresh = true,
  timeoutMs = 30_000,
): Promise<T> {
  const generation = getSessionGeneration();
  return withDeadline(timeoutMs, init?.signal, async (signal) => {
    const response = await requestRaw(path, token, {
      ...init,
      signal,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    }, allowRefresh, timeoutMs);
    if (!response.ok) throw await refusal(response);
    const data = response.status === 204 ? undefined : await response.json();
    requireSession(generation);
    return data as T;
  });
}

/**
 * Lists the server answers with an ETag (the to-do list, the chat list, a chat's
 * newest messages): the reply is kept, and the next read of the same path sends its
 * ETag back, so an unchanged list costs a 304 and no body (code-health audit NET-16).
 * Only this sign-in's replies are used.
 */
const MAX_REVALIDATED = 40;
const revalidated = new Map<string, { generation: number; etag: string; data: unknown }>();

function responseHeader(response: Response, name: string): string | null {
  // Test doubles and some transports have no headers object.
  return typeof response.headers?.get === "function" ? response.headers.get(name) : null;
}

export async function requestRevalidated<T>(
  path: string,
  token: string,
  init?: RequestInit,
  timeoutMs = 30_000,
): Promise<T> {
  const generation = getSessionGeneration();
  const held = revalidated.get(path);
  const kept = held?.generation === generation ? held : undefined;
  return withDeadline(timeoutMs, init?.signal, async (signal) => {
    const response = await requestRaw(path, token, {
      ...init,
      signal,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
        ...(kept ? { "If-None-Match": kept.etag } : {}),
      },
    }, true, timeoutMs);
    requireSession(generation);
    if (response.status === 304 && kept) {
      revalidated.delete(path);
      revalidated.set(path, kept);
      return kept.data as T;
    }
    if (!response.ok) throw await refusal(response);
    const data = (await response.json()) as T;
    requireSession(generation);
    const etag = responseHeader(response, "etag");
    revalidated.delete(path);
    if (etag) {
      revalidated.set(path, { generation, etag, data });
      while (revalidated.size > MAX_REVALIDATED) {
        revalidated.delete(revalidated.keys().next().value as string);
      }
    }
    return data;
  });
}

const EXPORT_TIMEOUT_MS = 120_000;

export async function fetchExportText(
  token: string,
  allowRefresh = true,
  signal?: AbortSignal,
): Promise<string> {
  const generation = getSessionGeneration();
  return withDeadline(EXPORT_TIMEOUT_MS, signal, async (deadline) => {
    const response = await requestRaw("/auth/me/export", token, {
      headers: { Accept: "application/json" },
      signal: deadline,
    }, allowRefresh, EXPORT_TIMEOUT_MS);
    if (!response.ok) throw await refusal(response);
    const text = await response.text();
    requireSession(generation);
    return text;
  });
}

/** Single authenticated fetch boundary for JSON, downloads, and SSE. Raw
 * responses keep their bodies unread; auth recovery always happens here. */
export async function requestRaw(
  path: string,
  token: string | null,
  init?: RequestInit,
  allowRefresh = true,
  timeoutMs = 30_000,
  retainStreamAbort = false,
): Promise<Response> {
  if (token) requireTokenSession(token);
  const generation = getSessionGeneration();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  const externalSignal = init?.signal ?? null;
  const onExternalAbort = () => controller.abort();
  externalSignal?.addEventListener("abort", onExternalAbort, { once: true });
  let streamingBodyReturned = false;
  try {
    requireNotAborted(externalSignal);
    let effectiveToken = token;
    let refreshAttempted = false;
    // Cold start used to mount every provider with an expired token, causing
    // /me, /home, /chats, /models, etc. to all send one doomed 401 before
    // joining the shared refresh. Join that same single-flight *before* any
    // authenticated request leaves the device when expiry is already known.
    // A refresh another request started keeps running for it; this one waits only
    // as long as its own deadline and its caller allow (code-health audit NET-17).
    if (effectiveToken && allowRefresh && accessTokenNeedsRefresh(effectiveToken)) {
      refreshAttempted = true;
      const refreshed = await untilAborted(refreshAccessToken(), controller.signal);
      requireSession(generation);
      requireNotAborted(controller.signal);
      if (refreshed) effectiveToken = refreshed;
    }

    const headers = { ...(init?.headers ?? {}) } as Record<string, string>;
    if (effectiveToken) headers.Authorization = `Bearer ${effectiveToken}`;
    const response = await fetchApi(path, { ...init, signal: controller.signal, headers }, generation);
    requireSession(generation);
    requireNotAborted(controller.signal);
    if (response.status === 401 && effectiveToken) {
      const replaced = allowRefresh ? replacedToken(effectiveToken, generation) : null;
      if (replaced) return requestRaw(path, replaced, init, true, timeoutMs, retainStreamAbort);
      if (allowRefresh && !refreshAttempted) {
        const refreshed = await untilAborted(refreshAccessToken(), controller.signal);
        requireSession(generation);
        requireNotAborted(controller.signal);
        if (refreshed) return requestRaw(path, refreshed, init, false, timeoutMs, retainStreamAbort);
      }
      notifyUnauthorized(generation);
    }
    if (response.status === 403) void readConsentRefusal(response, generation);
    streamingBodyReturned = retainStreamAbort && response.ok && response.body != null;
    return response;
  } finally {
    // SSE callers own one AbortController per stream. Keep forwarding Stop
    // after headers; the once-listener is released on abort or with that signal.
    if (!streamingBodyReturned) externalSignal?.removeEventListener("abort", onExternalAbort);
    clearTimeout(timeout);
  }
}

/**
 * Native transfers (a download straight to disk) cannot go through fetch, so
 * they borrow its auth recovery: a known-expired token refreshes first, and one
 * 401 refreshes and retries once. `send` gets the headers to attach and
 * resolves to the HTTP status it saw.
 */
export async function authorizeNativeTransfer(
  token: string | null,
  send: (headers: Record<string, string>) => Promise<number>,
  allowRefresh = true,
): Promise<number> {
  if (token) requireTokenSession(token);
  const generation = getSessionGeneration();
  let effectiveToken = token;
  let refreshAttempted = false;
  if (effectiveToken && allowRefresh && accessTokenNeedsRefresh(effectiveToken)) {
    refreshAttempted = true;
    const refreshed = await refreshAccessToken();
    requireSession(generation);
    if (refreshed) effectiveToken = refreshed;
  }
  const status = await send({
    [REQUEST_ID_HEADER]: newRequestId(),
    ...(effectiveToken ? { Authorization: `Bearer ${effectiveToken}` } : {}),
  });
  requireSession(generation);
  if (status === 401 && effectiveToken) {
    const replaced = allowRefresh ? replacedToken(effectiveToken, generation) : null;
    if (replaced) return authorizeNativeTransfer(replaced, send, true);
    if (allowRefresh && !refreshAttempted) {
      const refreshed = await refreshAccessToken();
      requireSession(generation);
      if (refreshed) return authorizeNativeTransfer(refreshed, send, false);
    }
    notifyUnauthorized(generation);
  }
  return status;
}

/** Streaming counterpart to request; returns the raw event-stream response. */
export async function requestSse(
  path: string,
  token: string,
  body: Record<string, unknown>,
  signal?: AbortSignal,
  allowRefresh = true,
  timeoutMs = 30_000,
): Promise<Response> {
  return requestRaw(path, token, {
    method: "POST",
    signal,
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
  }, allowRefresh, timeoutMs, true);
}
