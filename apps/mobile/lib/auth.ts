import * as SecureStore from "expo-secure-store";

export { clearOnboarded, getOnboarded, setOnboarded } from "@/lib/onboarding";

const SESSION_KEY = "recall_session_v1";

type TokenPair = { accessToken: string; refreshToken: string | null };

class AuthStorageError extends Error {
  constructor() {
    super("Recall could not access secure sign-in storage on this device. Please restart the app and try again.");
    this.name = "AuthStorageError";
  }
}

/**
 * The session record was read but is not a session (cut short, or not a token
 * pair). Unlike a keychain that cannot be read yet, no retry can turn it into
 * one: startup clears it and opens on sign-in (contexts/AuthContext.tsx).
 */
export class CorruptSessionError extends AuthStorageError {
  constructor() {
    super();
    this.name = "CorruptSessionError";
  }
}

export class SessionChangedError extends Error {
  constructor() {
    super("Your sign-in changed. Please try again.");
    this.name = "SessionChangedError";
  }
}

let sessionGeneration = 0;
const sessionAccessTokens = new Set<string>();
let storageQueue: Promise<void> = Promise.resolve();

export function getSessionGeneration(): number {
  return sessionGeneration;
}

/** Fence pending account operations immediately, before any asynchronous cleanup. */
export function invalidateSession(): number {
  sessionAccessTokens.clear();
  return ++sessionGeneration;
}

/** Accept refresh-era tokens only while their original account session remains active. */
export function requireTokenSession(token: string): void {
  if (!sessionAccessTokens.has(token)) throw new SessionChangedError();
}

function withStorage<T>(operation: () => Promise<T>): Promise<T> {
  const pending = storageQueue.then(async () => {
    try {
      return await operation();
    } catch (error) {
      if (error instanceof AuthStorageError) throw error;
      throw new AuthStorageError();
    }
  });
  // A rejected operation belongs to its caller, but must not wedge later reads/clears.
  storageQueue = pending.then(() => undefined, () => undefined);
  return pending;
}

function parseTokenPair(value: string): TokenPair | null {
  let pair: unknown;
  try {
    pair = JSON.parse(value);
  } catch {
    throw new CorruptSessionError();
  }
  if (pair === null) return null;
  if (
    typeof pair !== "object" ||
    !("accessToken" in pair) ||
    typeof pair.accessToken !== "string" ||
    !pair.accessToken ||
    !("refreshToken" in pair) ||
    !(pair.refreshToken === null || (typeof pair.refreshToken === "string" && pair.refreshToken))
  ) {
    throw new CorruptSessionError();
  }
  return { accessToken: pair.accessToken, refreshToken: pair.refreshToken };
}

async function readTokenPair(generation: number): Promise<TokenPair | null> {
  const stored = await SecureStore.getItemAsync(SESSION_KEY);
  // A JSON null record is an authoritative sign-out.
  if (stored === null) return null;
  const pair = parseTokenPair(stored);
  if (pair && generation === sessionGeneration) sessionAccessTokens.add(pair.accessToken);
  return pair;
}

export function getToken(): Promise<string | null> {
  const generation = sessionGeneration;
  return withStorage(async () => (await readTokenPair(generation))?.accessToken ?? null);
}

export function getRefreshToken(): Promise<string | null> {
  const generation = sessionGeneration;
  return withStorage(async () => (await readTokenPair(generation))?.refreshToken ?? null);
}

/** One secure write preserves the access/refresh pair across partial failures. */
export function setTokenPair(
  accessToken: string,
  refreshToken: string,
  expectedGeneration = sessionGeneration,
): Promise<boolean> {
  return withStorage(async () => {
    if (expectedGeneration !== sessionGeneration) return false;
    if (!accessToken || !refreshToken) throw new AuthStorageError();
    await SecureStore.setItemAsync(SESSION_KEY, JSON.stringify({ accessToken, refreshToken }));
    if (expectedGeneration !== sessionGeneration) {
      // A superseded native write may already have reached disk. Remove it
      // inside this queue slot before any newer session write can begin.
      await SecureStore.setItemAsync(SESSION_KEY, "null");
      return false;
    }
    sessionAccessTokens.add(accessToken);
    return true;
  });
}

export function clearToken(): Promise<void> {
  invalidateSession();
  return withStorage(async () => {
    try {
      await SecureStore.setItemAsync(SESSION_KEY, "null");
    } catch {
      // Deletion can still work when a write is unavailable (for example a
      // full store). Only report success when the credential record is gone.
      await SecureStore.deleteItemAsync(SESSION_KEY);
    }
  });
}
