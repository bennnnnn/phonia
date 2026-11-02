/* eslint-disable react-hooks/immutability -- Reanimated shared values are mutated on the UI thread by design */
/**
 * Play, pause and replay for a figure that walks sampled motion
 * (`SimulationBlock`, `TrajectoryChart`): one UI-thread clock from 0 to 1.
 */
import { useCallback, useEffect, useState } from "react";
import {
  cancelAnimation,
  runOnJS,
  useSharedValue,
  withRepeat,
  withSequence,
  withTiming,
  type SharedValue,
} from "react-native-reanimated";

import { playbackStart, remainingPlaybackDuration } from "@/lib/animationPlayback";
import { Motion, useReduceMotionSetting } from "@/lib/motion";

/**
 * Laps a looping figure runs after the first, then it rests on Play. Looping for ever,
 * an orbit or a wave redrew its canvas every frame for as long as the chat stayed
 * mounted, seen or not: under Settings, or scrolled just out of view.
 */
export const LOOP_LAPS = 3;

type Options = {
  /** One pass, start to end, in ms. */
  duration: number;
  /** Whether anything moves at all; a still figure never plays. */
  animated: boolean;
  /** Start by itself — only once Reduce Motion is known to be off. */
  autoplay: boolean;
  /**
   * Go round again while playing, for periodic motion (an orbit, a spring),
   * instead of holding the end state. Never under Reduce Motion: a user who
   * asks for one pass gets one pass.
   */
  loop: boolean;
  /**
   * The content being shown. A recycled list cell can keep this hook's state
   * while showing a different figure, so a new key rewinds and stops.
   */
  resetKey: string;
};

type Playback = {
  progress: SharedValue<number>;
  isPlaying: boolean;
  play: () => void;
  pause: () => void;
  /** The OS setting, `null` while it is still being read. */
  reduceMotion: boolean | null;
};

export function usePlayback({ duration, animated, autoplay, loop, resetKey }: Options): Playback {
  const progress = useSharedValue(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const reduceMotion = useReduceMotionSetting();
  const repeat = loop && reduceMotion === false;

  const markStopped = useCallback(() => setIsPlaying(false), []);
  const play = useCallback(() => {
    cancelAnimation(progress);
    const start = playbackStart(progress.value);
    progress.value = start;
    setIsPlaying(true);
    const easing = Motion.easing.linear;
    const rest = remainingPlaybackDuration(duration, start);
    if (repeat) {
      // Finish this lap from where it was paused, then go round from the top.
      progress.value = withSequence(
        withTiming(1, { duration: rest, easing }),
        withRepeat(
          withSequence(withTiming(0, { duration: 0 }), withTiming(1, { duration, easing })),
          LOOP_LAPS,
          false,
          (finished) => {
            if (finished) runOnJS(markStopped)();
          },
        ),
      );
      return;
    }
    progress.value = withTiming(1, { duration: rest, easing }, (finished) => {
      if (finished) runOnJS(markStopped)();
    });
  }, [duration, markStopped, progress, repeat]);

  const pause = useCallback(() => {
    cancelAnimation(progress);
    setIsPlaying(false);
  }, [progress]);

  useEffect(() => {
    cancelAnimation(progress);
    progress.value = 0;
    setIsPlaying(false);
    // `null` is "not known yet": starting on a guess and stopping a few frames
    // later is exactly the motion a Reduce Motion user asked not to see.
    if (!animated || !autoplay || reduceMotion !== false) return;
    play();
    return () => cancelAnimation(progress);
  }, [animated, autoplay, play, progress, reduceMotion, resetKey]);

  return { progress, isPlaying, play, pause, reduceMotion };
}
