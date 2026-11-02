import { type SharedValue, useAnimatedStyle } from "react-native-reanimated";

/**
 * Raises a piece of bottom chrome by `lift` (pt) on every frame, on the UI
 * thread, so it rides the keyboard with the composer without a React render.
 * Apply the style only when there is a lift; without one it moves nothing.
 */
export function useBottomLiftStyle(lift?: SharedValue<number>) {
  return useAnimatedStyle(() => ({ transform: [{ translateY: lift ? -lift.value : 0 }] }), [lift]);
}
