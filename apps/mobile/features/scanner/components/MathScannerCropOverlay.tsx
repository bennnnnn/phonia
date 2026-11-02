import { type ComponentProps, useEffect, useMemo, useState } from "react";
import { type AccessibilityActionEvent, StyleSheet, View } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { GestureDetector } from "react-native-gesture-handler";
import Animated, {
  cancelAnimation,
  type AnimatedStyle,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
} from "react-native-reanimated";
import { useTranslation } from "react-i18next";

import { Radius } from "@/lib/radius";
import { shadowElevated } from "@/lib/shadow";
import { Motion, useReduceMotion } from "@/lib/motion";
import { Theme, useTheme, withAlpha } from "@/lib/theme";

type AnimStyle = AnimatedStyle<Record<string, unknown>>;
type DetectorGesture = ComponentProps<typeof GestureDetector>["gesture"];

export type LiveScanFrameStatus = "idle" | "detecting" | "ready";

type Props = {
  regionGesture: DetectorGesture;
  cornerTL: DetectorGesture;
  cornerTR: DetectorGesture;
  cornerBL: DetectorGesture;
  cornerBR: DetectorGesture;
  regionStyle: AnimStyle;
  maskTopStyle: AnimStyle;
  maskBottomStyle: AnimStyle;
  maskLeftStyle: AnimStyle;
  maskRightStyle: AnimStyle;
  handleTLStyle: AnimStyle;
  handleTRStyle: AnimStyle;
  handleBLStyle: AnimStyle;
  handleBRStyle: AnimStyle;
  scanning: boolean;
  liveStatus?: LiveScanFrameStatus;
  onGrow: () => void;
  onShrink: () => void;
};

export function MathScannerCropOverlay({
  regionGesture,
  cornerTL,
  cornerTR,
  cornerBL,
  cornerBR,
  regionStyle,
  maskTopStyle,
  maskBottomStyle,
  maskLeftStyle,
  maskRightStyle,
  handleTLStyle,
  handleTRStyle,
  handleBLStyle,
  handleBRStyle,
  scanning,
  liveStatus = "idle",
  onGrow,
  onShrink,
}: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const reduceMotion = useReduceMotion();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const [regionHeight, setRegionHeight] = useState(0);
  const shimmerProgress = useSharedValue(0);

  useEffect(() => {
    cancelAnimation(shimmerProgress);
    shimmerProgress.value = 0;
    if (!scanning || reduceMotion || regionHeight <= 0) return;
    shimmerProgress.value = withRepeat(
      withTiming(1, { duration: 1850, easing: Motion.easing.linear }),
      -1,
      false,
    );
    return () => cancelAnimation(shimmerProgress);
  }, [reduceMotion, regionHeight, scanning, shimmerProgress]);

  const shimmerStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: -18 + shimmerProgress.value * (regionHeight + 36) }],
  }));

  const onA11yAction = (event: AccessibilityActionEvent) => {
    if (event.nativeEvent.actionName === "increment") onGrow();
    if (event.nativeEvent.actionName === "decrement") onShrink();
  };

  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="box-none">
      <View style={s.maskLayer} pointerEvents="none">
        <Animated.View style={[s.mask, s.maskTop, maskTopStyle]} />
        <Animated.View style={[s.mask, s.maskBottom, maskBottomStyle]} />
        <Animated.View style={[s.mask, s.maskSide, maskLeftStyle]} />
        <Animated.View style={[s.mask, s.maskSide, maskRightStyle]} />
      </View>
      <GestureDetector gesture={regionGesture}>
        <Animated.View
          testID={`math-scanner-frame-${liveStatus}`}
          style={[
            s.region,
            liveStatus === "detecting" ? s.regionDetecting : null,
            liveStatus === "ready" ? s.regionReady : null,
            regionStyle,
          ]}
          collapsable={false}
          accessible
          accessibilityRole="adjustable"
          accessibilityLabel={t("chat.math_scan_frame_a11y")}
          accessibilityActions={[
            { name: "increment", label: t("chat.math_scan_frame_grow") },
            { name: "decrement", label: t("chat.math_scan_frame_shrink") },
          ]}
          onAccessibilityAction={onA11yAction}
          onLayout={(event) => setRegionHeight(event.nativeEvent.layout.height)}
        >
          {scanning ? (
            <View style={s.shimmerClip} pointerEvents="none">
              <Animated.View
                testID="math-scanner-shimmer"
                style={[s.shimmerBand, reduceMotion ? s.shimmerStatic : shimmerStyle]}
              >
                <LinearGradient
                  colors={[
                    "transparent",
                    withAlpha(theme.primary, 0.22),
                    withAlpha(theme.primary, 0.82),
                    withAlpha(theme.primary, 0.22),
                    "transparent",
                  ]}
                  locations={[0, 0.28, 0.5, 0.72, 1]}
                  start={{ x: 0, y: 0.5 }}
                  end={{ x: 1, y: 0.5 }}
                  style={StyleSheet.absoluteFill}
                />
              </Animated.View>
            </View>
          ) : null}
          <View style={s.cornerTL} />
          <View style={s.cornerTR} />
          <View style={s.cornerBL} />
          <View style={s.cornerBR} />
        </Animated.View>
      </GestureDetector>
      <GestureDetector gesture={cornerTL}>
        <Animated.View style={[s.handle, handleTLStyle]} accessible={false} />
      </GestureDetector>
      <GestureDetector gesture={cornerTR}>
        <Animated.View style={[s.handle, handleTRStyle]} accessible={false} />
      </GestureDetector>
      <GestureDetector gesture={cornerBL}>
        <Animated.View style={[s.handle, handleBLStyle]} accessible={false} />
      </GestureDetector>
      <GestureDetector gesture={cornerBR}>
        <Animated.View style={[s.handle, handleBRStyle]} accessible={false} />
      </GestureDetector>
    </View>
  );
}

function makeStyles(theme: Theme) {
  const corner = {
    position: "absolute" as const,
    width: 24,
    height: 24,
    borderColor: theme.primary,
  };
  return StyleSheet.create({
    maskLayer: {
      ...StyleSheet.absoluteFill,
    },
    mask: {
      position: "absolute",
      backgroundColor: theme.scrim,
    },
    maskTop: {
      top: 0,
      left: 0,
      right: 0,
    },
    maskBottom: {
      left: 0,
      right: 0,
      bottom: 0,
    },
    maskSide: {
      left: 0,
    },
    region: {
      position: "absolute",
      borderColor: withAlpha(theme.onMedia, 0.95),
      borderWidth: 2,
      borderRadius: Radius.sm,
      backgroundColor: "transparent",
      zIndex: 4,
      ...shadowElevated(theme, "fab"),
    },
    regionDetecting: {
      borderColor: withAlpha(theme.primary, 0.72),
    },
    regionReady: {
      borderColor: theme.primary,
      borderWidth: 3,
    },
    shimmerClip: {
      ...StyleSheet.absoluteFill,
      overflow: "hidden",
      borderRadius: Radius.sm,
    },
    shimmerBand: {
      position: "absolute",
      left: 0,
      right: 0,
      top: 0,
      height: 18,
    },
    shimmerStatic: {
      top: "50%",
      opacity: 0.42,
      transform: [{ translateY: -9 }],
    },
    handle: {
      position: "absolute",
      zIndex: 8,
    },
    cornerTL: { ...corner, top: -2, left: -2, borderTopWidth: 3, borderLeftWidth: 3, borderTopLeftRadius: Radius.xs },
    cornerTR: { ...corner, top: -2, right: -2, borderTopWidth: 3, borderRightWidth: 3, borderTopRightRadius: Radius.xs },
    cornerBL: { ...corner, bottom: -2, left: -2, borderBottomWidth: 3, borderLeftWidth: 3, borderBottomLeftRadius: Radius.xs },
    cornerBR: { ...corner, bottom: -2, right: -2, borderBottomWidth: 3, borderRightWidth: 3, borderBottomRightRadius: Radius.xs },
  });
}
