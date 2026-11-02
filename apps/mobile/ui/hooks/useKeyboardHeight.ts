import { useEffect, useState } from "react";
import { Keyboard, Platform } from "react-native";

/**
 * OS keyboard height via Keyboard events (works inside Modals; Android activity
 * resize does not). When `enabled` is false, height resets to 0.
 */
export function useKeyboardHeight(enabled = true): number {
  const [keyboardHeight, setKeyboardHeight] = useState(0);

  useEffect(() => {
    if (!enabled) {
      setKeyboardHeight(0);
      return;
    }
    const showEvent = Platform.OS === "ios" ? "keyboardWillShow" : "keyboardDidShow";
    const hideEvent = Platform.OS === "ios" ? "keyboardWillHide" : "keyboardDidHide";
    const showSub = Keyboard.addListener(showEvent, (e) => {
      setKeyboardHeight(Math.max(0, e.endCoordinates.height));
    });
    const hideSub = Keyboard.addListener(hideEvent, () => setKeyboardHeight(0));
    const metrics = Keyboard.metrics();
    if (metrics?.height) setKeyboardHeight(Math.max(0, metrics.height));
    return () => {
      showSub.remove();
      hideSub.remove();
    };
  }, [enabled]);

  return keyboardHeight;
}
