import { Platform } from "react-native";

/** Shared native-stack transition presets for expo-router screens. */

type StackTransitionPreset = {
  animation?:
    | "default"
    | "fade"
    | "fade_from_bottom"
    | "slide_from_right"
    | "slide_from_bottom"
    | "none";
  gestureEnabled?: boolean;
  fullScreenGestureEnabled?: boolean;
  animationDuration?: number;
};

function withoutMotion(base: StackTransitionPreset): StackTransitionPreset {
  return { ...base, animation: "none", animationDuration: 0 };
}

/** Hierarchical push (settings drill-down, memory, todos). */
export function stackPushTransition(reduceMotion = false): StackTransitionPreset {
  const preset: StackTransitionPreset = {
    animation: Platform.OS === "ios" ? "default" : "slide_from_right",
    gestureEnabled: true,
    fullScreenGestureEnabled: Platform.OS === "ios",
    ...(Platform.OS === "ios" ? {} : { animationDuration: 210 }),
  };
  return reduceMotion ? withoutMotion(preset) : preset;
}

/** Utility screens opened from the drawer / home (slight lift). */
export function stackUtilityTransition(reduceMotion = false): StackTransitionPreset {
  const preset: StackTransitionPreset = {
    animation: "fade_from_bottom",
    gestureEnabled: true,
    fullScreenGestureEnabled: Platform.OS === "ios",
    animationDuration: 230,
  };
  return reduceMotion ? withoutMotion(preset) : preset;
}

/** Onboarding and login — soft cross-fade instead of a hard slide. */
export function stackAuthTransition(reduceMotion = false): StackTransitionPreset {
  const preset: StackTransitionPreset = {
    animation: "fade",
    gestureEnabled: false,
    animationDuration: 210,
  };
  return reduceMotion ? withoutMotion(preset) : preset;
}

/** Chat home — avoid animating the primary surface on cold start / redirects. */
export function stackHomeTransition(): StackTransitionPreset {
  return {
    animation: "none",
    gestureEnabled: false,
  };
}
