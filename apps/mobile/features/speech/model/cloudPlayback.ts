/** How often the player reports its status; the end of a clip shows within this. */
export const PLAYBACK_STATUS_MS = 100;
/** The backstop poll for a missed end event (at 50 ms it woke the app 40 times a second). */
export const PLAYBACK_POLL_MS = 500;

export function playbackStatusFinished(status: {
  didJustFinish?: boolean;
  currentTime?: number;
  duration?: number;
  playing?: boolean;
  sawPlaying?: boolean;
}): boolean {
  if (status.didJustFinish) return true;
  if (status.sawPlaying && status.playing === false) return true;
  const duration = status.duration ?? 0;
  const current = status.currentTime ?? 0;
  return duration > 0 && current >= duration - 0.04;
}

/** Read-aloud speed (Settings → Voice); the voice keeps its pitch. */
export function applySpeechRate(
  player: {
    shouldCorrectPitch?: boolean;
    setPlaybackRate?: (
      rate: number,
      quality?: "low" | "medium" | "high",
    ) => void;
  },
  rate: number,
): void {
  if (rate === 1) return;
  try {
    player.shouldCorrectPitch = true;
    player.setPlaybackRate?.(rate, "high");
  } catch {
    /* plays at normal speed */
  }
}
