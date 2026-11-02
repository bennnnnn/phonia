/** First wait after a socket failure; each failure in a row doubles it, up to the cap. */
export const WS_RETRY_BASE_MS = 10_000;
export const WS_RETRY_MAX_MS = 5 * 60_000;

/**
 * When a chat send may try the WebSocket again after it failed (a handshake
 * that timed out, an abnormal close, a dead or silent socket). SSE carries the
 * sends meanwhile; a turn the socket completes clears the wait. A chat used to
 * stay on SSE for good after one failure.
 */
export type WsBackoff = {
  fail(): void;
  succeed(): void;
  /** True while sends should skip the socket. */
  cooling(): boolean;
};

export function createWsBackoff(now: () => number = Date.now): WsBackoff {
  let failures = 0;
  let retryAt = 0;
  return {
    fail() {
      retryAt = now() + Math.min(WS_RETRY_BASE_MS * 2 ** failures, WS_RETRY_MAX_MS);
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
