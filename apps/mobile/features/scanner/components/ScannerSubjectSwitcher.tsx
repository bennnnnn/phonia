/* eslint-disable react-hooks/immutability -- Reanimated shared values are mutated on the UI thread by design */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View, type AccessibilityActionEvent } from "react-native";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import Animated, {
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from "react-native-reanimated";
import { useTranslation } from "react-i18next";

import { Motion, motionMs, useReduceMotion } from "@/lib/motion";
import { Radius } from "@/lib/radius";
import { SCANNER_SUBJECTS, type ScannerSubject } from "@/lib/scanner/subjects";
import { Space } from "@/lib/space";
import { Theme, useTheme, withAlpha } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";

type Props = {
  value: ScannerSubject;
  onChange: (subject: ScannerSubject) => void;
};

const LABEL_KEYS: Record<ScannerSubject, string> = {
  math: "chat.math_scan_subject_math",
  physics: "chat.math_scan_subject_physics",
  chemistry: "chat.math_scan_subject_chemistry",
  biology: "chat.math_scan_subject_biology",
};

function subjectAt(index: number): ScannerSubject {
  return SCANNER_SUBJECTS[Math.max(0, Math.min(SCANNER_SUBJECTS.length - 1, index))] ?? "math";
}

export function ScannerSubjectSwitcher({ value, onChange }: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const reduceMotion = useReduceMotion();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const [width, setWidth] = useState(0);
  const segmentWidth = Math.max(0, width - 6) / SCANNER_SUBJECTS.length;
  const initialPosition = SCANNER_SUBJECTS.indexOf(value);
  const position = useSharedValue(initialPosition);
  const dragStart = useSharedValue(initialPosition);
  const transitionMs = motionMs(Motion.duration.standard, reduceMotion);

  useEffect(() => {
    position.value = withTiming(SCANNER_SUBJECTS.indexOf(value), { duration: transitionMs });
  }, [position, transitionMs, value]);

  const selectIndex = useCallback(
    (index: number) => {
      const next = subjectAt(index);
      if (next !== value) onChange(next);
    },
    [onChange, value],
  );

  const pan = useMemo(
    () =>
      Gesture.Pan()
        .minDistance(4)
        .onBegin(() => {
          dragStart.value = position.value;
        })
        .onUpdate((event) => {
          if (segmentWidth <= 0) return;
          position.value = Math.max(
            0,
            Math.min(SCANNER_SUBJECTS.length - 1, dragStart.value + event.translationX / segmentWidth),
          );
        })
        .onEnd(() => {
          const target = Math.round(position.value);
          position.value = withTiming(target, { duration: transitionMs });
          runOnJS(selectIndex)(target);
        }),
    [dragStart, position, segmentWidth, selectIndex, transitionMs],
  );

  const indicatorStyle = useAnimatedStyle(() => ({
    width: segmentWidth,
    transform: [{ translateX: position.value * segmentWidth }],
  }));
  const inkStyle = useAnimatedStyle(() => ({
    width: segmentWidth * SCANNER_SUBJECTS.length,
    transform: [{ translateX: -position.value * segmentWidth }],
  }));

  const onA11yAction = (event: AccessibilityActionEvent) => {
    const current = SCANNER_SUBJECTS.indexOf(value);
    if (event.nativeEvent.actionName === "increment") selectIndex(current + 1);
    if (event.nativeEvent.actionName === "decrement") selectIndex(current - 1);
  };

  return (
    <GestureDetector gesture={pan}>
      <View
        testID="scanner-subject-switcher"
        style={s.track}
        onLayout={(event) => setWidth(event.nativeEvent.layout.width)}
        accessible
        accessibilityRole="adjustable"
        accessibilityLabel={t("chat.math_scan_subject_a11y")}
        accessibilityValue={{ text: t(LABEL_KEYS[value]) }}
        accessibilityActions={[{ name: "increment" }, { name: "decrement" }]}
        onAccessibilityAction={onA11yAction}
      >
        {SCANNER_SUBJECTS.map((subject, index) => {
          const selected = subject === value;
          return (
            <Pressable
              key={subject}
              testID={`scanner-subject-${subject}`}
              style={s.option}
              onPress={() => selectIndex(index)}
              accessibilityRole="tab"
              accessibilityState={{ selected }}
              accessibilityLabel={t(LABEL_KEYS[subject])}
            >
              <Text style={s.label}>{t(LABEL_KEYS[subject])}</Text>
            </Pressable>
          );
        })}
        {width > 0 ? (
          // Dark copies ride inside the pill. The words underneath stay light,
          // so a drag does not blank the subject you started on.
          <Animated.View pointerEvents="none" style={[s.indicator, indicatorStyle]}>
            <Animated.View style={[s.inkRow, inkStyle]}>
              {SCANNER_SUBJECTS.map((subject) => (
                <View key={subject} style={[s.inkCell, { width: segmentWidth }]}>
                  <Text style={s.inkLabel} accessibilityElementsHidden importantForAccessibility="no">
                    {t(LABEL_KEYS[subject])}
                  </Text>
                </View>
              ))}
            </Animated.View>
          </Animated.View>
        ) : null}
      </View>
    </GestureDetector>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    track: {
      width: "86%",
      maxWidth: 360,
      height: 42,
      alignSelf: "center",
      flexDirection: "row",
      borderRadius: Radius.full,
      padding: Space.xxs,
      overflow: "hidden",
      backgroundColor: withAlpha(theme.mediaScrim, 0.68),
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: withAlpha(theme.onMedia, 0.24),
    },
    indicator: {
      position: "absolute",
      top: 3,
      bottom: 3,
      left: 3,
      borderRadius: Radius.full,
      overflow: "hidden",
      backgroundColor: withAlpha(theme.onMedia, 0.96),
    },
    inkRow: {
      flexDirection: "row",
      height: "100%",
    },
    inkCell: {
      height: "100%",
      paddingHorizontal: Space.xs,
      alignItems: "center",
      justifyContent: "center",
    },
    option: {
      flex: 1,
      minHeight: 36,
      paddingHorizontal: Space.xs,
      alignItems: "center",
      justifyContent: "center",
    },
    label: {
      ...Type.compact,
      color: withAlpha(theme.onMedia, 0.78),
      ...Weight.bold,
    },
    inkLabel: {
      ...Type.compact,
      color: theme.mediaScrim,
      ...Weight.bold,
    },
  });
}
