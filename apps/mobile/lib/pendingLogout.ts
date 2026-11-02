/**
 * A sign-out the server has not heard yet. Signing out clears the phone at once, but the
 * logout request that revokes the session and forgets this device's push token can fail
 * (offline, a timeout, a 5xx). Then the server kept the token, and the signed-out
 * account's reminders kept arriving on this lock screen. The logout is written down
 * before it is sent and crossed off once the server answers; one still owed is sent again
 * at the next start, on each return to the app and when our API answers again.
 *
 * It holds tokens, so it lives in the secure store like the session itself (lib/auth.ts).
 */
import * as SecureStore from "expo-secure-store";

import { logoutSession } from "@/lib/api/client";
import { onConnectionAnswered } from "@/lib/api/connectionFailures";
import { getToken } from "@/lib/auth";
import { onAppStateChange } from "@/lib/foregroundRefresh";
import { reportFailure } from "@/lib/sentry";

export type ServerLogout = {
  accessToken: string;
  refreshToken: string | null;
  /** This device's Expo push token; null when it could not be read at sign-out. */
  pushToken: string | null;
};

type PendingLogout = ServerLogout & { queuedAt: number };

const PENDING_LOGOUTS_KEY = "phonia_pending_logouts_v1";
/** A phone signs out of a handful of accounts at most between connections. */
const MAX_PENDING = 5;
/** The refresh token's lifetime: after it the server has ended the session itself. */
export const PENDING_LOGOUT_MAX_AGE_MS = 30 * 24 * 60 * 60_000;

/** Each store operation reads and writes inside its own catch, so none rejects. */
let storage: Promise<unknown> = Promise.resolve();
/** null until the store was read this run; false once nothing is owed. */
let hasPending: boolean | null = null;
let retrying: Promise<void> | null = null;

/** One read-modify-write at a time, so a logout written down is never lost to another. */
function serial<T>(operation: () => Promise<T>): Promise<T> {
  const run = storage.then(operation, operation);
  storage = run;
  return run;
}

function isPending(value: unknown): value is PendingLogout {
  if (typeof value !== "object" || value === null) return false;
  const entry = value as Record<string, unknown>;
  return (
    typeof entry.accessToken === "string" && entry.accessToken !== "" &&
    (entry.refreshToken === null || typeof entry.refreshToken === "string") &&
    (entry.pushToken === null || typeof entry.pushToken === "string") &&
    typeof entry.queuedAt === "number"
  );
}

async function readPending(): Promise<PendingLogout[]> {
  try {
    const raw = await SecureStore.getItemAsync(PENDING_LOGOUTS_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter(isPending) : [];
  } catch (error) {
    // Unreadable: nothing is owed that this run can send.
    reportFailure("sign_out", error);
    return [];
  }
}

async function writePending(entries: PendingLogout[]): Promise<void> {
  hasPending = entries.length > 0;
  try {
    if (entries.length === 0) await SecureStore.deleteItemAsync(PENDING_LOGOUTS_KEY);
    else await SecureStore.setItemAsync(PENDING_LOGOUTS_KEY, JSON.stringify(entries));
  } catch (error) {
    // An unwritable store leaves only this run's attempt.
    reportFailure("sign_out", error);
  }
}

function crossOff(accessTokens: ReadonlySet<string>): Promise<void> {
  if (accessTokens.size === 0) return Promise.resolve();
  return serial(async () =>
    writePending((await readPending()).filter((entry) => !accessTokens.has(entry.accessToken))),
  );
}

/** Sign-out's server half: written down first, then sent, then crossed off when the server answered. */
export async function endServerSession(logout: Promise<ServerLogout>): Promise<void> {
  const entry: PendingLogout = { ...(await logout), queuedAt: Date.now() };
  await serial(async () => writePending([...(await readPending()), entry].slice(-MAX_PENDING)));
  if (await logoutSession(entry.accessToken, entry.refreshToken, entry.pushToken)) {
    await crossOff(new Set([entry.accessToken]));
  }
}

/** Someone is signed in on this phone; a store that cannot say counts as yes. */
async function signedIn(): Promise<boolean> {
  try {
    return (await getToken()) !== null;
  } catch (error) {
    reportFailure("sign_out", error);
    return true;
  }
}

async function retryOwed(readPushToken: () => Promise<string | null>): Promise<void> {
  const entries = await serial(readPending);
  hasPending = entries.length > 0;
  const done = new Set<string>();
  // Someone signed in since: their registration took this device's token, and the same
  // account signing back in must not lose it to its own old logout. The session is still revoked.
  const sendPushToken = entries.length > 0 && !(await signedIn());
  for (const entry of entries) {
    const age = Date.now() - entry.queuedAt;
    if (age < 0 || age > PENDING_LOGOUT_MAX_AGE_MS) {
      done.add(entry.accessToken);
      continue;
    }
    const pushToken = sendPushToken ? (entry.pushToken ?? (await readPushToken())) : null;
    if (!(await logoutSession(entry.accessToken, entry.refreshToken, pushToken))) break;
    done.add(entry.accessToken);
  }
  await crossOff(done);
}

/**
 * Send every logout still owed; one run at a time. Stops at the first that does not reach
 * the server. `readPushToken` never rejects (it answers null when it cannot read one).
 */
export function retryPendingLogouts(readPushToken: () => Promise<string | null>): Promise<void> {
  retrying ??= retryOwed(readPushToken).finally(() => {
    retrying = null;
  });
  return retrying;
}

/** Retry now, then on each return to the app and each answer from our API while one is owed. */
export function watchPendingLogouts(readPushToken: () => Promise<string | null>): () => void {
  const retry = () => {
    if (hasPending !== false) void retryPendingLogouts(readPushToken);
  };
  retry();
  const stopForeground = onAppStateChange((state) => {
    if (state === "active") retry();
  });
  const stopAnswers = onConnectionAnswered(retry);
  return () => {
    stopForeground();
    stopAnswers();
  };
}

export function resetPendingLogoutsForTest(): void {
  storage = Promise.resolve();
  hasPending = null;
  retrying = null;
}
