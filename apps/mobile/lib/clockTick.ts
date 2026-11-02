/**
 * Shared once-per-second tick broadcaster.
 *
 * `CircularClockBlock` fences render inside a FlashList, which over-renders a
 * bit beyond the visible viewport (`drawDistance`). Before this module, each
 * mounted clock ran its own `setInterval`, so N clocks off-screen meant N
 * independent timers ticking forever until FlashList unmounted the row. This
 * module runs exactly one interval — reference-counted so it starts on the
 * first subscriber and stops once the last one unsubscribes — and fans the
 * tick out to every subscriber. Same house pattern as
 * `features/chat/model/streamingDraftStore.ts`: module-level state + a `Set<Listener>` +
 * subscribe/publish.
 */

type ClockTickListener = () => void;

const TICK_INTERVAL_MS = 1000;

const listeners = new Set<ClockTickListener>();
let intervalId: ReturnType<typeof setInterval> | null = null;

function broadcastTick(): void {
  listeners.forEach((listener) => listener());
}

function ensureIntervalStarted(): void {
  if (intervalId != null) return;
  intervalId = setInterval(broadcastTick, TICK_INTERVAL_MS);
}

function stopIntervalIfNoSubscribers(): void {
  if (listeners.size > 0) return;
  if (intervalId == null) return;
  clearInterval(intervalId);
  intervalId = null;
}

/**
 * Subscribe to the shared once-per-second tick. The underlying interval is
 * created lazily on the first subscriber and cleared once the last
 * subscriber unsubscribes — call the returned function on unmount.
 */
export function subscribeClockTick(listener: ClockTickListener): () => void {
  listeners.add(listener);
  ensureIntervalStarted();

  return () => {
    listeners.delete(listener);
    stopIntervalIfNoSubscribers();
  };
}
