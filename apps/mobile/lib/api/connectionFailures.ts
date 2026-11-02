import { createListenerSet } from "@/lib/listenerSet";

/**
 * Requests that found no API. The connection check (hooks/useNetworkStatus.ts) ran on a
 * network change, a return to the app and while the banner showed, so an outage that began
 * with the app open went unseen: a read failed, no banner showed, and the list on screen was
 * not read again when the API came back (lib/reconnectRefresh.ts). The client
 * (lib/api/client.ts) reports each such failure here; the check coalesces them.
 */
const failures = createListenerSet();
/** Requests our API answered, by when each was sent. */
const answers = createListenerSet<[sentAt: number]>();

/** A request got no answer, or a 502, 503 or 504. */
export function reportConnectionFailure(): void {
  failures.emit();
}

/** `listener` on each failure; returns its unsubscribe. */
export function onConnectionFailure(listener: () => void): () => void {
  return failures.subscribe(listener);
}

/**
 * Our API answered a request sent at `sentAt` (a 2xx or 304; a socket's frame). While the
 * banner shows, one sent after the outage was seen says the API is back.
 */
export function reportConnectionAnswered(sentAt: number): void {
  answers.emit(sentAt);
}

/** `listener` on each answer, with when its request was sent; returns its unsubscribe. */
export function onConnectionAnswered(listener: (sentAt: number) => void): () => void {
  return answers.subscribe(listener);
}
