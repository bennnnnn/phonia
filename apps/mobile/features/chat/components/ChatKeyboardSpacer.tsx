import Animated, { type SharedValue, useAnimatedStyle } from "react-native-reanimated";

/**
 * Room under the last message for the keyboard. It grows and shrinks with
 * every frame of the keyboard on the UI thread, so the thread can scroll clear
 * of the raised composer without the chat screen rendering for each step.
 */
export function ChatKeyboardSpacer({ lift }: { lift: SharedValue<number> }) {
  const style = useAnimatedStyle(() => ({ height: lift.value }));
  return <Animated.View style={style} pointerEvents="none" testID="chat-keyboard-spacer" />;
}
