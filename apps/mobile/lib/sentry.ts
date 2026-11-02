/**
 * Optional Sentry: a no-op when EXPO_PUBLIC_SENTRY_DSN is unset. Same rule as
 * the API's (apps/api/app/core/sentry.py): an event carries what broke, never
 * what the user wrote, what the model answered, a request body or a token.
 *
 * The SDK (about 750 KB) loads inside the deferred init, not at launch. Until
 * then Sentry has no global handler, as before; a boundary crash reported in
 * that window waits in a short queue and is sent once the SDK is up.
 */

import type { Breadcrumb, ErrorEvent } from "@sentry/react-native";

import { isServerUnreachable } from "@/lib/api/deadline";
import { isRequestId } from "@/lib/api/requestId";
import type { FenceId } from "@/lib/fenceRegistry";
import type { FenceRefusal, FenceReportName } from "@/lib/fenceReports";

type SentrySdk = typeof import("@sentry/react-native");

/** The SDK once `init` has run. */
let sdk: SentrySdk | null = null;
let starting: Promise<void> | null = null;

/** A crash loop before init keeps only the first few; a minor report takes at most half. */
const MAX_EARLY_REPORTS = 10;
const MAX_EARLY_MINOR_REPORTS = MAX_EARLY_REPORTS / 2;
const earlyReports: ((sentry: SentrySdk) => void)[] = [];

function configuredDsn(): string | undefined {
  return process.env.EXPO_PUBLIC_SENTRY_DSN?.trim() || undefined;
}

const SENSITIVE_HEADERS = new Set([
  "authorization",
  "cookie",
  "set-cookie",
  "x-api-key",
  "x-forwarded-authorization",
]);

// Bearer tokens, JWTs (our access tokens), Live Talk's ek_ secret, provider keys.
const SECRET_PATTERNS: readonly RegExp[] = [
  /\bBearer\s+[A-Za-z0-9._~+/=-]+/gi,
  /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+/g,
  /\b(?:ek|sk|rk)_[A-Za-z0-9_-]{8,}/g,
];

/** Errors can quote what they choked on; keep the start, which says what broke. */
const MAX_ERROR_TEXT = 300;

export function redactSecrets(text: string): string {
  let out = text;
  for (const pattern of SECRET_PATTERNS) out = out.replace(pattern, "[REDACTED]");
  return out.length > MAX_ERROR_TEXT ? `${out.slice(0, MAX_ERROR_TEXT)}…` : out;
}

function withoutQuery(url: unknown): unknown {
  return typeof url === "string" ? url.split(/[?#]/, 1)[0] : url;
}

/** Console lines can hold chat text; network crumbs keep only method, path and status. */
export function scrubBreadcrumb(breadcrumb: Breadcrumb): Breadcrumb | null {
  if (breadcrumb.category === "console") return null;
  const data = breadcrumb.data;
  if (!data) return breadcrumb;
  const kept: Record<string, unknown> = {};
  for (const key of ["method", "status_code", "url", "from", "to", "request_id"]) {
    if (key in data) kept[key] = key === "url" ? withoutQuery(data[key]) : data[key];
  }
  return { ...breadcrumb, data: kept };
}

/**
 * Drop bodies, query strings, cookies, auth headers, extras and user fields. An API
 * refusal's call id becomes the event's `request_id` tag, the API's log lines' own id.
 */
export function scrubSentryEvent(
  event: ErrorEvent,
  hint?: { originalException?: unknown },
): ErrorEvent | null {
  const requestId = (hint?.originalException as { requestId?: unknown } | null | undefined)
    ?.requestId;
  if (isRequestId(requestId)) event.tags = { ...event.tags, request_id: requestId };
  const request = event.request;
  if (request) {
    delete request.data;
    delete request.cookies;
    request.query_string = undefined;
    request.url = withoutQuery(request.url) as string | undefined;
    for (const name of Object.keys(request.headers ?? {})) {
      if (SENSITIVE_HEADERS.has(name.toLowerCase()) && request.headers) {
        request.headers[name] = "[REDACTED]";
      }
    }
  }
  delete event.extra;
  if (event.user) event.user = event.user.id ? { id: event.user.id } : undefined;
  if (event.message) event.message = redactSecrets(event.message);
  for (const exception of event.exception?.values ?? []) {
    if (exception.value) exception.value = redactSecrets(exception.value);
  }
  if (event.breadcrumbs) {
    event.breadcrumbs = event.breadcrumbs
      .map(scrubBreadcrumb)
      .filter((crumb): crumb is Breadcrumb => crumb !== null);
  }
  return event;
}

/**
 * Requests that carry Sentry's trace headers: our API's, and no one else's. On a phone
 * the SDK's default is every URL, so OpenAI's realtime call, Google's connectivity check
 * and each storage upload carried the DSN's public key, the environment and a trace id
 * (`baggage` and `sentry-trace`, about 200 bytes).
 */
function apiTraceTargets(apiUrl: string): RegExp[] {
  const origin = apiUrl.replace(/\/+$/, "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return [new RegExp(`^${origin}(?:[/?#]|$)`)];
}

/** Loads and starts the SDK once; resolves when it is up, or at once without a DSN. */
export function initMobileSentry(): Promise<void> {
  const dsn = configuredDsn();
  if (!dsn) return Promise.resolve();
  starting ??= Promise.all([import("@sentry/react-native"), import("@/lib/config")]).then(
    ([Sentry, { getApiUrl }]) => {
      Sentry.init({
        dsn,
        enabled: !__DEV__,
        tracesSampleRate: 0.1,
        tracePropagationTargets: apiTraceTargets(getApiUrl()),
        sendDefaultPii: false,
        beforeSend: scrubSentryEvent,
        beforeBreadcrumb: scrubBreadcrumb,
      });
      sdk = Sentry;
      for (const report of earlyReports.splice(0)) report(Sentry);
    },
    () => {
      // The SDK could not load (a dev bundle offline): the next init tries again.
      starting = null;
    },
  );
  return starting;
}

/**
 * A render crash an error boundary kept inside one message or one screen (one
 * block of a reply is `reportFenceCrash`). The boundary shows its fallback either way;
 * this only reports it, and only when Sentry is configured (before the SDK is
 * up, it waits in the queue). The component stack names components, never
 * their text; `screen` is the route's file path (`memory/[key]`), never its
 * values.
 */
export function reportBoundaryError(
  boundary: "markdown" | "message_row" | "screen",
  error: Error,
  componentStack?: string | null,
  screen?: string,
): void {
  report((Sentry) => {
    Sentry.captureException(error, {
      tags: screen ? { boundary, screen } : { boundary },
      contexts: componentStack ? { react: { componentStack } } : undefined,
    });
  });
}

/**
 * The app store could not be read when the upgrade sheet opened. The sheet says
 * so and offers a retry; this tells us, since an outage otherwise looks like a
 * store with nothing to sell (code-health audit CLAR-08).
 */
export function reportStoreUnavailable(error: unknown): void {
  report((Sentry) => {
    Sentry.captureException(error, { tags: { area: "store" } });
  });
}

/**
 * Turning push off could not remove this phone's token from the server. The switch
 * still turns off (the account setting stops sends) and the next sync tries again;
 * this says so, since the call failing on every phone once went unseen.
 */
export function reportPushUnregisterFailed(error: unknown): void {
  report((Sentry) => {
    Sentry.captureException(error, { tags: { area: "push_unregister" } });
  });
}

/**
 * The stored sign-in was there but was no session (cut short, or not a token
 * pair), so the launch cleared it and opened on sign-in. The event is that fact
 * alone, to count how often it happens: never the record, a token or whose it
 * was. A keychain that cannot be read yet, or a network error, is not this:
 * that launch keeps the sign-in and offers Retry and Sign out.
 */
export function reportCorruptSessionCleared(): void {
  report((Sentry) => {
    Sentry.captureMessage("Stored sign-in was not a session; cleared at launch", {
      level: "warning",
      tags: { area: "stored_session" },
    });
  });
}

/**
 * A call to our API that failed: a crumb with its method, path (no query, which can
 * hold what the user searched), status and id, so the next report names the call.
 * Before the SDK is up there is nowhere to put it, and it is dropped.
 */
export function noteApiFailure(
  method: string,
  path: string,
  status: number | null,
  requestId: string,
): void {
  try {
    sdk?.addBreadcrumb({
      category: "api",
      level: "warning",
      message: "API call failed",
      data: {
        method,
        url: withoutQuery(path),
        status_code: status ?? undefined,
        request_id: requestId,
      },
    });
  } catch {
    // Best effort: the caller gets the call's own response or error, never this one.
    return;
  }
}

/**
 * Sent at once when the SDK is up; before that it waits in the short queue. A minor
 * report (a refused fence, a handled failure) waits only while the queue is under half
 * full, so a crash at launch still has room.
 */
function report(capture: (sentry: SentrySdk) => void, minor = false): void {
  if (sdk) {
    capture(sdk);
    return;
  }
  const room = minor ? MAX_EARLY_MINOR_REPORTS : MAX_EARLY_REPORTS;
  if (!configuredDsn() || earlyReports.length >= room) return;
  earlyReports.push(capture);
}

const HOUR_MS = 60 * 60_000;

/**
 * Whether a report may go: one per key every `repeatMs`, and `perHour` in all, so a long
 * chat of broken fences or a read failing in a loop cannot flood Sentry.
 */
function reportLimit(repeatMs: number, perHour: number): (key: string) => boolean {
  const lastSent = new Map<string, number>();
  let sent: number[] = [];
  return (key) => {
    const now = Date.now();
    const last = lastSent.get(key);
    if (last !== undefined && now - last < repeatMs) return false;
    sent = sent.filter((at) => now - at < HOUR_MS);
    if (sent.length >= perHour) return false;
    lastSent.set(key, now);
    sent.push(now);
    return true;
  };
}

/** A class name or a kind that is one word, never a sentence the error quoted. */
const SAFE_NAME = /^[A-Za-z][A-Za-z0-9_]{0,39}$/;
/** A refusal's code (`rate_limited`, a store's numeric code), never a sentence. */
const SAFE_CODE = /^[A-Za-z0-9_.-]{1,40}$/;

/**
 * The frames of `error`'s stack. The stack opens with the message, which can run over
 * several lines and hold one that reads like a frame ("  at noon"): everything up to the
 * message's end is cut before the frames are kept.
 */
function stackFrames(error: Error): string[] {
  let stack = error.stack ?? "";
  const message = error.message;
  const end = message ? stack.indexOf(message) : -1;
  if (end >= 0) stack = stack.slice(end + message.length);
  return stack.split("\n").filter((line) => /^\s+at /.test(line));
}

/**
 * `error` with its message replaced by `label`: its class and stack frames, which say
 * where it broke, and none of the text it carried (a parser's error can quote the body
 * it choked on; a refusal, the server's words about what was sent).
 */
function withoutMessage(error: unknown, label: string): Error {
  const name = error instanceof Error && SAFE_NAME.test(error.name) ? error.name : "Error";
  const out = new Error(label);
  out.name = name;
  out.stack = [`${name}: ${label}`, ...(error instanceof Error ? stackFrames(error) : [])].join("\n");
  return out;
}

/** A fence crash reports once per fence and error class a minute, twenty an hour in all. */
const fenceCrashAllowed = reportLimit(60_000, 20);

/**
 * A fence's block threw while it was built or drawn (`renderFence`, `FenceErrorBoundary`).
 * The block falls back either way; this reports it, tagged with the fence's registry id
 * or the kind of block it was drawn as (`lib/fenceReports.ts`), never the tag the reply
 * wrote. The error goes without its message, which can quote the fence's body.
 */
export function reportFenceCrash(
  fence: FenceReportName,
  error: unknown,
  componentStack?: string | null,
): void {
  const reported = withoutMessage(error, "Fence render failed");
  if (!fenceCrashAllowed(`${fence}:${reported.name}`)) return;
  report((Sentry) => {
    Sentry.captureException(reported, {
      tags: { boundary: "fence", fence },
      contexts: componentStack ? { react: { componentStack } } : undefined,
    });
  });
}

/** A refused fence reports once per fence and reason an hour, ten an hour in all. */
const fenceRefusalAllowed = reportLimit(HOUR_MS, 10);

/**
 * The phone would not draw a fence: which one and why (`lib/fenceReports.ts`), nothing
 * of its body. The block shows its own fallback either way.
 */
export function reportFenceRefused(fence: FenceId, reason: FenceRefusal): void {
  if (!fenceRefusalAllowed(`${fence}:${reason}`)) return;
  report((Sentry) => {
    Sentry.captureMessage("Fence refused", {
      level: "warning",
      tags: { area: "fence_refused", fence, reason },
      fingerprint: ["fence_refused", fence, reason],
    });
  }, true);
}

/**
 * Where a user's action failed after the screen handled it (a toast, the draft given
 * back, the page on screen kept).
 */
export type FailureArea =
  | "chat_create"
  | "chat_load"
  | "chat_refresh"
  | "chat_page"
  | "attachment_upload"
  | "paywall_load"
  | "purchase"
  | "purchase_restore"
  | "purchase_sync";

/** A handled failure reports once per area and kind every ten minutes, twenty an hour in all. */
const failureAllowed = reportLimit(10 * 60_000, 20);

/** What kind of failure: its class, an HTTP status, a refusal's code. Never its text. */
function failureTags(area: FailureArea, error: unknown): Record<string, string> {
  const fields = (typeof error === "object" && error !== null ? error : {}) as {
    name?: unknown;
    status?: unknown;
    code?: unknown;
    reason?: unknown;
  };
  const name = typeof fields.name === "string" && SAFE_NAME.test(fields.name) ? fields.name : "unknown";
  const tags: Record<string, string> = { area, error: name };
  if (typeof fields.status === "number" && Number.isInteger(fields.status)) {
    tags.status = String(fields.status);
  }
  const code = typeof fields.code === "string" || typeof fields.code === "number"
    ? String(fields.code)
    : fields.reason;
  if (typeof code === "string" && SAFE_CODE.test(code)) tags.code = code;
  return tags;
}

/**
 * A user's action that failed and was handled on screen: where (`area`) and what kind
 * of failure, as tags, with the stack but never the error's text. A call that found no
 * API (offline, a timeout), one cancelled, and one a sign-out overtook are not reported:
 * the connection banner and the next sign-in own those.
 */
export function reportFailure(area: FailureArea, error: unknown): void {
  const name = (error as { name?: unknown } | null | undefined)?.name;
  if (isServerUnreachable(error) || name === "SessionChangedError") return;
  const tags = failureTags(area, error);
  if (!failureAllowed(Object.values(tags).join(":"))) return;
  const requestId = (error as { requestId?: unknown } | null | undefined)?.requestId;
  const reported = withoutMessage(error, `${area} failed`);
  report((Sentry) => {
    Sentry.captureException(reported, {
      level: "warning",
      tags: isRequestId(requestId) ? { ...tags, request_id: requestId } : tags,
      fingerprint: ["handled_failure", ...Object.values(tags)],
    });
  }, true);
}
