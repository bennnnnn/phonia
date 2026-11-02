import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { useTranslation } from "react-i18next";

import { Icon } from "../icons/Icon";
import { Button } from "../controls/Button";
import type { IconName } from "../icons/names";
import { IconSize } from "../icons/sizes";
import { tap } from "@/lib/haptics";
import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";

type Props = {
  variant: "loading" | "error" | "empty";
  title?: string;
  message?: string;
  icon?: IconName;
  onRetry?: () => void;
  retryLabel?: string;
  compact?: boolean;
};

export function StateView({
  variant,
  title,
  message,
  icon,
  onRetry,
  retryLabel,
  compact = false,
}: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = makeStyles(theme, compact);
  const resolvedRetryLabel = retryLabel ?? (onRetry ? t("common.retry") : undefined);

  if (variant === "loading") {
    return (
      <View style={s.wrap}>
        <ActivityIndicator size={compact ? "small" : "large"} color={theme.primary} />
        {title ? <Text style={s.title} accessibilityRole="header">{title}</Text> : null}
        {message ? <Text style={s.message}>{message}</Text> : null}
        {/* A long job can offer one way out ("Cancel"). */}
        {onRetry && retryLabel ? (
          <Button title={retryLabel} variant="secondary" onPress={onRetry} style={s.retryBtn} />
        ) : null}
      </View>
    );
  }

  const defaultIcon: IconName =
    variant === "error" ? "alert-circle" : "folder-open";

  return (
    <View style={s.wrap}>
      <Icon
        name={icon ?? defaultIcon}
        size={compact ? IconSize.xl : IconSize.hero}
        color={theme.textTertiary}
        style={s.icon}
      />
      {title ? <Text style={s.title} accessibilityRole="header">{title}</Text> : null}
      {message ? <Text style={s.message}>{message}</Text> : null}
      {onRetry ? (
        <Button
          title={resolvedRetryLabel ?? t("common.retry")}
          onPress={() => {
            tap();
            onRetry();
          }}
          style={s.retryBtn}
        />
      ) : null}
    </View>
  );
}

function makeStyles(theme: Theme, compact: boolean) {
  return StyleSheet.create({
    wrap: {
      flex: compact ? undefined : 1,
      alignItems: "center",
      justifyContent: "center",
      paddingVertical: compact ? Space.lg : Space.xl + Space.xs,
      paddingHorizontal: Space.lg,
      gap: Space.xs,
    },
    icon: { marginBottom: Space.xxs },
    title: {
      ...Type.navTitle,
      color: theme.text,
      textAlign: "center",
    },
    message: {
      ...Type.secondary,
      color: theme.textSecondary,
      textAlign: "center",
    },
    retryBtn: {
      marginTop: Space.xs,
      alignSelf: "center",
      paddingHorizontal: Space.lg,
    },
  });
}
