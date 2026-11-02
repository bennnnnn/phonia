import { useEffect, useMemo, useRef } from "react";
import {
  StyleSheet,
  Text,
  View,
  type AccessibilityActionEvent,
  type GestureResponderEvent,
} from "react-native";
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withSpring,
} from "react-native-reanimated";

import {
  angleForHour,
  angleForMinute,
  HOURS_INNER,
  HOURS_OUTER,
  hourAtAngle,
  hourOnInnerRing,
  MINUTE_MARKS,
  minuteAtAngle,
  pad2,
  pointOnDial,
  pointToAngle,
  touchesInnerRing,
  type ClockMode,
} from "@/lib/datetime/clockDial";
import { selection } from "@/lib/haptics";
import { Motion, useReduceMotion } from "@/lib/motion";
import { type Theme, useTheme } from "@/lib/theme";
import { DYNAMIC_TYPE_PICKER_MAX, Type } from "@/lib/type";

/** Material clock: a 256 face, 48 handle, and labels 24 in from the rim. */
export const CLOCK_DIAL_SIZE = 256;
const HANDLE = 48;
const CENTER_DOT = 8;
/** Marks a minute between the five-minute labels. */
const HANDLE_DOT = 6;
const INNER_RING_GAP = 40;

type Props = {
  mode: ClockMode;
  /** 0–23. */
  hour: number;
  minute: number;
  is24Hour: boolean;
  /** `final` is true when the finger lifts (the picker then moves on to minutes). */
  onHourChange: (hour: number, final: boolean) => void;
  onMinuteChange: (minute: number, final: boolean) => void;
  size?: number;
  /** Spoken name of the dial, e.g. "Hour". */
  accessibilityLabel: string;
  /** Spoken current value, e.g. "9 PM" or "11 minutes". */
  accessibilityValueText: string;
  testID?: string;
};

/** Shortest turn from `from` to `to`, so 330° → 30° goes forward through 12. */
function nearestTurn(from: number, to: number): number {
  const delta = ((((to - from) % 360) + 540) % 360) - 180;
  return from + delta;
}

type Label = { value: number; text: string; angle: number; inner: boolean };

/**
 * The round face of the time picker. Tap or drag to a number; the hand glides
 * there and the number under the handle turns white, as on Android's clock.
 * One adjustable control for screen readers: swipe up/down to change it.
 */
export function ClockDial({
  mode,
  hour,
  minute,
  is24Hour,
  onHourChange,
  onMinuteChange,
  size = CLOCK_DIAL_SIZE,
  accessibilityLabel,
  accessibilityValueText,
  testID = "clock-dial",
}: Props) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme, size), [theme, size]);
  const reduceMotion = useReduceMotion();
  const center = size / 2;
  const outerRadius = center - HANDLE / 2 - 4;
  const innerRadius = outerRadius - INNER_RING_GAP;

  const inner = mode === "hour" && hourOnInnerRing(hour, is24Hour);
  const angle = mode === "hour" ? angleForHour(hour) : angleForMinute(minute);
  const tipRadius = inner ? innerRadius : outerRadius;

  const turn = useSharedValue(angle);
  const reach = useSharedValue(tipRadius);
  const dragging = useRef(false);
  const lastValue = useRef<number | null>(null);

  useEffect(() => {
    const target = nearestTurn(turn.value, angle);
    if (reduceMotion || dragging.current) {
      turn.value = target;
      reach.value = tipRadius;
    } else {
      turn.value = withSpring(target, Motion.spring.pointer);
      reach.value = withSpring(tipRadius, Motion.spring.pointer);
    }
  }, [angle, tipRadius, reduceMotion, turn, reach]);

  const labels = useMemo<Label[]>(() => {
    if (mode === "minute") {
      return MINUTE_MARKS.map((value) => ({
        value,
        text: pad2(value),
        angle: angleForMinute(value),
        inner: false,
      }));
    }
    const outer = HOURS_OUTER.map((value) => ({
      value,
      text: is24Hour ? pad2(value) : String(value),
      angle: angleForHour(value),
      inner: false,
    }));
    if (!is24Hour) return outer;
    return [
      ...outer,
      ...HOURS_INNER.map((value) => ({
        value,
        text: pad2(value),
        angle: angleForHour(value),
        inner: true,
      })),
    ];
  }, [mode, is24Hour]);

  const pick = (event: GestureResponderEvent, final: boolean) => {
    const dx = event.nativeEvent.locationX - center;
    const dy = event.nativeEvent.locationY - center;
    const at = pointToAngle(dx, dy);
    let value: number;
    if (mode === "hour") {
      value = hourAtAngle(at, {
        is24Hour,
        inner: is24Hour && touchesInnerRing(Math.hypot(dx, dy), outerRadius, innerRadius),
        pm: hour >= 12,
      });
    } else {
      value = minuteAtAngle(at);
    }
    if (value !== lastValue.current) {
      lastValue.current = value;
      selection();
    }
    if (mode === "hour") onHourChange(value, final);
    else onMinuteChange(value, final);
  };

  const step = (delta: number) => {
    if (mode === "hour") onHourChange((hour + delta + 24) % 24, false);
    else onMinuteChange((minute + delta + 60) % 60, false);
  };

  const onAccessibilityAction = (event: AccessibilityActionEvent) => {
    if (event.nativeEvent.actionName === "increment") step(1);
    if (event.nativeEvent.actionName === "decrement") step(-1);
  };

  const armStyle = useAnimatedStyle(() => ({
    transform: [{ rotate: `${turn.value}deg` }],
  }));
  const lineStyle = useAnimatedStyle(() => ({
    top: center - reach.value,
    height: reach.value,
  }));
  const handleStyle = useAnimatedStyle(() => ({
    top: center - reach.value - HANDLE / 2,
  }));
  // The white copy of the labels inside the handle, turned back upright and
  // shifted so each label sits exactly over its grey twin.
  const inkStyle = useAnimatedStyle(() => ({
    top: -(center - reach.value - HANDLE / 2),
    transform: [{ rotate: `${-turn.value}deg` }],
  }));

  const renderLabels = (ink: boolean) =>
    labels.map((label) => {
      const point = pointOnDial(label.angle, label.inner ? innerRadius : outerRadius, center);
      return (
        <View
          key={`${label.inner ? "i" : "o"}${label.value}`}
          style={[s.labelBox, { left: point.x - HANDLE / 2, top: point.y - HANDLE / 2 }]}
        >
          <Text
            style={[s.label, label.inner && s.labelInner, ink && s.labelInk]}
            maxFontSizeMultiplier={DYNAMIC_TYPE_PICKER_MAX}
          >
            {label.text}
          </Text>
        </View>
      );
    });

  return (
    <View
      testID={testID}
      style={s.face}
      onStartShouldSetResponder={() => true}
      onMoveShouldSetResponder={() => true}
      onResponderTerminationRequest={() => false}
      onResponderGrant={(event) => {
        dragging.current = true;
        pick(event, false);
      }}
      onResponderMove={(event) => pick(event, false)}
      onResponderRelease={(event) => {
        dragging.current = false;
        pick(event, true);
        lastValue.current = null;
      }}
      onResponderTerminate={() => {
        dragging.current = false;
        lastValue.current = null;
      }}
      accessible
      accessibilityRole="adjustable"
      accessibilityLabel={accessibilityLabel}
      accessibilityValue={{ text: accessibilityValueText }}
      accessibilityActions={[{ name: "increment" }, { name: "decrement" }]}
      onAccessibilityAction={onAccessibilityAction}
    >
      <View style={StyleSheet.absoluteFill} pointerEvents="none">
        {renderLabels(false)}
      </View>
      <Animated.View style={[StyleSheet.absoluteFill, armStyle]} pointerEvents="none">
        <Animated.View style={[s.line, lineStyle]} />
        <Animated.View style={[s.handle, handleStyle]}>
          <Animated.View style={[s.ink, inkStyle]}>{renderLabels(true)}</Animated.View>
          {mode === "minute" && minute % 5 !== 0 ? <View style={s.handleDot} /> : null}
        </Animated.View>
      </Animated.View>
      <View style={s.centerDot} pointerEvents="none" />
    </View>
  );
}

function makeStyles(t: Theme, size: number) {
  const center = size / 2;
  return StyleSheet.create({
    face: {
      width: size,
      height: size,
      borderRadius: center,
      backgroundColor: t.control,
      alignSelf: "center",
    },
    labelBox: {
      position: "absolute",
      width: HANDLE,
      height: HANDLE,
      alignItems: "center",
      justifyContent: "center",
    },
    label: {
      ...Type.body,
      color: t.text,
      fontVariant: ["tabular-nums"],
    },
    labelInner: {
      ...Type.secondary,
      color: t.textSecondary,
    },
    labelInk: { color: t.onPrimary },
    line: {
      position: "absolute",
      left: center - 1,
      width: 2,
      backgroundColor: t.primary,
    },
    handle: {
      position: "absolute",
      left: center - HANDLE / 2,
      width: HANDLE,
      height: HANDLE,
      borderRadius: HANDLE / 2,
      backgroundColor: t.primary,
      overflow: "hidden",
      alignItems: "center",
      justifyContent: "center",
    },
    ink: {
      position: "absolute",
      left: -(center - HANDLE / 2),
      width: size,
      height: size,
    },
    handleDot: {
      width: HANDLE_DOT,
      height: HANDLE_DOT,
      borderRadius: HANDLE_DOT / 2,
      backgroundColor: t.onPrimary,
    },
    centerDot: {
      position: "absolute",
      left: center - CENTER_DOT / 2,
      top: center - CENTER_DOT / 2,
      width: CENTER_DOT,
      height: CENTER_DOT,
      borderRadius: CENTER_DOT / 2,
      backgroundColor: t.primary,
    },
  });
}
