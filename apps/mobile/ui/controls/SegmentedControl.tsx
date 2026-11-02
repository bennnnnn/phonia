import { useEffect, useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import Animated, { useAnimatedStyle, useSharedValue, withSpring } from "react-native-reanimated";

import { selection } from "@/lib/haptics";
import { Motion, useReduceMotion } from "@/lib/motion";
import { Radius } from "@/lib/radius";
import { shadowRaised } from "@/lib/shadow";
import { Space } from "@/lib/space";
import { type Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";

type Segment<K extends string> = { key: K; label: string };

type Props<K extends string> = {
  segments: readonly Segment<K>[];
  value: K;
  onChange: (key: K) => void;
  /** Spoken name of the choice, e.g. "Text size". */
  accessibilityLabel?: string;
  testID?: string;
};

/**
 * Pick one of two to four short options in place (Small · Medium · Large).
 * A raised thumb slides to the choice. For longer lists use SelectMenu.
 */
export function SegmentedControl<K extends string>({
  segments,
  value,
  onChange,
  accessibilityLabel,
  testID = "segmented",
}: Props<K>) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const reduceMotion = useReduceMotion();
  const [width, setWidth] = useState(0);
  const index = Math.max(
    0,
    segments.findIndex((segment) => segment.key === value),
  );
  const segmentWidth = width > 0 ? (width - Space.xxs * 2) / segments.length : 0;
  const offset = useSharedValue(index * segmentWidth);

  useEffect(() => {
    const target = index * segmentWidth;
    offset.value =
      reduceMotion || segmentWidth === 0 ? target : withSpring(target, Motion.spring.press);
  }, [index, segmentWidth, reduceMotion, offset]);

  const thumbStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: offset.value }],
  }));

  return (
    <View
      style={s.track}
      onLayout={(event) => setWidth(event.nativeEvent.layout.width)}
      accessibilityRole="radiogroup"
      accessibilityLabel={accessibilityLabel}
      testID={testID}
    >
      {segmentWidth > 0 ? (
        <Animated.View
          pointerEvents="none"
          style={[s.thumb, { width: segmentWidth }, thumbStyle]}
          testID={`${testID}-thumb`}
        />
      ) : null}
      {segments.map((segment) => {
        const selected = segment.key === value;
        return (
          <Pressable
            key={segment.key}
            style={s.segment}
            // 40pt segment in a 4pt-padded track: the track's edge is the 44pt target's.
            hitSlop={{ top: 2, bottom: 2 }}
            onPress={() => {
              if (selected) return;
              selection();
              onChange(segment.key);
            }}
            accessibilityRole="radio"
            accessibilityState={{ checked: selected }}
            accessibilityLabel={segment.label}
            testID={`${testID}-${segment.key}`}
          >
            <Text style={[s.label, selected && s.labelOn]} numberOfLines={1}>
              {segment.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    // The thumb is always the lighter of the two, so the choice reads as raised.
    track: {
      flexDirection: "row",
      padding: Space.xxs,
      borderRadius: Radius.full,
      backgroundColor: t.isDark ? t.surface : t.control,
    },
    thumb: {
      position: "absolute",
      top: Space.xxs,
      bottom: Space.xxs,
      left: Space.xxs,
      borderRadius: Radius.full,
      backgroundColor: t.isDark ? t.control : t.elevated,
      ...shadowRaised(t),
    },
    segment: {
      flex: 1,
      minHeight: Space.xl + Space.xs,
      paddingHorizontal: Space.xs,
      borderRadius: Radius.full,
      alignItems: "center",
      justifyContent: "center",
    },
    label: { ...Type.label, ...Weight.medium, color: t.textSecondary },
    labelOn: { ...Weight.semibold, color: t.text },
  });
}
