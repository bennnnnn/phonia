/**
 * Max wait for the WebSocket handshake before sends go over SSE.
 * A healthy socket should open well inside this budget; a proxy/network path
 * that silently drops WS must not add a multi-second penalty before SSE.
 */
export const WS_CONNECT_TIMEOUT_MS = 900;

/**
 * Start the eager socket almost immediately after a chat becomes active so
 * navigation/typing time hides the handshake, while keeping a small debounce
 * to avoid opening a socket for every row during a fast list fling.
 */
export const EAGER_CONNECT_DEBOUNCE_MS = 100;

/** Server sends start before turn preparation. This bounds an OPEN but silent
 * connection without imposing a deadline on acknowledged model/tool work. */
export const WS_FIRST_EVENT_TIMEOUT_MS = 30_000;

/** The server answers a send with `start` at once; this long without it, the
 * socket is probed instead of waiting out the first-event deadline. */
export const WS_ACK_PROBE_MS = 3_000;

/** A probe's ping unanswered this long: the socket is dead (often half-open
 * after a Wi-Fi/cellular switch) and the send is replayed. */
export const WS_PROBE_TIMEOUT_MS = 3_000;

/** A saved reply's follow-up questions come on its socket after `done` (the
 * server gives their model call 6 s): a socket being replaced waits this long. */
export const WS_FOLLOW_UPS_WAIT_MS = 10_000;

/**
 * Once a turn's stream has started (socket or SSE), the longest it may go with
 * nothing. A quiet turn sends a `keepalive` every 15 s, so a longer silence is a
 * dead connection: the phone gives up on the stream and reloads the chat for the
 * reply the server saves (code-health audit NET-17).
 */
export const STREAM_IDLE_TIMEOUT_MS = 45_000;
