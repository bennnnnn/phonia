import { useEffect, useMemo, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import Animated, {
  cancelAnimation,
  useAnimatedStyle,
  useSharedValue,
  withDelay,
  withRepeat,
  withTiming,
} from "react-native-reanimated";

import { Motion, useReduceMotion } from "@/lib/motion";
import { Theme, useTheme, withAlpha } from "@/lib/theme";
import { Type } from "@/lib/type";

const BAND_WIDTH = 72;
const SWEEP_MS = 1500;
const PAUSE_MS = 500;

type Props = {
  label: string;
  /** Sweep a light band across the words (still while Reduce Motion is on). */
  shimmer: boolean;
  testID?: string;
};

/**
 * The short status line above the image-gen card ("Sketching it out").
 *
 * The shimmer is a band of the page color sliding over the text: on the page
 * it is invisible, over the letters it lightens them, so the light seems to
 * pass through the words. `ActionShimmer` tints its band with the ink, which
 * reads as a grey smear over grey text; this keeps the sweep to the glyphs.
 * Hidden from screen readers: the card's image label carries the same status.
 */
export function StageLine({ label, shimmer, testID }: Props) {
  const C = useTheme();
  const s = useMemo(() => makeStyles(C), [C]);
  const reduceMotion = useReduceMotion();
  const [width, setWidth] = useState(0);
  const x = useSharedValue(-BAND_WIDTH);
  const sweep = shimmer && !reduceMotion && width > 0;

  useEffect(() => {
    cancelAnimation(x);
    x.value = -BAND_WIDTH;
    if (!sweep) return;
    x.value = withRepeat(
      withDelay(
        PAUSE_MS,
        withTiming(width + BAND_WIDTH, { duration: SWEEP_MS, easing: Motion.easing.inOut }),
      ),
      -1,
      false,
    );
    return () => cancelAnimation(x);
  }, [sweep, width, x]);

  const bandStyle = useAnimatedStyle(() => ({ transform: [{ translateX: x.value }] }));

  return (
    <View
      style={s.wrap}
      onLayout={(event) => setWidth(event.nativeEvent.layout.width)}
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      testID={testID}
    >
      <Text style={s.label} numberOfLines={1}>
        {label}
      </Text>
      {sweep ? (
        <Animated.View pointerEvents="none" style={[s.band, bandStyle]}>
          <LinearGradient
            testID={testID ? `${testID}-shimmer` : undefined}
            colors={[withAlpha(C.bg, 0), withAlpha(C.bg, 0.78), withAlpha(C.bg, 0)]}
            start={{ x: 0, y: 0.5 }}
            end={{ x: 1, y: 0.5 }}
            style={StyleSheet.absoluteFill}
          />
        </Animated.View>
      ) : null}
    </View>
  );
}

function makeStyles(C: Theme) {
  return StyleSheet.create({
    wrap: {
      alignSelf: "flex-start",
      maxWidth: "100%",
      overflow: "hidden",
    },
    label: {
      ...Type.body,
      color: C.textSecondary,
    },
    band: {
      position: "absolute",
      top: 0,
      bottom: 0,
      left: 0,
      width: BAND_WIDTH,
    },
  });
}
