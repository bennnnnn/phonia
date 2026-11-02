import { useEffect, useMemo } from "react";
import { StyleSheet, Text, View } from "react-native";
import Animated, {
  Easing,
  type SharedValue,
  useAnimatedReaction,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
} from "react-native-reanimated";
import { useTranslation } from "react-i18next";

import { motionMs, useReduceMotion } from "@/lib/motion";
import { Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";
import { Space } from "@/lib/space";

const BAR_COUNT = 36;
const MIN_H = 3;
const MAX_H = 26;

type BarProps = {
  index: number;
  meter: SharedValue<number>;
  phase: SharedValue<number>;
  processing: SharedValue<number>;
  color: string;
};

function WaveBar({ index, meter, phase, processing, color }: BarProps) {
  const style = useAnimatedStyle(() => {
    const center = (BAR_COUNT - 1) / 2;
    const dist = Math.abs(index - center) / center;
    const centerWeight = 1 - dist * 0.5;
    const wave = Math.sin(phase.value * Math.PI * 2 + index * 0.38) * 0.5 + 0.5;
    const proc = processing.value;
    const recordingLevel = 0.08 + meter.value * centerWeight * (0.25 + 0.75 * wave);
    // One bump traveling L→R — reads as "working on the take", not live mic.
    const sweep = phase.value * (BAR_COUNT + 8) - 4;
    const d = Math.abs(index - sweep);
    const bump = Math.max(0, 1 - d / 3.4);
    const processingLevel = 0.1 + 0.78 * bump;
    const level = recordingLevel * (1 - proc) + processingLevel * proc;
    const h = MIN_H + (MAX_H - MIN_H) * level;
    return {
      height: h,
      opacity: 0.28 + 0.72 * level,
    };
  });

  return (
    <Animated.View testID="voice-waveform-bar" style={[styles.bar, { backgroundColor: color }, style]} />
  );
}

/** The live mic level, written by the recorder without a React render. */
export type MeterLevel = SharedValue<number>;

type Props = {
  recording: boolean;
  transcribing: boolean;
  meterLevel?: MeterLevel;
};

/** Live meter while dictating; a traveling sweep + label while transcribing. */
export function VoiceComposerWaveform({
  recording: _recording,
  transcribing,
  meterLevel,
}: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const reduceMotion = useReduceMotion();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const meter = useSharedValue(0.12);
  const phase = useSharedValue(0);
  const processing = useSharedValue(transcribing ? 1 : 0);
  const idleLevel = useSharedValue(0.12);
  const level = meterLevel ?? idleLevel;
  const meterMs = motionMs(70, reduceMotion);

  useAnimatedReaction(
    () => level.value,
    (next) => {
      meter.value = withTiming(next, { duration: meterMs });
    },
    [meterMs],
  );

  useEffect(() => {
    if (reduceMotion) {
      phase.value = transcribing ? 0.45 : 0.5;
      return;
    }
    phase.value = 0;
    phase.value = withRepeat(
      withTiming(1, {
        duration: transcribing ? 1700 : 1100,
        easing: Easing.linear,
      }),
      -1,
      false,
    );
  }, [phase, reduceMotion, transcribing]);

  useEffect(() => {
    processing.value = withTiming(transcribing ? 1 : 0, {
      duration: motionMs(180, reduceMotion),
    });
  }, [transcribing, processing, reduceMotion]);

  const indices = useMemo(() => Array.from({ length: BAR_COUNT }, (_, i) => i), []);
  const label = transcribing ? t("chat.voice_transcribing") : t("chat.voice_listening");
  const barColor = theme.text;

  return (
    <View
      style={s.wrap}
      accessibilityRole="progressbar"
      accessibilityLabel={label}
      accessibilityLiveRegion="polite"
      accessibilityState={{ busy: transcribing }}
    >
      {transcribing ? (
        <Text style={s.status} numberOfLines={1}>
          {t("chat.voice_transcribing")}
        </Text>
      ) : null}
      <View style={s.bars}>
        {indices.map((i) => (
          <WaveBar
            key={i}
            index={i}
            meter={meter}
            phase={phase}
            processing={processing}
            color={barColor}
          />
        ))}
      </View>
    </View>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    wrap: {
      flex: 1,
      minHeight: 28,
      flexDirection: "row",
      alignItems: "center",
      gap: Space.xs,
      paddingVertical: 2,
    },
    status: {
      ...Type.caption,
      color: t.textSecondary,
      flexShrink: 0,
    },
    bars: {
      flex: 1,
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "center",
      gap: 2,
      height: MAX_H,
    },
  });
}

const styles = StyleSheet.create({
  bar: {
    width: 2.5,
    borderRadius: 2,
  },
});
