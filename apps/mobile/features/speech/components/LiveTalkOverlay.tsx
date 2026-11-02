import { useEffect, useMemo, useState } from "react";
import { AccessibilityInfo, Pressable, StyleSheet, View } from "react-native";
import Animated, {
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  withTiming,
} from "react-native-reanimated";
import { useTranslation } from "react-i18next";

import { useDrawerOpen } from "@/contexts/DrawerContext";
import { LiveTalkOrb } from "@/features/speech/components/LiveTalkOrb";
import {
  liveTalkOrbA11yHintKey,
  liveTalkOrbA11yKey,
  liveTalkOrbAction,
  liveTalkPhaseA11yKey,
  type LiveTalkPhase,
} from "@/features/speech/model/liveTalkLogic";
import { Motion, useReduceMotion } from "@/lib/motion";
import { Theme, useTheme } from "@/lib/theme";

const ENTER_SPRING = { damping: 16, stiffness: 210, mass: 0.78 };
const EXIT_MS = 280;
const EXIT_DROP_Y = 78;
const ENTER_SCALE = 0.16;

type Props = {
  visible: boolean;
  phase: LiveTalkPhase;
  recording: boolean;
  /** Leave this strip open so ChatHeader (hamburger / ⋮) stays tappable; the drawer hides the header. */
  headerInset: number;
  /** Leave the real composer (type / attach) uncovered. */
  composerClearance: number;
  onToggle: () => void;
};

export function LiveTalkOverlay({
  visible,
  phase,
  recording,
  headerInset,
  composerClearance,
  onToggle,
}: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const reduceMotion = useReduceMotion();
  const drawerOpen = useDrawerOpen();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const orbAction = liveTalkOrbAction(phase);
  const orbLabel = t(liveTalkOrbA11yKey(phase));
  const orbHint = liveTalkOrbA11yHintKey(phase);
  const [mounted, setMounted] = useState(visible);
  const appear = useSharedValue(visible ? 1 : 0);

  // The orb has no on-screen Listening or Speaking copy; a screen reader is
  // told each change instead, so a blind user knows when to talk.
  useEffect(() => {
    const key = visible ? liveTalkPhaseA11yKey(phase) : null;
    if (key) AccessibilityInfo.announceForAccessibility(t(key));
  }, [phase, t, visible]);

  useEffect(() => {
    if (visible) {
      setMounted(true);
      appear.value = reduceMotion ? 1 : withSpring(1, ENTER_SPRING);
      return;
    }
    if (reduceMotion) {
      appear.value = 0;
      setMounted(false);
      return;
    }
    appear.value = withTiming(0, { duration: EXIT_MS, easing: Motion.easing.in }, (finished) => {
      if (finished) runOnJS(setMounted)(false);
    });
  }, [appear, reduceMotion, visible]);

  const overlayStyle = useAnimatedStyle(() => ({
    opacity: appear.value,
  }));
  const orbWrapStyle = useAnimatedStyle(() => ({
    transform: [
      { translateY: (1 - appear.value) * EXIT_DROP_Y },
      { scale: ENTER_SCALE + (1 - ENTER_SCALE) * appear.value },
    ],
  }));

  if (!mounted) return null;

  const orb = (
    <LiveTalkOrb
      theme={theme}
      phase={phase}
      recording={recording}
      reduceMotion={reduceMotion}
    />
  );

  return (
    <Animated.View
      style={[s.overlay, overlayStyle, { top: drawerOpen ? 0 : headerInset, bottom: composerClearance }]}
      testID="live-talk-overlay"
      pointerEvents={visible ? "auto" : "none"}
    >
      <View style={s.body}>
        <Animated.View style={orbWrapStyle}>
          {orbAction === "none" ? (
            <View accessible accessibilityLabel={orbLabel} testID="live-talk-orb">
              {orb}
            </View>
          ) : (
            <Pressable
              onPress={onToggle}
              accessibilityRole="button"
              accessibilityLabel={orbLabel}
              accessibilityHint={orbHint ? t(orbHint) : undefined}
              testID="live-talk-orb"
            >
              {orb}
            </Pressable>
          )}
        </Animated.View>
      </View>
    </Animated.View>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    overlay: {
      position: "absolute",
      left: 0,
      right: 0,
      zIndex: 120,
    },
    body: {
      flex: 1,
      backgroundColor: theme.bg,
      alignItems: "center",
      justifyContent: "center",
    },
  });
}
