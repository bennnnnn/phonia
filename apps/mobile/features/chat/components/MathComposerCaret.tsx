import { useEffect, useMemo, useState } from "react";
import { Animated, Easing, StyleSheet } from "react-native";

import { Theme, useTheme } from "@/lib/theme";

const CARET_BLINK_MS = 450;

type Props = {
  testID?: string;
};

/** Blinking insert caret while the math pad owns the keyboard. */
export function MathComposerCaret({ testID }: Props) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const [opacity] = useState(() => new Animated.Value(1));

  useEffect(() => {
    if (process.env.NODE_ENV === "test") return;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, {
          toValue: 0.15,
          duration: CARET_BLINK_MS,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
        Animated.timing(opacity, {
          toValue: 1,
          duration: CARET_BLINK_MS,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [opacity]);

  return <Animated.View testID={testID} style={[s.caret, { opacity }]} />;
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    caret: {
      width: 2,
      height: 18,
      borderRadius: 1,
      backgroundColor: theme.primary,
    },
  });
}
