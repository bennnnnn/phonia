import { ReactNode, useMemo } from "react";
import { StyleSheet, Text, View } from "react-native";

import { Icon } from "@/ui/icons/Icon";
import { CopyButton } from "@/components/CopyButton";
import type { IconName } from "@/ui/icons/names";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import { IconSize } from "@/ui/icons/sizes";
import { PARAGRAPH_GAP } from "@/components/markdown/markdownContentStyles";

type Props = {
  label: string;
  copyText?: string;
  icon?: IconName;
  /** A logo or other drawing shown instead of `icon`. */
  leading?: ReactNode;
  iconColor?: string;
  accentColor?: string;
  /** When false, the left edge is a normal hairline — no colored stripe. */
  accent?: boolean;
  /** Extra header controls (edit, Gmail, …). Replaces the default Copy button. */
  headerActions?: ReactNode;
  testID?: string;
  children: ReactNode;
};

export function CardShell({
  label,
  copyText,
  icon,
  leading,
  iconColor,
  accentColor,
  accent = true,
  headerActions,
  testID,
  children,
}: Props) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const resolvedAccent = accentColor ?? theme.border;

  return (
    <View
      testID={testID}
      style={[
        s.wrap,
        accent ? { borderLeftColor: resolvedAccent } : s.wrapEven,
      ]}
    >
      <View style={s.header}>
        <View style={s.labelRow}>
          {leading ?? (icon ? <Icon name={icon} size={IconSize.sm} color={iconColor} /> : null)}
          <Text style={s.label}>{label}</Text>
        </View>
        <View style={s.headerActions}>
          {headerActions ??
            (copyText ? <CopyButton text={copyText} /> : null)}
        </View>
      </View>
      <View style={s.body}>{children}</View>
    </View>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    wrap: {
      alignSelf: "stretch",
      backgroundColor: t.surface,
      borderRadius: Radius.card,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: t.border,
      borderLeftWidth: 3,
      marginTop: 0,
      marginBottom: PARAGRAPH_GAP,
      overflow: "hidden",
    },
    // The same hairline as the other three sides: 1pt drew a heavier left edge.
    wrapEven: {
      borderLeftWidth: StyleSheet.hairlineWidth,
      borderLeftColor: t.border,
    },
    header: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "space-between",
      gap: Space.xs,
      paddingHorizontal: Space.sm,
      paddingTop: Space.sm,
      paddingBottom: Space.xxs,
    },
    labelRow: { flexDirection: "row", alignItems: "center", gap: Space.xs, flex: 1 },
    label: { ...Type.compact, ...Weight.semibold, color: t.textSecondary },
    headerActions: { flexDirection: "row", alignItems: "center", gap: 2 },
    body: { paddingHorizontal: Space.sm, paddingVertical: Space.sm },
  });
}
