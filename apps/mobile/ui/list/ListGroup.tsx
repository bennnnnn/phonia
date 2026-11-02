import { useMemo, type ReactNode } from "react";
import { StyleSheet, Text, View, type StyleProp, type ViewStyle } from "react-native";

import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { type Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";

/**
 * Grouped ListRows under an optional heading: one rounded block, rows
 * separated by thin gaps (put a ListSeparator between rows).
 */
export function ListGroup({
  label,
  children,
  spaced = false,
  style,
  testID,
}: {
  label?: string;
  children: ReactNode;
  /** Put the thin gap between every row, instead of placing ListSeparators. */
  spaced?: boolean;
  style?: StyleProp<ViewStyle>;
  testID?: string;
}) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  return (
    <View style={style} testID={testID}>
      {label ? (
        <Text style={s.label} accessibilityRole="header">
          {label}
        </Text>
      ) : null}
      <View style={[s.group, spaced && s.spaced]}>{children}</View>
    </View>
  );
}

/**
 * Between two rows. `grouped` (default): the thin gap inside a ListGroup.
 * `plain`: a 1pt line for plain rows on the page, indented by `inset` so it
 * starts under the text rather than under the leading art.
 */
export function ListSeparator({
  appearance = "grouped",
  inset = 0,
}: {
  appearance?: "grouped" | "plain";
  inset?: number;
} = {}) {
  const theme = useTheme();
  if (appearance === "plain") {
    return <View style={{ height: 1, marginLeft: inset, backgroundColor: theme.separator }} />;
  }
  return <View style={{ height: 2, backgroundColor: theme.bg }} />;
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    label: {
      ...Type.secondary,
      color: t.textSecondary,
      marginHorizontal: Space.md,
      marginBottom: Space.sm,
    },
    group: {
      backgroundColor: t.bg,
      borderRadius: Radius.xl,
      overflow: "hidden",
    },
    spaced: { gap: 2 },
  });
}
