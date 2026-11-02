import { Pressable, Text } from "react-native";
import Animated, { type SharedValue } from "react-native-reanimated";
import { Icon } from "@/ui/icons/Icon";
import { useTranslation } from "react-i18next";

import type { ChatScreenStyles } from "@/features/chat/components/chatScreenStyles";
import type { Theme } from "@/lib/theme";
import { IconSize } from "@/ui/icons/sizes";
import { useBottomLiftStyle } from "@/ui/hooks/useBottomLiftStyle";

type Props = {
  styles: ChatScreenStyles;
  theme: Theme;
  bottomOffset: number;
  /** Rides the keyboard with the composer, frame by frame. */
  lift?: SharedValue<number>;
  usedPct: number;
  onUpgrade: () => void;
  onDismiss: () => void;
};

export function ChatQuotaNudge({
  styles: s,
  theme,
  bottomOffset,
  lift,
  usedPct,
  onUpgrade,
  onDismiss,
}: Props) {
  const { t } = useTranslation();
  const liftStyle = useBottomLiftStyle(lift);

  return (
    <Animated.View style={[s.quotaNudge, { bottom: bottomOffset }, lift ? liftStyle : null]}>
      <Pressable style={s.quotaNudgeBody} onPress={onUpgrade} accessibilityRole="button">
        <Icon
          name="zap"
          size={IconSize.xs}
          color={theme.primary}
          style={s.quotaNudgeIcon}
        />
        <Text style={s.quotaNudgeText}>
          {t("chat.quota_nudge_body", { pct: usedPct })}
        </Text>
      </Pressable>
      <Pressable style={s.quotaNudgeCta} onPress={onUpgrade} hitSlop={{ top: 10, bottom: 10 }} accessibilityRole="button">
        <Text style={s.quotaNudgeCtaText}>{t("chat.quota_nudge_cta")}</Text>
      </Pressable>
      <Pressable onPress={onDismiss} hitSlop={{ top: 10, bottom: 10, left: 8, right: 10 }} style={s.quotaNudgeClose} accessibilityRole="button" accessibilityLabel={t("common.cancel")}>
        <Icon name="close" size={IconSize.xs} color={theme.textTertiary} />
      </Pressable>
    </Animated.View>
  );
}
