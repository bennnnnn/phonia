import { useMemo } from "react";
import { StyleSheet, View } from "react-native";

import { SkeletonBlock } from "@/ui/feedback/SkeletonLoader";
import { Space } from "@/lib/space";
import { type Theme, useTheme } from "@/lib/theme";
import { Radius } from "@/lib/radius";

export function SettingsSkeleton({
  rows = 3,
  contained = false,
  accessibilityLabel,
}: {
  rows?: number;
  contained?: boolean;
  accessibilityLabel?: string;
}) {
  const theme = useTheme();
  const styles = useMemo(() => makeStyles(theme), [theme]);

  return (
    <View
      testID="settings-loading-skeleton"
      style={[styles.root, contained ? styles.contained : styles.screen]}
      accessible
      accessibilityRole="progressbar"
      accessibilityLabel={accessibilityLabel}
      accessibilityState={{ busy: true }}
    >
      {Array.from({ length: rows }, (_, index) => (
        <View key={index} style={styles.row}>
          <View style={styles.copy} accessibilityElementsHidden>
            <SkeletonBlock width={index % 2 === 0 ? "64%" : "52%"} height={16} />
            <SkeletonBlock width={index % 2 === 0 ? "42%" : "70%"} height={12} />
          </View>
          <SkeletonBlock width={42} height={24} borderRadius={12} />
        </View>
      ))}
    </View>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    root: {
      gap: 2,
      backgroundColor: theme.bg,
    },
    screen: {
      flex: 1,
      paddingHorizontal: Space.gutter,
      paddingTop: Space.xl,
    },
    contained: {
      width: "100%",
    },
    row: {
      minHeight: 68,
      flexDirection: "row",
      alignItems: "center",
      gap: Space.gutter,
      paddingHorizontal: Space.gutter,
      paddingVertical: Space.gutter,
      borderRadius: Radius.row,
      backgroundColor: theme.settingsSurface,
    },
    copy: {
      flex: 1,
      gap: Space.xs,
    },
  });
}
