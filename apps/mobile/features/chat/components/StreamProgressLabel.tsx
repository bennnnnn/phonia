import { useEffect, useState } from "react";
import { type StyleProp, Text, type TextStyle } from "react-native";
import Animated, { useAnimatedStyle, useSharedValue, withTiming } from "react-native-reanimated";
import { useTranslation } from "react-i18next";

import { Motion, useReduceMotion } from "@/lib/motion";
import {
  isProgressStreamPhase,
  PROGRESS_LABEL_DELAY_MS,
  progressStreamLabel,
} from "@/lib/streamStatusLabel";

const AnimatedText = Animated.createAnimatedComponent(Text);
const SECOND_MS = 1000;

type Props = {
  /** The live `streamStatus` phase. */
  phase: string;
  /** When the phase began on this phone's clock (`StreamingDraft.statusStartedAt`). */
  startedAt?: number;
  style?: StyleProp<TextStyle>;
};

type Ticking = "never" | "once" | "every_second";

/**
 * Milliseconds since `startedAt`, re-read only when the label could change: at
 * the label delay ("once"), then on each whole second ("every_second").
 */
function useElapsedMs(startedAt: number, ticking: Ticking): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    const schedule = () => {
      const elapsed = Date.now() - startedAt;
      if (ticking === "never") return;
      if (ticking === "once" && elapsed >= PROGRESS_LABEL_DELAY_MS) return;
      const wait =
        elapsed < PROGRESS_LABEL_DELAY_MS
          ? PROGRESS_LABEL_DELAY_MS - elapsed
          : SECOND_MS - (elapsed % SECOND_MS);
      timer = setTimeout(() => {
        setNow(Date.now());
        schedule();
      }, wait);
    };
    setNow(Date.now());
    schedule();
    return () => {
      if (timer) clearTimeout(timer);
    };
  }, [startedAt, ticking]);
  return Math.max(0, now - startedAt);
}

function tickingFor(phase: string): Ticking {
  if (phase === "thinking") return "every_second";
  return isProgressStreamPhase(phase) ? "once" : "never";
}

/**
 * One quiet line naming real work: "Thinking… 12s" under the typing indicator,
 * "Checking the answer…" under a reply that has streamed but not yet saved.
 * Hidden for its first second so a quick step never flashes it, then faded in on
 * the UI thread. Only this line re-renders as the seconds tick, never the bubble
 * or the list around it.
 */
export function StreamProgressLabel({ phase, startedAt, style }: Props) {
  const { t } = useTranslation();
  const reduceMotion = useReduceMotion();
  const [mountedAt] = useState(() => Date.now());
  const elapsed = useElapsedMs(startedAt ?? mountedAt, tickingFor(phase));
  const label = progressStreamLabel(t, phase, elapsed);
  const visible = label !== null;
  // A label that names a step at once (not a timed one) needs no fade.
  const timed = isProgressStreamPhase(phase);
  const opacity = useSharedValue(timed ? 0 : 1);

  useEffect(() => {
    if (!visible) {
      opacity.value = 0;
      return;
    }
    opacity.value =
      reduceMotion || !timed ? 1 : withTiming(1, { duration: Motion.duration.snappy });
  }, [opacity, reduceMotion, timed, visible]);

  const fade = useAnimatedStyle(() => ({ opacity: opacity.value }));

  if (!label) return null;
  return (
    <AnimatedText style={[style, fade]} numberOfLines={1} testID={`stream-progress-${phase}`}>
      {label}
    </AnimatedText>
  );
}
