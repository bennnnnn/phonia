import { useMemo } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import Animated, { type SharedValue } from "react-native-reanimated";
import { Icon } from "@/ui/icons/Icon";
import { useTranslation } from "react-i18next";

import type { ResolvedChatError } from "@/features/chat/model/errorMessage";
import { Radius } from "@/lib/radius";
import { shadowElevated } from "@/lib/shadow";
import { Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import { Space } from "@/lib/space";
import { IconSize } from "@/ui/icons/sizes";
import { useBottomLiftStyle } from "@/ui/hooks/useBottomLiftStyle";

type Props = {
  error: ResolvedChatError | null;
  upgradeLabel?: string;
  onUpgrade?: () => void;
  onStop?: () => void;
  onRetry?: () => void;
  onChangeModel?: () => void;
  onDismiss: () => void;
  bottom: number;
  /** Rides the keyboard with the composer, frame by frame. */
  lift?: SharedValue<number>;
};

export function ChatInlineError({
  error,
  upgradeLabel,
  onUpgrade,
  onStop,
  onRetry,
  onChangeModel,
  onDismiss,
  bottom,
  lift,
}: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const liftStyle = useBottomLiftStyle(lift);

  if (!error) return null;

  const iconName =
    error.kind === "quota"
      ? "zap"
      : error.kind === "busy" || error.kind === "send_rejected"
        ? "hourglass"
        : error.kind === "model_unavailable"
          ? "cloud-off"
          : "alert-circle";

  return (
    <Animated.View style={[s.wrap, { bottom }, lift ? liftStyle : null]}>
      <View style={s.body}>
        <Icon name={iconName} size={IconSize.xs} color={theme.warning} style={s.icon} />
        <Text style={s.text}>{error.message}</Text>
      </View>
      {error.kind === "quota" && onUpgrade && upgradeLabel ? (
        <Pressable
          style={s.cta}
          onPress={onUpgrade}
          accessibilityRole="button"
          accessibilityLabel={upgradeLabel}
        >
          <Text style={s.ctaText}>{upgradeLabel}</Text>
        </Pressable>
      ) : null}
      {error.kind === "busy" && onStop ? (
        <Pressable
          style={s.cta}
          onPress={onStop}
          accessibilityRole="button"
          accessibilityLabel={t("chat.stop_a11y")}
          testID="chat-busy-stop"
        >
          <Text style={s.ctaText}>{t("chat.stop")}</Text>
        </Pressable>
      ) : null}
      {error.kind === "send_rejected" && onRetry ? (
        <Pressable
          style={s.cta}
          onPress={onRetry}
          accessibilityRole="button"
          accessibilityLabel={t("common.retry")}
          testID="chat-error-retry"
        >
          <Text style={s.ctaText}>{t("common.retry")}</Text>
        </Pressable>
      ) : null}
      {error.kind === "generic" && onRetry ? (
        <Pressable
          style={s.cta}
          onPress={onRetry}
          accessibilityRole="button"
          accessibilityLabel={t("chat.regenerate_a11y")}
          testID="chat-error-regenerate"
        >
          <Text style={s.ctaText}>{t("chat.regenerate")}</Text>
        </Pressable>
      ) : null}
      {error.kind === "attachment_rejected" && onRetry ? (
        <Pressable
          style={s.cta}
          onPress={onRetry}
          accessibilityRole="button"
          accessibilityLabel={t("chat.restore_draft")}
          testID="chat-error-restore"
        >
          <Text style={s.ctaText}>{t("chat.restore_draft")}</Text>
        </Pressable>
      ) : null}
      {error.kind === "model_unavailable" && onChangeModel ? (
        <Pressable
          style={s.cta}
          onPress={onChangeModel}
          accessibilityRole="button"
          accessibilityLabel={t("settings.model")}
          testID="chat-error-change-model"
        >
          <Text style={s.ctaText}>{t("settings.model")}</Text>
        </Pressable>
      ) : null}
      <Pressable
        onPress={onDismiss}
        hitSlop={8}
        style={s.close}
        accessibilityRole="button"
        accessibilityLabel={t("chat.error_dismiss_a11y")}
      >
        <Icon name="close" size={IconSize.xs} color={theme.textTertiary} />
      </Pressable>
    </Animated.View>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    wrap: {
      position: "absolute",
      left: 12,
      right: 12,
      flexDirection: "row",
      alignItems: "center",
      gap: Space.xs,
      backgroundColor: theme.surface,
      borderRadius: Radius.lg,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: theme.warning,
      paddingLeft: Space.sm,
      paddingRight: Space.xs,
      paddingVertical: Space.sm,
      ...shadowElevated(theme, "banner"),
      zIndex: 20,
    },
    body: { flex: 1, flexDirection: "row", alignItems: "flex-start", gap: Space.xs },
    icon: { marginTop: 1, flexShrink: 0 },
    text: { flex: 1, ...Type.compact, color: theme.text },
    cta: {
      backgroundColor: theme.primary,
      borderRadius: Radius.full,
      paddingHorizontal: Space.sm,
      paddingVertical: Space.xs,
      minHeight: 44,
      justifyContent: "center",
      flexShrink: 0,
    },
    ctaText: { ...Type.caption, ...Weight.bold, color: theme.onPrimary },
    close: {
      width: 44,
      height: 44,
      alignItems: "center",
      justifyContent: "center",
      flexShrink: 0,
      marginVertical: -8,
      marginRight: -6,
    },
  });
}
