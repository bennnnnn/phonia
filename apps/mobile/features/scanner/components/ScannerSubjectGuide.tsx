import { useEffect, useMemo } from "react";
import { StyleSheet, View } from "react-native";
import Animated, {
  cancelAnimation,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from "react-native-reanimated";
import Svg, { Circle, Ellipse, Line, Path } from "react-native-svg";
import { useTranslation } from "react-i18next";

import { Motion, motionMs, useReduceMotion } from "@/lib/motion";
import { Radius } from "@/lib/radius";
import type { ScannerSubject } from "@/lib/scanner/subjects";
import { Theme, useTheme, withAlpha } from "@/lib/theme";

type Props = {
  subject: ScannerSubject;
};

const LABEL_KEYS: Record<ScannerSubject, string> = {
  math: "chat.math_scan_subject_math",
  physics: "chat.math_scan_subject_physics",
  chemistry: "chat.math_scan_subject_chemistry",
  biology: "chat.math_scan_subject_biology",
};

export function ScannerSubjectGuide({ subject }: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const reduceMotion = useReduceMotion();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const reveal = useSharedValue(1);
  const transitionMs = motionMs(Motion.duration.standard, reduceMotion);

  useEffect(() => {
    cancelAnimation(reveal);
    if (reduceMotion) {
      reveal.value = 1;
      return;
    }
    reveal.value = 0;
    reveal.value = withTiming(1, { duration: transitionMs });
    return () => cancelAnimation(reveal);
  }, [reduceMotion, reveal, subject, transitionMs]);

  const revealStyle = useAnimatedStyle(() => ({
    opacity: 0.4 + reveal.value * 0.6,
    transform: [{ scale: 0.9 + reveal.value * 0.1 }],
  }));

  return (
    <View style={s.position} pointerEvents="none">
      <Animated.View
        key={subject}
        testID={`scanner-subject-guide-${subject}`}
        style={[s.badge, revealStyle]}
        accessible
        accessibilityRole="image"
        accessibilityLabel={t(LABEL_KEYS[subject])}
      >
        <SubjectMark subject={subject} primary={theme.primary} ink={theme.onMedia} />
      </Animated.View>
    </View>
  );
}

function SubjectMark({ subject, primary, ink }: Props & { primary: string; ink: string }) {
  if (subject === "physics") {
    return (
      <Svg width={62} height={62} viewBox="0 0 64 64">
        <Ellipse cx={32} cy={32} rx={25} ry={10} fill="none" stroke={ink} strokeWidth={2.4} />
        <Ellipse
          cx={32}
          cy={32}
          rx={25}
          ry={10}
          fill="none"
          stroke={ink}
          strokeWidth={2.4}
          transform="rotate(60 32 32)"
        />
        <Ellipse
          cx={32}
          cy={32}
          rx={25}
          ry={10}
          fill="none"
          stroke={ink}
          strokeWidth={2.4}
          transform="rotate(120 32 32)"
        />
        <Circle cx={32} cy={32} r={5.2} fill={primary} />
        <Circle cx={56} cy={32} r={2.8} fill={primary} />
        <Circle cx={20} cy={10.5} r={2.8} fill={primary} />
        <Circle cx={20} cy={53.5} r={2.8} fill={primary} />
      </Svg>
    );
  }

  if (subject === "chemistry") {
    return (
      <Svg width={62} height={62} viewBox="0 0 64 64">
        <Path
          d="M26 8h12M28 8v16L16 52a6 6 0 0 0 5 8h22a6 6 0 0 0 5-8L36 24V8"
          fill="none"
          stroke={ink}
          strokeWidth={3}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <Path d="M20 42h24" stroke={primary} strokeWidth={3} strokeLinecap="round" />
      </Svg>
    );
  }

  if (subject === "biology") {
    return (
      <Svg width={62} height={62} viewBox="0 0 64 64">
        <Path
          d="M18 7c0 12 28 12 28 25S18 45 18 57"
          fill="none"
          stroke={ink}
          strokeWidth={3}
          strokeLinecap="round"
        />
        <Path
          d="M46 7c0 12-28 12-28 25s28 13 28 25"
          fill="none"
          stroke={primary}
          strokeWidth={3}
          strokeLinecap="round"
        />
        <Line x1={21} y1={14} x2={43} y2={14} stroke={ink} strokeWidth={2} />
        <Line x1={18} y1={25} x2={46} y2={25} stroke={ink} strokeWidth={2} />
        <Line x1={18} y1={39} x2={46} y2={39} stroke={ink} strokeWidth={2} />
        <Line x1={21} y1={50} x2={43} y2={50} stroke={ink} strokeWidth={2} />
      </Svg>
    );
  }

  return (
    <Svg width={62} height={62} viewBox="0 0 64 64">
      <Path
        d="M48 10H20L34 32 20 54h28"
        fill="none"
        stroke={ink}
        strokeWidth={4}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <Line x1={41} y1={25} x2={56} y2={25} stroke={primary} strokeWidth={3} strokeLinecap="round" />
      <Line x1={48.5} y1={17.5} x2={48.5} y2={32.5} stroke={primary} strokeWidth={3} strokeLinecap="round" />
      <Circle cx={49} cy={46} r={3.5} fill={primary} />
    </Svg>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    position: {
      position: "absolute",
      top: 94,
      left: 0,
      right: 0,
      alignItems: "center",
      zIndex: 4,
    },
    badge: {
      width: 82,
      height: 82,
      alignItems: "center",
      justifyContent: "center",
      borderRadius: Radius.xl,
      backgroundColor: withAlpha(theme.mediaScrim, 0.3),
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: withAlpha(theme.onMedia, 0.26),
    },
  });
}
