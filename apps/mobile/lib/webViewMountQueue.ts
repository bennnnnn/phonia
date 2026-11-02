/**
 * Module-level slot queue that gates how many WebView-based rich blocks
 * (chart/vega, mermaid diagrams, heavy multi-line math) may mount at the
 * same time.
 *
 * FlashList already virtualizes at the message-row level (off-screen rows
 * unmount), but a single *visible* assistant reply can contain several rich
 * fences — each one mounting its own `react-native-webview` instance the
 * moment the row renders. Charts and mermaid diagrams each independently
 * fetch 1MB+ of JS from a CDN, and even math (no CDN fetch) pays a WebView
 * shell native-memory cost — so N fences in one message means N simultaneous
 * mounts/fetches in the same frame. This queue staggers that: callers
 * request a ticket, wait for it to be granted (subscribe), and release it
 * once their WebView has loaded (or unmounts before loading), freeing the
 * slot for the next waiter.
 *
 * Kept framework-free (no React) so the allocation logic is unit-testable
 * without rendering anything — see hooks/useDeferredWebViewMount.ts for the
 * React wrapper that consuming components actually use. Pattern mirrors
 * features/chat/model/streamingDraftStore.ts: private module-level state + a listeners set
 * that gets notified on every change.
 */

export const MAX_CONCURRENT_WEBVIEW_MOUNTS = 2;

export type MountTicket = number;

type Listener = () => void;

let nextTicketId = 1;
const grantedTickets = new Set<MountTicket>();
const waitQueue: MountTicket[] = [];
const listeners = new Set<Listener>();

function notify(): void {
  listeners.forEach((listener) => listener());
}

function fillSlots(): void {
  while (grantedTickets.size < MAX_CONCURRENT_WEBVIEW_MOUNTS && waitQueue.length > 0) {
    const next = waitQueue.shift();
    if (next != null) grantedTickets.add(next);
  }
}

/**
 * Request a mount slot. Always returns a ticket immediately — check
 * {@link isMountGranted} (or subscribe via {@link subscribeMountQueue}) to
 * know whether it has actually been granted yet.
 */
export function requestMountTicket(): MountTicket {
  const ticket = nextTicketId++;
  waitQueue.push(ticket);
  fillSlots();
  notify();
  return ticket;
}

/**
 * Release a ticket — granted or still waiting — and promote the next
 * waiter into any freed slot. Safe to call more than once for the same
 * ticket (a second call is a no-op).
 */
export function releaseMountTicket(ticket: MountTicket): void {
  const wasGranted = grantedTickets.delete(ticket);
  const queueIndex = waitQueue.indexOf(ticket);
  if (queueIndex !== -1) waitQueue.splice(queueIndex, 1);
  if (wasGranted) fillSlots();
  notify();
}

export function isMountGranted(ticket: MountTicket): boolean {
  return grantedTickets.has(ticket);
}

export function subscribeMountQueue(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Test-only: reset all state between test cases. */
export function resetWebViewMountQueue(): void {
  grantedTickets.clear();
  waitQueue.length = 0;
  nextTicketId = 1;
}
