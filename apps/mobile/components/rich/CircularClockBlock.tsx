import { useEffect, useMemo, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withSequence,
  withTiming,
} from "react-native-reanimated";
import Svg, { Circle, Line } from "react-native-svg";
import { useTranslation } from "react-i18next";

import {
  getClockParts,
  handAngle,
  resolveClockTimezone,
  type ClockParts,
} from "@/lib/clockTime";
import { subscribeClockTick } from "@/lib/clockTick";
import { useReduceMotion } from "@/lib/motion";
import { Theme, useTheme } from "@/lib/theme";
import { Space } from "@/lib/space";
import { Type } from "@/lib/type";

type Props = { content: string };

const SIZE = 232;
const CX = SIZE / 2;
const R = CX - 14;

function ClockHand({
  angle,
  length,
  strokeWidth,
  color,
}: {
  angle: number;
  length: number;
  strokeWidth: number;
  color: string;
}) {
  const rad = ((angle - 90) * Math.PI) / 180;
  return (
    <Line
      x1={CX}
      y1={CX}
      x2={CX + length * Math.cos(rad)}
      y2={CX + length * Math.sin(rad)}
      stroke={color}
      strokeWidth={strokeWidth}
      strokeLinecap="round"
    />
  );
}

function ClockFace({ parts, theme }: { parts: ClockParts; theme: Theme }) {
  const ticks = useMemo(
    () =>
      Array.from({ length: 12 }, (_, i) => {
        const a = ((i / 12) * 360 - 90) * (Math.PI / 180);
        const inner = R - (i % 3 === 0 ? 14 : 8);
        const outer = R - 2;
        return {
          x1: CX + inner * Math.cos(a),
          y1: CX + inner * Math.sin(a),
          x2: CX + outer * Math.cos(a),
          y2: CX + outer * Math.sin(a),
          major: i % 3 === 0,
        };
      }),
    [],
  );

  const second = handAngle(parts.hours, parts.minutes, parts.seconds, "second");
  const minute = handAngle(parts.hours, parts.minutes, parts.seconds, "minute");
  const hour = handAngle(parts.hours, parts.minutes, parts.seconds, "hour");

  return (
    <Svg width={SIZE} height={SIZE}>
      <Circle
        cx={CX}
        cy={CX}
        r={R}
        fill={theme.surface}
        stroke={theme.border}
        strokeWidth={2}
      />
      {ticks.map((t, i) => (
        <Line
          key={i}
          x1={t.x1}
          y1={t.y1}
          x2={t.x2}
          y2={t.y2}
          stroke={theme.textSecondary}
          strokeWidth={t.major ? 2.5 : 1.5}
          strokeLinecap="round"
        />
      ))}
      <ClockHand
        angle={hour}
        length={R * 0.52}
        strokeWidth={4}
        color={theme.text}
      />
      <ClockHand
        angle={minute}
        length={R * 0.72}
        strokeWidth={3}
        color={theme.text}
      />
      <ClockHand angle={second} length={R * 0.82} strokeWidth={2} color={theme.danger} />
      <Circle cx={CX} cy={CX} r={5} fill={theme.primary} />
      <Circle cx={CX} cy={CX} r={2.5} fill={theme.surface} />
    </Svg>
  );
}

/** Live circular analog clock — ```clock fence with IANA timezone. */
export function CircularClockBlock({ content }: Props) {
  const theme = useTheme();
  const { t } = useTranslation();
  const s = useMemo(() => makeStyles(theme), [theme]);
  // No zone named, or one no engine knows: the user's own (the device's), like every
  // other time. The profile's copy was "" on a cold start and drew UTC.
  const timeZone = useMemo(() => resolveClockTimezone(content), [content]);

  const [now, setNow] = useState(() => new Date());
  const reduceMotion = useReduceMotion();
  const pulse = useSharedValue(1);
  const ringOpacity = useSharedValue(0.35);

  useEffect(() => {
    const tick = () => {
      setNow(new Date());
      if (reduceMotion) return;
      pulse.value = withSequence(
        withTiming(1.06, { duration: 120, easing: Easing.out(Easing.quad) }),
        withTiming(1, { duration: 180, easing: Easing.inOut(Easing.quad) }),
      );
      ringOpacity.value = withSequence(
        withTiming(0.85, { duration: 100 }),
        withTiming(0.35, { duration: 400 }),
      );
    };
    tick();
    // One shared interval drives every mounted clock — see lib/clockTick.ts —
    // instead of each instance running its own setInterval indefinitely
    // (FlashList keeps rows mounted slightly past the viewport, so N clocks
    // used to mean N live timers).
    return subscribeClockTick(tick);
  }, [pulse, reduceMotion, ringOpacity]);

  // Read every tick (a cached formatter each): a change of language or clock shows at once.
  const parts = getClockParts(now, timeZone);

  const pulseStyle = useAnimatedStyle(() => ({
    transform: [{ scale: pulse.value }],
  }));

  const ringStyle = useAnimatedStyle(() => ({
    opacity: ringOpacity.value,
  }));

  return (
    <View
      style={s.wrap}
      accessibilityRole="text"
      accessibilityLabel={t("rich.current_time_a11y", { time: parts.timeLabel, date: parts.dateLabel })}
    >
      <View style={s.clockStage}>
        <Animated.View style={[s.ring, ringStyle, pulseStyle]} />
        <Animated.View style={pulseStyle}>
          <ClockFace parts={parts} theme={theme} />
        </Animated.View>
      </View>
      <Text style={s.date}>{parts.dateLabel}</Text>
      <Text style={s.digitalTime}>{parts.timeLabel}</Text>
      <Text style={s.tz}>{parts.tzLabel}</Text>
    </View>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    wrap: {
      alignSelf: "stretch",
      alignItems: "center",
      paddingVertical: Space.gutter,
      paddingHorizontal: Space.md,
      marginVertical: Space.xs,
    },
    clockStage: {
      width: SIZE,
      height: SIZE,
      alignItems: "center",
      justifyContent: "center",
    },
    ring: {
      position: "absolute",
      width: SIZE + 12,
      height: SIZE + 12,
      borderRadius: (SIZE + 12) / 2,
      borderWidth: 3,
      borderColor: theme.primary,
    },
    date: {
      marginTop: Space.sm,
      ...Type.label,
      color: theme.text,
      textAlign: "center",
    },
    digitalTime: {
      marginTop: Space.xs,
      ...Type.h1,
      color: theme.primary,
      textAlign: "center",
      fontVariant: ["tabular-nums"],
    },
    tz: {
      marginTop: Space.xxs,
      ...Type.meta,
      color: theme.textSecondary,
      textAlign: "center",
    },
  });
}
