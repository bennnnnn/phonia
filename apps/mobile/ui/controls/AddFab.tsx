import { useEffect } from "react";
import { Platform, Pressable, StyleSheet, View } from "react-native";
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withDelay,
  withRepeat,
  withTiming,
} from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Icon } from "../icons/Icon";
import { useKeyboardHeight } from "../hooks/useKeyboardHeight";
import { tap } from "@/lib/haptics";
import { useReduceMotion } from "@/lib/motion";
import { Radius } from "@/lib/radius";
import { shadowElevated } from "@/lib/shadow";
import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";
import { IconSize } from "../icons/sizes";
import { FAB_SIZE, fabBottom } from "./addFabLayout";

const WAVE_MS = 1800;
/** Rings a visit shows, then the button rests: pulsing for ever kept the To-do screen
 * redrawing every frame while it sat open (and kept a ProMotion screen at full rate). */
const WAVE_PULSES = 3;

type Props = {
  onPress: () => void;
  accessibilityLabel: string;
  /** Soft expanding rings, used on the To-do add button. */
  wave?: boolean;
};

/** Bottom-right + FAB for Add reminder. */
export function AddFab({ onPress, accessibilityLabel, wave = false }: Props) {
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const keyboardHeight = useKeyboardHeight(true);
  const s = makeStyles(theme);
  // Android activity resize already shrinks the window — only lift on iOS.
  const keyboardLift = Platform.OS === "ios" ? keyboardHeight : 0;
  const bottom = fabBottom(insets.bottom) + keyboardLift;

  return (
    <View
      pointerEvents="box-none"
      style={[s.slot, { bottom, right: Space.md + insets.right }]}
    >
      {wave ? <FabWave color={theme.primary} /> : null}
      <Pressable
        onPress={() => {
          tap();
          onPress();
        }}
        accessibilityRole="button"
        accessibilityLabel={accessibilityLabel}
        style={s.btn}
      >
        <Icon name="plus" size={IconSize.lg} color={theme.onPrimary} />
      </Pressable>
    </View>
  );
}

function FabWave({ color }: { color: string }) {
  const reduceMotion = useReduceMotion();
  const first = useSharedValue(0);
  const second = useSharedValue(0);

  useEffect(() => {
    if (reduceMotion) return;
    const pulse = () =>
      withRepeat(
        withTiming(1, { duration: WAVE_MS, easing: Easing.out(Easing.ease) }),
        WAVE_PULSES,
        false,
      );
    first.value = pulse();
    second.value = withDelay(WAVE_MS / 2, pulse());
  }, [first, reduceMotion, second]);

  const lead = useAnimatedStyle(() => ({
    opacity: reduceMotion ? 0 : 0.35 * (1 - first.value),
    transform: [{ scale: 1 + first.value * 0.85 }],
  }));
  const trail = useAnimatedStyle(() => ({
    opacity: reduceMotion ? 0 : 0.35 * (1 - second.value),
    transform: [{ scale: 1 + second.value * 0.85 }],
  }));

  if (reduceMotion) return null;

  return (
    <>
      <Animated.View pointerEvents="none" style={[waveRing(color), lead]} />
      <Animated.View pointerEvents="none" style={[waveRing(color), trail]} />
    </>
  );
}

function waveRing(color: string) {
  return {
    position: "absolute" as const,
    width: FAB_SIZE,
    height: FAB_SIZE,
    borderRadius: Radius.full,
    borderWidth: 2,
    borderColor: color,
  };
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    slot: {
      position: "absolute",
      zIndex: 20,
      width: FAB_SIZE,
      height: FAB_SIZE,
      alignItems: "center",
      justifyContent: "center",
    },
    btn: {
      width: FAB_SIZE,
      height: FAB_SIZE,
      borderRadius: Radius.full,
      backgroundColor: theme.primary,
      alignItems: "center",
      justifyContent: "center",
      ...shadowElevated(theme, "fab"),
    },
  });
}
