/* eslint-disable react-hooks/immutability -- Reanimated shared values mutate `.value` in gestures. */
import { useMemo } from "react";
import { Gesture } from "react-native-gesture-handler";
import {
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
} from "react-native-reanimated";

const DISMISS_DY = 96;
const DISMISS_VY = 900;
const PAN_SPRING = { damping: 28, stiffness: 280, overshootClamping: true } as const;

/** Handle-only pan-down dismiss for bottom Sheets (Reanimated shared values). */
export function useSheetPanDismiss(
  enabled: boolean,
  reduceMotion: boolean,
  onClose: () => void,
) {
  const translateY = useSharedValue(0);

  const pan = useMemo(
    () =>
      Gesture.Pan()
        .enabled(enabled)
        // One finger drags down; two belong to a pinch-zoom inside (photo viewer).
        .maxPointers(1)
        .activeOffsetY(12)
        .failOffsetX([-32, 32])
        .onUpdate((e) => {
          translateY.value = Math.max(0, e.translationY);
        })
        .onEnd((e) => {
          const shouldClose = e.translationY > DISMISS_DY || e.velocityY > DISMISS_VY;
          if (shouldClose) {
            translateY.value = 0;
            runOnJS(onClose)();
            return;
          }
          translateY.value = reduceMotion ? 0 : withSpring(0, PAN_SPRING);
        }),
    [enabled, onClose, reduceMotion, translateY],
  );

  const panStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: translateY.value }],
  }));

  return { pan, panStyle, translateY };
}
