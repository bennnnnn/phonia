/** First wait after a socket failure; each failure in a row doubles it, up to the cap. */
export const WS_RETRY_BASE_MS = 10_000;
export const WS_RETRY_MAX_MS = 5 * 60_000;
/**
 * First wait when the failure is a handshake that did not finish in time and nothing
 * failed before it. A slow cellular path can miss the handshake budget once without the
 * socket being broken, so a send soon after tries it again; a second failure in a row
 * waits as any other does.
 */
export const WS_CONNECT_TIMEOUT_RETRY_MS = 3_000;

/** A handshake that ran out of time, or any other socket failure. */
export type WsFailure = "connect_timeout" | "socket";

/**
 * When a chat send may try the WebSocket again after it failed (a handshake
 * that timed out, an abnormal close, a dead or silent socket). SSE carries the
 * sends meanwhile; a turn the socket completes clears the wait. A chat used to
 * stay on SSE for good after one failure.
 */
export type WsBackoff = {
  fail(kind?: WsFailure): void;
  succeed(): void;
  /** True while sends should skip the socket. */
  cooling(): boolean;
};

export function createWsBackoff(now: () => number = Date.now): WsBackoff {
  let failures = 0;
  let retryAt = 0;
  return {
    fail(kind: WsFailure = "socket") {
      const wait =
        kind === "connect_timeout" && failures === 0
          ? WS_CONNECT_TIMEOUT_RETRY_MS
          : Math.min(WS_RETRY_BASE_MS * 2 ** failures, WS_RETRY_MAX_MS);
      retryAt = now() + wait;
      failures += 1;
    },
    succeed() {
      failures = 0;
      retryAt = 0;
    },
    cooling() {
      return now() < retryAt;
    },
  };
}
