import { onAppStateChange } from "@/lib/foregroundRefresh";
import { createListenerSet } from "@/lib/listenerSet";

/**
 * What the phone reads again once the API answers after an outage. A read that failed while
 * "No internet" or "Can't reach Recall" showed was read again only on the next return from the
 * background: the banner cleared over a stale or empty list. The connection check
 * (hooks/useNetworkStatus.ts) now says when the API is back, and the list on screen, only that
 * one, is read again the way its screen reads it (its stale window still holds).
 *
 * The read waits a random 0–10 s: every phone the outage refused finds the API back within a
 * second or two of the others, and they must not all read again in the same second.
 */
const SPREAD_MS = 10_000;

/** The wait before the read, uniform over [0, 10 s). */
export function reconnectRefreshDelayMs(random: () => number = Math.random): number {
  return Math.floor(random() * SPREAD_MS);
}

const reconnected = createListenerSet();
const disconnected = createListenerSet();
/** When the connection check last failed (0: not in this run). */
let lostAt = 0;

/** The connection check passed after failing, with the app in the foreground. */
export function reportReconnected(): void {
  reconnected.emit();
}

/** The connection check failed: a read waiting for the API is called off. */
export function reportDisconnected(): void {
  lostAt = Date.now();
  disconnected.emit();
}

/**
 * When the connection was last lost: a read that landed since found the API back, and a
 * screen may count it as the read the API's return asks for.
 */
export function connectionLostAt(): number {
  return lostAt;
}

/**
 * A list read from the server at `readAt` (its cache's time, or the screen's own record) landed
 * after the connection was lost: it found the API back, and is the read its return asks for.
 */
export function readSinceLost(readAt: number | undefined): boolean {
  return readAt !== undefined && readAt > lostAt;
}

/**
 * Runs `refresh` once after each reconnect, `delayMs()` later, if `onScreen()` holds both when
 * the API comes back and when the wait ends. The wait is called off when the connection drops
 * again, the app goes to the background, or the returned stop is called (the screen lost focus).
 */
export function onReconnect(
  refresh: () => void,
  onScreen: () => boolean = () => true,
  delayMs: () => number = reconnectRefreshDelayMs,
): () => void {
  let cancelWait: (() => void) | null = null;
  const cancel = () => {
    cancelWait?.();
    cancelWait = null;
  };
  const stopReconnected = reconnected.subscribe(() => {
    cancel();
    if (!onScreen()) return;
    const timer = setTimeout(() => {
      cancel();
      if (onScreen()) refresh();
    }, delayMs());
    const stopAppState = onAppStateChange((state) => {
      if (state === "background") cancel();
    });
    cancelWait = () => {
      clearTimeout(timer);
      stopAppState();
    };
  });
  const stopDisconnected = disconnected.subscribe(cancel);
  return () => {
    cancel();
    stopReconnected();
    stopDisconnected();
  };
}
