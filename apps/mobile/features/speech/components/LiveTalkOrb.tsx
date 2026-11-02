import { useEffect, useMemo } from "react";
import { StyleSheet, View } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import Animated, {
  Easing,
  type SharedValue,
  cancelAnimation,
  useAnimatedStyle,
  useSharedValue,
  withDelay,
  withRepeat,
  withSequence,
  withTiming,
} from "react-native-reanimated";

import { liveTalkOrbMode, type LiveTalkPhase } from "@/features/speech/model/liveTalkLogic";
import { Motion } from "@/lib/motion";
import { Theme, withAlpha } from "@/lib/theme";
import { Space } from "@/lib/space";
import { Radius } from "@/lib/radius";

const STAGE = 236;
const CORE = 128;
const HALO = 148;
const PARK_LOOK_X = 9;
const PARK_LOOK_Y = -7;
const LISTENING_GLOW = 0.8;

type Props = {
  theme: Theme;
  phase: LiveTalkPhase;
  recording: boolean;
  reduceMotion: boolean;
};

export function LiveTalkOrb({ theme, phase, recording, reduceMotion }: Props) {
  const s = useMemo(() => makeOrbStyles(theme), [theme]);
  const mode = liveTalkOrbMode(phase);
  const lookX = useSharedValue(PARK_LOOK_X);
  const lookY = useSharedValue(PARK_LOOK_Y);
  const blink = useSharedValue(1);
  const drift = useSharedValue(0);
  const scaleX = useSharedValue(1);
  const scaleY = useSharedValue(1);
  const meter = useSharedValue(0);

  // A steady glow while it listens. Live talk has no input level to follow, so the halo
  // says "listening" rather than pretending to move with the voice.
  useEffect(() => {
    const target = mode === "listen" && recording ? LISTENING_GLOW : 0;
    meter.value = withTiming(target, { duration: reduceMotion ? 0 : 120 });
  }, [mode, recording, meter, reduceMotion]);

  useEffect(() => {
    cancelAnimation(lookX);
    cancelAnimation(lookY);
    cancelAnimation(blink);
    cancelAnimation(drift);
    cancelAnimation(scaleX);
    cancelAnimation(scaleY);
    if (reduceMotion) {
      lookX.value = PARK_LOOK_X;
      lookY.value = PARK_LOOK_Y;
      blink.value = 1;
      drift.value = 0;
      scaleX.value = 1;
      scaleY.value = mode === "speak" ? 1.02 : 1;
      return;
    }
    const ease = Motion.easing.inOut;
    drift.value = withRepeat(withTiming(1, { duration: 2400, easing: Easing.linear }), -1, true);
    startGaze(mode, lookX, lookY, ease);
    startBlink(mode, blink, ease);
    startBody(mode, scaleX, scaleY, ease);
  }, [blink, drift, lookX, lookY, mode, reduceMotion, scaleX, scaleY]);

  const bodyStyle = useAnimatedStyle(() => ({
    transform: [{ scaleX: scaleX.value }, { scaleY: scaleY.value }],
  }));
  const gazeStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: lookX.value },
      { translateY: lookY.value },
      { scaleY: Math.max(0.08, blink.value) },
    ],
  }));
  const rightEyeStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: drift.value * 1.6 }, { translateY: drift.value * -0.8 }],
  }));
  const haloStyle = useAnimatedStyle(() => ({
    transform: [{ scale: 1 + meter.value * 0.25 }],
    opacity: 0.5 + meter.value * 0.5,
  }));

  const inner = theme.isDark
    ? ([theme.primaryDark, theme.primary, theme.primaryLight] as const)
    : ([theme.primary, theme.primaryDark] as const);

  return (
    <View style={s.stage} testID={`live-talk-orb-${mode}`}>
      <Animated.View
        pointerEvents="none"
        style={[
          s.halo,
          { backgroundColor: withAlpha(theme.primary, 0.35) },
          haloStyle,
        ]}
      />
      <Animated.View style={[s.core, bodyStyle]}>
        <LinearGradient colors={[...inner]} start={{ x: 0.22, y: 0 }} end={{ x: 0.85, y: 1 }} style={s.fill} />
        <Animated.View style={[s.eyes, gazeStyle]} testID="live-talk-orb-eyes">
          <View style={s.eye} />
          <Animated.View style={[s.eye, rightEyeStyle]} />
        </Animated.View>
      </Animated.View>
    </View>
  );
}

function startGaze(
  mode: ReturnType<typeof liveTalkOrbMode>,
  lookX: SharedValue<number>,
  lookY: SharedValue<number>,
  ease: typeof Motion.easing.inOut,
): void {
  if (mode === "speak") {
    lookX.value = withRepeat(
      withSequence(
        withTiming(4, { duration: 280, easing: ease }),
        withTiming(-5, { duration: 260, easing: ease }),
        withTiming(2, { duration: 220, easing: ease }),
        withTiming(0, { duration: 240, easing: ease }),
      ),
      -1,
      false,
    );
    lookY.value = withRepeat(
      withSequence(
        withTiming(-5, { duration: 240, easing: ease }),
        withTiming(-2, { duration: 200, easing: ease }),
        withTiming(-6, { duration: 260, easing: ease }),
        withTiming(-3, { duration: 220, easing: ease }),
      ),
      -1,
      false,
    );
    return;
  }
  const slow = mode === "think" || mode === "idle";
  const d = slow ? 1.45 : 1;
  lookX.value = withRepeat(
    withSequence(
      withTiming(10, { duration: 640 * d, easing: ease }),
      withTiming(-8, { duration: 720 * d, easing: ease }),
      withTiming(5, { duration: 540 * d, easing: ease }),
      withTiming(-11, { duration: 800 * d, easing: ease }),
      withTiming(9, { duration: 600 * d, easing: ease }),
    ),
    -1,
    false,
  );
  lookY.value = withRepeat(
    withSequence(
      withTiming(-8, { duration: 700 * d, easing: ease }),
      withTiming(5, { duration: 640 * d, easing: ease }),
      withTiming(-4, { duration: 580 * d, easing: ease }),
      withTiming(7, { duration: 760 * d, easing: ease }),
      withTiming(-6, { duration: 520 * d, easing: ease }),
    ),
    -1,
    false,
  );
}

function startBlink(
  mode: ReturnType<typeof liveTalkOrbMode>,
  blink: SharedValue<number>,
  ease: typeof Motion.easing.inOut,
): void {
  if (mode === "speak") {
    blink.value = withTiming(1, { duration: 80 });
    return;
  }
  const gap = mode === "listen" ? 1800 : 3200;
  const second = mode === "listen" ? 160 : 2800;
  blink.value = 1;
  blink.value = withRepeat(
    withSequence(
      withDelay(gap, withTiming(0.1, { duration: 70, easing: ease })),
      withTiming(1, { duration: 90, easing: ease }),
      withDelay(second, withTiming(0.1, { duration: 60, easing: ease })),
      withTiming(1, { duration: 90, easing: ease }),
    ),
    -1,
    false,
  );
}

function startBody(
  mode: ReturnType<typeof liveTalkOrbMode>,
  scaleX: SharedValue<number>,
  scaleY: SharedValue<number>,
  ease: typeof Motion.easing.inOut,
): void {
  if (mode !== "speak") {
    scaleX.value = withTiming(1, { duration: 180, easing: ease });
    scaleY.value = withTiming(1, { duration: 180, easing: ease });
    return;
  }
  // Irregular squash/stretch — speech rhythm, not a heartbeat.
  scaleX.value = withRepeat(
    withSequence(
      withTiming(1.1, { duration: 130, easing: ease }),
      withTiming(0.92, { duration: 150, easing: ease }),
      withTiming(1.06, { duration: 100, easing: ease }),
      withTiming(0.96, { duration: 170, easing: ease }),
      withTiming(1.03, { duration: 120, easing: ease }),
      withTiming(0.94, { duration: 140, easing: ease }),
    ),
    -1,
    false,
  );
  scaleY.value = withRepeat(
    withSequence(
      withTiming(0.9, { duration: 130, easing: ease }),
      withTiming(1.08, { duration: 150, easing: ease }),
      withTiming(0.94, { duration: 100, easing: ease }),
      withTiming(1.05, { duration: 170, easing: ease }),
      withTiming(0.97, { duration: 120, easing: ease }),
      withTiming(1.07, { duration: 140, easing: ease }),
    ),
    -1,
    false,
  );
}

function makeOrbStyles(theme: Theme) {
  return StyleSheet.create({
    stage: {
      width: STAGE,
      height: STAGE,
      alignItems: "center",
      justifyContent: "center",
    },
    halo: {
      position: "absolute",
      width: HALO,
      height: HALO,
      borderRadius: HALO / 2,
    },
    core: {
      width: CORE,
      height: CORE,
      borderRadius: CORE / 2,
      overflow: "hidden",
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: theme.primary,
    },
    fill: {
      ...StyleSheet.absoluteFill,
    },
    eyes: {
      flexDirection: "row",
      alignItems: "center",
      gap: Space.xs,
      marginTop: -14,
    },
    eye: {
      width: 11,
      height: 24,
      borderRadius: Radius.full,
      // The eyes sit mid-orb, on the accent: white on indigo (5.5:1), and near-black
      // on dark mode's pale accent (10:1), where white was 1.9:1.
      backgroundColor: theme.onPrimary,
    },
  });
}
