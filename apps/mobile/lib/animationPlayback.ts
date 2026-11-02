/** Shared pause/resume arithmetic for native physics animations. */

function clampProgress(progress: number): number {
  if (!Number.isFinite(progress)) return 0;
  return Math.max(0, Math.min(1, progress));
}

/**
 * A paused animation resumes at its current frame. A completed animation is
 * the one exception: pressing Play after it finishes starts a fresh replay.
 */
export function playbackStart(progress: number): number {
  const current = clampProgress(progress);
  return current >= 1 ? 0 : current;
}

/** Keep resumed playback at the same speed instead of replaying slowly. */
export function remainingPlaybackDuration(totalMs: number, start: number): number {
  const duration = Number.isFinite(totalMs) ? Math.max(0, totalMs) : 0;
  return Math.max(1, Math.round(duration * (1 - clampProgress(start))));
}
