/**
 * Shared cadence for stream-time UI work (markdown parse, assistant fence
 * derive). Draft still coalesces on rAF (~60fps); these consumers flush at
 * ~30fps so text appears fluidly without running heavy strip/parse every frame.
 */
export const STREAM_UI_INTERVAL_MS = 32;

/** Remaining wait for a throttle flush; 0 means flush now. */
export function nextStreamUiFlushDelay(
  elapsedMs: number,
  intervalMs: number = STREAM_UI_INTERVAL_MS,
): number {
  return Math.max(0, intervalMs - elapsedMs);
}
