import { ActivityIndicator, Pressable, Text, View } from "react-native";
import { useTranslation } from "react-i18next";

import type { makeChatComposerStyles } from "@/features/chat/components/chatComposerStyles";
import { Space } from "@/lib/space";
import { useTheme } from "@/lib/theme";
import { Icon } from "@/ui/icons/Icon";
import { IconSize } from "@/ui/icons/sizes";

type ComposerStyles = ReturnType<typeof makeChatComposerStyles>;

/** The row the scan hint adds above the field, so the thread can clear it. */
export const COMPOSER_SCAN_HINT_HEIGHT = 40;

/** + opens the attach sheet; while voice is active the same slot cancels the take. */
export function ComposerAttachButton({
  s,
  voiceActive,
  disabled,
  picking = false,
  onPress,
}: {
  s: ComposerStyles;
  voiceActive: boolean;
  /** An attachment cannot be added right now (a send is preparing or a reply streams). */
  disabled: boolean;
  /** A picked file is still being prepared: the button shows it is working. */
  picking?: boolean;
  onPress: () => void;
}) {
  const { t } = useTranslation();
  const theme = useTheme();
  return (
    <Pressable
      testID="composer-attachment-button"
      style={[s.attachBtn, !voiceActive && disabled && s.controlDisabled]}
      onPress={onPress}
      disabled={!voiceActive && disabled}
      hitSlop={{ top: 14, bottom: 14, left: 14, right: 14 }}
      accessibilityRole="button"
      accessibilityLabel={t(voiceActive ? "chat.voice_cancel_a11y" : "chat.attach_a11y")}
      accessibilityState={{ disabled: !voiceActive && disabled, busy: !voiceActive && picking }}
    >
      {voiceActive ? (
        <Icon
          name="close"
          size={IconSize.md}
          color={theme.text}
          testID="composer-voice-cancel-icon"
        />
      ) : picking ? (
        <ActivityIndicator size="small" color={theme.textTertiary} testID="composer-attachment-busy" />
      ) : (
        <Icon
          name="plus"
          size={IconSize.md}
          color={theme.text}
          testID="composer-attachment-add-icon"
        />
      )}
    </Pressable>
  );
}

/** After an image-only paste: offer the math scanner instead. */
export function ComposerScanHint({
  s,
  onOpenScanner,
  onDismiss,
}: {
  s: ComposerStyles;
  onOpenScanner: () => void;
  onDismiss: () => void;
}) {
  const { t } = useTranslation();
  const theme = useTheme();
  return (
    <View style={s.scanHint}>
      <Text style={s.scanHintText}>{t("chat.math_paste_scan_hint")}</Text>
      <Pressable
        onPress={onOpenScanner}
        accessibilityRole="button"
        accessibilityLabel={t("chat.math_paste_scan_cta")}
        // A one-word link: reach the 44pt target around it.
        hitSlop={{ top: 12, bottom: 12, left: Space.xs, right: Space.xs }}
      >
        <Text style={s.scanHintCta}>{t("chat.math_paste_scan_cta")}</Text>
      </Pressable>
      <Pressable
        onPress={onDismiss}
        accessibilityRole="button"
        accessibilityLabel={t("common.cancel")}
        // A 16pt glyph: 14pt each side makes the 44pt target.
        hitSlop={14}
      >
        <Icon name="close" size={IconSize.xs} color={theme.textSecondary} />
      </Pressable>
    </View>
  );
}

/** Opens a long draft in the full-height editor, and closes it again. */
export function ComposerExpandControl({
  s,
  expanded,
  onPress,
}: {
  s: ComposerStyles;
  expanded: boolean;
  onPress: () => void;
}) {
  const { t } = useTranslation();
  const theme = useTheme();
  return (
    <View style={s.expandControlRow}>
      <Pressable
        style={s.expandControl}
        onPress={onPress}
        accessibilityRole="button"
        accessibilityLabel={t(expanded ? "rich.collapse" : "rich.expand")}
        accessibilityState={{ expanded }}
        testID="composer-expand"
      >
        <Icon
          name={expanded ? "collapse" : "expand"}
          size={IconSize.sm}
          color={theme.textSecondary}
        />
      </Pressable>
    </View>
  );
}
