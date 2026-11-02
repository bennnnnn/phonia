import type { RealtimeTimer, RealtimeTurnEvent } from "@/features/speech/model/realtimeTurnState";

type RealtimeMicGate = {
  setMic: (enabled: boolean) => void;
  /** Replaces a pending timer of the same name; `then` goes to onElapsed when it fires. */
  start: (timer: RealtimeTimer, ms: number, then: RealtimeTurnEvent) => void;
  clear: (timer: RealtimeTimer) => void;
  clearAll: () => void;
};

/**
 * The local mic tracks and the two timers that hold input shut: the warmup
 * after connect (session_ready) and the playback tail (mic_resume).
 */
export function createRealtimeMicGate(
  tracks: readonly { enabled: boolean }[],
  onElapsed: (event: RealtimeTurnEvent) => void,
): RealtimeMicGate {
  const timers = new Map<RealtimeTimer, ReturnType<typeof setTimeout>>();
  const clear = (timer: RealtimeTimer) => {
    const handle = timers.get(timer);
    if (handle == null) return;
    clearTimeout(handle);
    timers.delete(timer);
  };
  return {
    setMic: (enabled) => {
      for (const track of tracks) {
        try {
          track.enabled = enabled;
        } catch {
          /* best-effort */
        }
      }
    },
    start: (timer, ms, then) => {
      clear(timer);
      timers.set(
        timer,
        setTimeout(() => {
          timers.delete(timer);
          onElapsed(then);
        }, ms),
      );
    },
    clear,
    clearAll: () => {
      clear("mic_resume");
      clear("session_ready");
    },
  };
}
