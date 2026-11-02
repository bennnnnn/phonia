import { useEffect, useMemo, useState } from "react";
import {
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type TextStyle,
  type ViewStyle,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import Animated, {
  cancelAnimation,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
} from "react-native-reanimated";

import { Motion, useReduceMotion } from "@/lib/motion";
import { useTheme, withAlpha } from "@/lib/theme";
import { makeActionShimmerStyles, SHIMMER_BAND_WIDTH } from "./actionShimmerStyles";

const DEFAULT_DELAY_MS = 220;
const SWEEP_MS = 1050;

export type ActionShimmerProps = {
  label: string;
  color?: string;
  delayMs?: number;
  compact?: boolean;
  style?: StyleProp<ViewStyle>;
  textStyle?: StyleProp<TextStyle>;
  testID?: string;
};

export default function ActionShimmerMotion({
  label,
  color,
  delayMs = DEFAULT_DELAY_MS,
  compact = false,
  style,
  textStyle,
  testID,
}: ActionShimmerProps) {
  const theme = useTheme();
  const reduceMotion = useReduceMotion();
  const s = useMemo(() => makeActionShimmerStyles(theme), [theme]);
  const [width, setWidth] = useState(0);
  const [sweepEnabled, setSweepEnabled] = useState(delayMs <= 0);
  const translateX = useSharedValue(-SHIMMER_BAND_WIDTH);
  const ink = color ?? theme.primary;

  useEffect(() => {
    if (delayMs <= 0) {
      setSweepEnabled(true);
      return;
    }
    setSweepEnabled(false);
    const timer = setTimeout(() => setSweepEnabled(true), delayMs);
    return () => clearTimeout(timer);
  }, [delayMs, label]);

  useEffect(() => {
    cancelAnimation(translateX);
    translateX.value = -SHIMMER_BAND_WIDTH;
    if (reduceMotion || !sweepEnabled || width <= 0) return;
    translateX.value = withRepeat(
      withTiming(width + SHIMMER_BAND_WIDTH, {
        duration: SWEEP_MS,
        easing: Motion.easing.inOut,
      }),
      -1,
      false,
    );
    return () => cancelAnimation(translateX);
  }, [reduceMotion, sweepEnabled, translateX, width]);

  const bandStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: translateX.value }],
  }));

  return (
    <View
      testID={testID}
      style={[s.wrap, compact && s.compact, style]}
      onLayout={(event) => setWidth(event.nativeEvent.layout.width)}
      accessibilityRole="progressbar"
      accessibilityLabel={label}
      accessibilityLiveRegion="polite"
    >
      {reduceMotion ? (
        <View
          testID={testID ? `${testID}-static` : undefined}
          style={[s.dot, { backgroundColor: ink }]}
        />
      ) : null}
      <Text style={[s.label, { color: ink }, textStyle]} numberOfLines={1}>
        {label}
      </Text>
      {sweepEnabled && !reduceMotion ? (
        <Animated.View pointerEvents="none" style={[s.band, bandStyle]}>
          <LinearGradient
            testID={testID ? `${testID}-band` : undefined}
            colors={["transparent", withAlpha(ink, 0.32), "transparent"]}
            start={{ x: 0, y: 0.5 }}
            end={{ x: 1, y: 0.5 }}
            style={StyleSheet.absoluteFill}
          />
        </Animated.View>
      ) : null}
    </View>
  );
}
