import { ActivityIndicator, Pressable, View } from "react-native";
import { useTranslation } from "react-i18next";

import type { makeChatComposerStyles } from "@/features/chat/components/chatComposerStyles";
import { COMPOSER_CONTROL_SIZE } from "@/features/chat/model/composerLogic";
import { VoiceMicButton } from "@/features/speech/components/VoiceMicButton";
import { useTheme } from "@/lib/theme";
import { Icon } from "@/ui/icons/Icon";
import { IconSize } from "@/ui/icons/sizes";

type Props = {
  s: ReturnType<typeof makeChatComposerStyles>;
  streaming: boolean;
  onStop: () => void;
  onSend: () => void;
  showSend: boolean;
  sendBusy: boolean;
  isOffline: boolean;
  /** A picked file is still being prepared: send and the mic wait for it. */
  attachBusy: boolean;
  showMic: boolean;
  voiceRecording: boolean;
  voiceTranscribing: boolean;
  onVoicePress?: () => void;
};

/** Stop while a reply streams; otherwise mic or send, whichever the draft calls for. */
export function ComposerSendControls({
  s,
  streaming,
  onStop,
  onSend,
  showSend,
  sendBusy,
  isOffline,
  attachBusy,
  showMic,
  voiceRecording,
  voiceTranscribing,
  onVoicePress,
}: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  if (streaming) {
    return (
      <View style={s.sendBtnSlot}>
        <Pressable
          style={s.sendBtn}
          onPress={onStop}
          hitSlop={6}
          accessibilityRole="button"
          accessibilityLabel={t("chat.stop_a11y")}
        >
          <Icon name="stop" size={IconSize.xxs} color={theme.onPrimary} />
        </Pressable>
      </View>
    );
  }
  const sendDisabled = isOffline || sendBusy || attachBusy;
  return (
    <View style={s.sendBtnSlot}>
      {showMic && onVoicePress ? (
        <VoiceMicButton
          size={COMPOSER_CONTROL_SIZE}
          recording={voiceRecording}
          transcribing={voiceTranscribing}
          disabled={attachBusy || sendBusy || isOffline}
          onPress={onVoicePress}
        />
      ) : null}
      {showSend || sendBusy ? (
        <Pressable
          style={[s.sendBtn, sendDisabled && s.sendBtnDisabled]}
          onPress={onSend}
          disabled={sendDisabled}
          hitSlop={6}
          accessibilityRole="button"
          accessibilityLabel={sendBusy ? t("chat.sending") : t("chat.send_a11y")}
          accessibilityHint={isOffline ? t("chat.offline_body") : undefined}
          accessibilityState={{ disabled: sendDisabled, busy: sendBusy }}
        >
          {sendBusy ? (
            <ActivityIndicator size="small" color={theme.textTertiary} />
          ) : (
            <Icon
              name="arrow-up"
              size={IconSize.sm}
              color={isOffline ? theme.textTertiary : theme.onPrimary}
            />
          )}
        </Pressable>
      ) : null}
    </View>
  );
}
