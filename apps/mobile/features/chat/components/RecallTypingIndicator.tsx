import { useEffect, useMemo } from "react";
import { StyleSheet, View } from "react-native";
import Animated, {
  cancelAnimation,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withSequence,
  withTiming,
} from "react-native-reanimated";
import { useTranslation } from "react-i18next";

import { Motion, useReduceMotion } from "@/lib/motion";
import { Radius } from "@/lib/radius";
import { Theme, useTheme } from "@/lib/theme";
import { PULSE_PROFILES, typingPulseKindForPhase } from "@/lib/typingPulse";

type Props = {
  /** Live `streamStatus` phase from the chat socket (preparing, searching, …). */
  phase?: string | null;
};

/** Accent disc whose pulse speed/strength tracks the live chat status phase. */
export function RecallTypingIndicator({ phase }: Props) {
  const theme = useTheme();
  const { t } = useTranslation();
  const reduceMotion = useReduceMotion();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const kind = typingPulseKindForPhase(phase);
  const profile = PULSE_PROFILES[kind];
  const scale = useSharedValue(1);
  const opacity = useSharedValue(0.7);

  useEffect(() => {
    cancelAnimation(scale);
    cancelAnimation(opacity);
    if (reduceMotion) {
      scale.value = 1;
      opacity.value = 0.85;
      return;
    }
    const { minScale, maxScale, minOpacity, maxOpacity, halfMs } = profile;
    scale.value = minScale;
    opacity.value = minOpacity;
    scale.value = withRepeat(
      withSequence(
        withTiming(maxScale, { duration: halfMs, easing: Motion.easing.inOut }),
        withTiming(minScale, { duration: halfMs, easing: Motion.easing.inOut }),
      ),
      -1,
      false,
    );
    opacity.value = withRepeat(
      withSequence(
        withTiming(maxOpacity, { duration: halfMs, easing: Motion.easing.inOut }),
        withTiming(minOpacity, { duration: halfMs, easing: Motion.easing.inOut }),
      ),
      -1,
      false,
    );
  }, [opacity, profile, reduceMotion, scale]);

  const discStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
    opacity: opacity.value,
  }));

  const a11yKey = phase ? `chat.status.${phase}` : "chat.status.thinking";
  const a11y = t(a11yKey);
  const a11yLabel = a11y === a11yKey ? t("chat.status.thinking") : a11y;

  return (
    <View style={s.wrap} accessibilityRole="progressbar" accessibilityLabel={a11yLabel}>
      <Animated.View style={[s.disc, discStyle]} />
    </View>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    wrap: {
      width: 28,
      height: 28,
      alignItems: "center",
      justifyContent: "center",
    },
    disc: {
      width: 18,
      height: 18,
      borderRadius: Radius.full,
      backgroundColor: t.accent,
    },
  });
}
