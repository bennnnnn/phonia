import { useMemo } from "react";
import {
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type ViewStyle,
} from "react-native";

import { Radius } from "@/lib/radius";
import { type Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";
import { Space } from "@/lib/space";

type CountBadgeTone = "primary" | "danger";

type Props = {
  count: number;
  max?: number;
  tone?: CountBadgeTone;
  bordered?: boolean;
  style?: StyleProp<ViewStyle>;
};

/** Compact numeric status that grows with Dynamic Type instead of clipping. */
export function CountBadge({
  count,
  max = 99,
  tone = "primary",
  bordered = false,
  style,
}: Props) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  if (count <= 0) return null;

  return (
    <View
      style={[
        s.badge,
        tone === "danger" && s.danger,
        bordered && s.bordered,
        style,
      ]}
    >
      <Text style={[s.text, tone === "danger" && s.dangerText]}>
        {count > max ? `${max}+` : String(count)}
      </Text>
    </View>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    badge: {
      minWidth: 18,
      minHeight: 18,
      borderRadius: Radius.full,
      paddingHorizontal: Space.xxs,
      backgroundColor: theme.primary,
      alignItems: "center",
      justifyContent: "center",
    },
    danger: {
      paddingHorizontal: Space.xxs,
      backgroundColor: theme.danger,
    },
    bordered: {
      borderWidth: 1.5,
      borderColor: theme.surface,
    },
    text: {
      ...Type.micro,
      color: theme.onPrimary,
    },
    dangerText: {
      color: theme.onDanger,
    },
  });
}
