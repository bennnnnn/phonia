import { lazy, Suspense, useMemo } from "react";
import { Text, View } from "react-native";

import { useTheme } from "@/lib/theme";
import type { ActionShimmerProps } from "./ActionShimmerMotion";
import { makeActionShimmerStyles } from "./actionShimmerStyles";

const LazyActionShimmerMotion = lazy(() => import("./ActionShimmerMotion"));

/**
 * Indeterminate action progress. The label remains readable immediately; the
 * sweep starts after a short delay so fast actions do not flash animation.
 */
export function ActionShimmer(props: ActionShimmerProps) {
  const { label, color, compact = false, style, textStyle, testID } = props;
  const theme = useTheme();
  const s = useMemo(() => makeActionShimmerStyles(theme), [theme]);
  const ink = color ?? theme.primary;

  return (
    <Suspense
      fallback={
        <View
          testID={testID}
          style={[s.wrap, compact && s.compact, style]}
          accessibilityRole="progressbar"
          accessibilityLabel={label}
          accessibilityLiveRegion="polite"
        >
          <View style={[s.dot, { backgroundColor: ink }]} />
          <Text style={[s.label, { color: ink }, textStyle]} numberOfLines={1}>
            {label}
          </Text>
        </View>
      }
    >
      <LazyActionShimmerMotion {...props} />
    </Suspense>
  );
}
