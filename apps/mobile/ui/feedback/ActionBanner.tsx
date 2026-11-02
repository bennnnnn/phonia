import { useEffect, useMemo, useRef } from "react";
import { Pressable, StyleSheet, Text } from "react-native";
import Animated, {
  runOnJS,
  type SharedValue,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  withTiming,
} from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Icon } from "../icons/Icon";
import { ACTION_BANNER_MS } from "@/lib/feedbackTiming";
import type { IconName } from "../icons/names";
import { Layer } from "@/lib/layer";
import { Motion, useReduceMotion } from "@/lib/motion";
import { Radius } from "@/lib/radius";
import { shadowElevated } from "@/lib/shadow";
import { Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";
import { Space } from "@/lib/space";
import { IconSize } from "../icons/sizes";
import { useBottomLiftStyle } from "../hooks/useBottomLiftStyle";
import { useLiveAnnouncement } from "../hooks/useLiveAnnouncement";

type Props = {
  message: string | null;
  icon?: IconName;
  tone?: ActionFeedbackTone;
  /** `media`: a white pill with black ink, for a toast over a photo viewer's black stage. */
  appearance?: ActionBannerAppearance;
  onDismiss: () => void;
  bottomOffset?: number;
  /** Moves the toast up by this much (pt) on the UI thread, e.g. with a keyboard-lifted composer. */
  lift?: SharedValue<number>;
};

type ActionFeedbackTone = "success" | "info" | "warning" | "error";
export type ActionBannerAppearance = "default" | "media";

export function ActionBanner({
  message,
  icon = "check-circle-filled",
  tone = "success",
  appearance = "default",
  onDismiss,
  bottomOffset = 24,
  lift,
}: Props) {
  const insets = useSafeAreaInsets();
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme, appearance), [theme, appearance]);
  const reduceMotion = useReduceMotion();
  const opacity = useSharedValue(0);
  const translateY = useSharedValue(24);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useLiveAnnouncement(message);

  useEffect(() => {
    if (!message) return;

    opacity.value = reduceMotion ? 1 : 0;
    translateY.value = reduceMotion ? 0 : 24;
    if (!reduceMotion) {
      opacity.value = withTiming(1, { duration: Motion.duration.snappy });
      translateY.value = withSpring(0, { damping: 14, stiffness: 140 });
    }

    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      if (reduceMotion) {
        onDismiss();
        return;
      }
      opacity.value = withTiming(0, { duration: Motion.duration.snappy }, (finished) => {
        if (finished) runOnJS(onDismiss)();
      });
      translateY.value = withTiming(16, { duration: Motion.duration.snappy });
    }, ACTION_BANNER_MS[tone]);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [message, onDismiss, opacity, reduceMotion, tone, translateY]);

  const bannerStyle = useAnimatedStyle(() => ({
    opacity: opacity.value,
    transform: [{ translateY: translateY.value }],
  }));
  const liftStyle = useBottomLiftStyle(lift);

  if (!message) return null;

  const iconColor =
    tone === "error"
      ? theme.danger
      : tone === "warning"
        ? theme.warning
        : tone === "info"
          ? theme.primary
          : theme.success;
  const liveRegion = tone === "error" || tone === "warning" ? "assertive" : "polite";

  return (
    <Animated.View
      testID="action-banner-host"
      style={[s.host, lift ? liftStyle : null]}
      pointerEvents="box-none"
    >
      <Animated.View
        style={[
          s.wrap,
          {
            bottom: insets.bottom + bottomOffset,
          },
          bannerStyle,
        ]}
        pointerEvents="box-none"
      >
        <Pressable
          style={s.toast}
          onPress={onDismiss}
          accessibilityRole="alert"
          accessibilityLiveRegion={liveRegion}
          accessibilityLabel={message}
        >
          <Icon name={icon} size={IconSize.sm} color={iconColor} />
          <Text style={s.text} numberOfLines={2}>
            {message}
          </Text>
        </Pressable>
      </Animated.View>
    </Animated.View>
  );
}

function makeStyles(theme: Theme, appearance: ActionBannerAppearance) {
  const media = appearance === "media";
  // A dark toast vanishes on a black viewer; over media it is always the white pill.
  const toastBg = media ? theme.onMedia : theme.isDark ? theme.surfaceAlt : theme.text;
  const toastText = media ? theme.mediaScrim : theme.isDark ? theme.text : theme.onPrimary;

  return StyleSheet.create({
    host: {
      position: "absolute",
      top: 0,
      right: 0,
      bottom: 0,
      left: 0,
      zIndex: Layer.toast,
      elevation: Layer.toast,
    },
    wrap: {
      position: "absolute",
      left: 24,
      right: 24,
      alignItems: "center",
    },
    toast: {
      flexDirection: "row",
      alignItems: "center",
      gap: Space.xs,
      backgroundColor: toastBg,
      borderRadius: Radius.full,
      paddingHorizontal: Space.gutter,
      paddingVertical: Space.sm,
      maxWidth: 340,
      borderWidth: theme.isDark && !media ? StyleSheet.hairlineWidth : 0,
      borderColor: theme.border,
      ...shadowElevated(theme, "toast"),
    },
    text: {
      flexShrink: 1,
      ...Type.callout,
      color: toastText,
      textAlign: "center",
    },
  });
}
