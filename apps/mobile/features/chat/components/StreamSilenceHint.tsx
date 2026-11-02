import { useEffect, useMemo } from "react";
import { AccessibilityInfo, StyleSheet, Text } from "react-native";
import { useTranslation } from "react-i18next";

import { Space } from "@/lib/space";
import { type Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";

/** Under a reply that stopped growing mid-stream: still working, and Stop ends it. */
export function StreamSilenceHint() {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const text = t("chat.still_working");

  useEffect(() => {
    AccessibilityInfo.announceForAccessibility(text);
  }, [text]);

  return (
    <Text style={s.text} accessibilityLiveRegion="polite" testID="stream-silence-hint">
      {text}
    </Text>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    text: {
      ...Type.caption,
      color: theme.textSecondary,
      marginTop: Space.xxs,
      paddingHorizontal: Space.md,
    },
  });
}
