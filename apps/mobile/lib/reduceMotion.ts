import { useEffect, useState } from "react";
import { AccessibilityInfo } from "react-native";

/**
 * The last value the OS reported, shared by every subscriber.
 *
 * Reading the setting is async, so a component mounted before the first
 * answer would otherwise start from a guess. Once any screen has asked, every
 * later mount starts from the real value.
 */
let knownReduceMotion: boolean | null = null;

/**
 * The OS Reduce Motion setting, or `null` until it is known.
 *
 * Use this where acting on a guess is visible: a scene that autoplays on
 * `false` and is then told `true` has already moved, and freezes a few frames
 * in. Wait for a boolean before starting motion the user did not ask for.
 */
export function useReduceMotionSetting(): boolean | null {
  const [reduceMotion, setReduceMotion] = useState<boolean | null>(knownReduceMotion);

  useEffect(() => {
    let mounted = true;
    const update = (enabled: boolean) => {
      knownReduceMotion = enabled;
      if (mounted) setReduceMotion(enabled);
    };
    void AccessibilityInfo.isReduceMotionEnabled().then(update, () => update(false));
    const sub = AccessibilityInfo.addEventListener("reduceMotionChanged", update);
    return () => {
      mounted = false;
      sub.remove();
    };
  }, []);

  return reduceMotion;
}

/** Subscribe to the OS Reduce Motion setting; `false` until it is known. */
export function useReduceMotion(): boolean {
  return useReduceMotionSetting() ?? false;
}
