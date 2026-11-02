import { useMemo } from "react";
import { Pressable, StyleSheet, Text } from "react-native";
import { useTranslation } from "react-i18next";

import { Icon } from "@/ui/icons/Icon";
import { Space } from "@/lib/space";
import { useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";
import { IconSize } from "@/ui/icons/sizes";

type Props = {
  onRetry: () => void;
  /** Hide the word "Retry" on tiny thumbs; a11y label still reads it. */
  compact?: boolean;
  /** On a media stage (the photo viewer's black): white ink in both schemes. */
  media?: boolean;
};

export function MediaLoadRetry({ onRetry, compact = false, media = false }: Props) {
  const C = useTheme();
  const { t } = useTranslation();
  const ink = media ? C.onMedia : C.textSecondary;
  const s = useMemo(() => makeStyles(ink), [ink]);

  return (
    <Pressable
      onPress={onRetry}
      accessibilityRole="button"
      accessibilityLabel={t("common.retry")}
      testID="media-load-retry"
      style={s.btn}
    >
      <Icon
        name="refresh"
        size={compact ? IconSize.sm : IconSize.lg}
        color={ink}
        testID="media-load-retry-icon"
      />
      {compact ? null : <Text style={s.label}>{t("common.retry")}</Text>}
    </Pressable>
  );
}

function makeStyles(ink: string) {
  return StyleSheet.create({
    btn: {
      alignItems: "center",
      justifyContent: "center",
      gap: Space.xxs,
      minWidth: Space.minTouch,
      minHeight: Space.minTouch,
      paddingHorizontal: Space.xs,
      paddingVertical: Space.xxs,
    },
    label: {
      ...Type.caption,
      color: ink,
    },
  });
}
