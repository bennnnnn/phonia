import { useEffect, useMemo } from "react";
import { StyleSheet, Text, View } from "react-native";
import Animated, {
  cancelAnimation,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withSequence,
  withTiming,
} from "react-native-reanimated";

import { Motion, useReduceMotion } from "@/lib/motion";
import { Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";

/** Private-use mark so the caret can sit inside the last streaming text run. */
export const STREAM_CARET = "\uE010";

export function splitStreamCaret(content: string): { text: string; caret: boolean } {
  if (!content.includes(STREAM_CARET)) return { text: content, caret: false };
  return { text: content.split(STREAM_CARET).join(""), caret: true };
}

/** Append the caret mark to the last prose line, not after a trailing break. */
export function withStreamCaret(markdown: string): string {
  if (!markdown.trim() || markdown.includes(STREAM_CARET)) return markdown;
  const trailing = /\n*$/.exec(markdown);
  const end = trailing?.index ?? markdown.length;
  const body = markdown.slice(0, end);
  if (!body.trim()) return markdown;
  return body + STREAM_CARET + markdown.slice(end);
}

const AnimatedText = Animated.createAnimatedComponent(Text);

/** Thin bar that can live inside a React Native Text run. */
const INLINE_CARET = "\u258F";

/**
 * Blinking caret shown while assistant text is streaming in.
 * `inline` is a Text glyph. A View inside Text lays out at 0×0 on iOS.
 */
export function StreamingCursor({ inline = false }: { inline?: boolean }) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const reduceMotion = useReduceMotion();
  const opacity = useSharedValue(1);

  useEffect(() => {
    if (reduceMotion) {
      cancelAnimation(opacity);
      opacity.value = 1;
      return;
    }
    opacity.value = withRepeat(
      withSequence(
        withTiming(0.15, {
          duration: Motion.duration.pulse,
          easing: Motion.easing.inOut,
        }),
        withTiming(1, {
          duration: Motion.duration.pulse,
          easing: Motion.easing.inOut,
        }),
      ),
      -1,
      false,
    );
    return () => cancelAnimation(opacity);
  }, [opacity, reduceMotion]);

  const caretStyle = useAnimatedStyle(() => ({
    opacity: opacity.value,
  }));

  if (inline) {
    return (
      <AnimatedText
        testID="stream-caret"
        style={[s.inlineCaret, caretStyle]}
        accessibilityElementsHidden
        importantForAccessibility="no"
      >
        {INLINE_CARET}
      </AnimatedText>
    );
  }

  return (
    <View
      testID="stream-caret"
      style={s.inlineWrap}
      accessibilityElementsHidden
      importantForAccessibility="no"
    >
      <Animated.View style={[s.caret, caretStyle]} />
    </View>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    inlineWrap: {
      width: 7,
      height: 18,
      justifyContent: "center",
      marginLeft: 1,
    },
    caret: {
      width: 2,
      height: 16,
      borderRadius: 1,
      backgroundColor: t.accent,
    },
    inlineCaret: {
      ...Type.body,
      color: t.accent,
    },
  });
}
