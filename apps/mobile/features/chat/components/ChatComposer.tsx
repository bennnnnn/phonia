import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  useWindowDimensions,
  View,
  type ViewStyle,
} from "react-native";
import Animated, {
  useAnimatedKeyboard,
  useAnimatedStyle,
  type AnimatedStyle,
} from "react-native-reanimated";
import * as Clipboard from "expo-clipboard";
import { LinearGradient } from "expo-linear-gradient";
import {
  BOTTOM_CHROME_FADE_LOCATIONS,
  bottomChromeFadeColors,
} from "@/features/chat/components/chromeFade";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Icon } from "@/ui/icons/Icon";
import { useTranslation } from "react-i18next";

import { LiveTalkComposerControls } from "@/features/speech/components/LiveTalkComposerControls";
import { type MeterLevel, VoiceComposerWaveform } from "@/features/speech/components/VoiceComposerWaveform";
import {
  MathDraftPreview,
  MATH_DRAFT_PREVIEW_HEIGHT,
} from "@/features/chat/components/MathDraftPreview";
import {
  ComposerAttachButton,
  ComposerExpandControl,
  ComposerScanHint,
  COMPOSER_SCAN_HINT_HEIGHT,
} from "@/features/chat/components/ComposerControls";
import { ComposerSendControls } from "@/features/chat/components/ComposerSendControls";
import { ComposerTextMeasure } from "@/features/chat/components/ComposerTextMeasure";
import { MathComposerCaret } from "@/features/chat/components/MathComposerCaret";
import { MathKeyboardBar } from "@/features/chat/components/MathKeyboardBar";
import { makeChatComposerStyles } from "@/features/chat/components/chatComposerStyles";
import { ComposerAttachmentPreview } from "@/features/attachments/components/ComposerAttachmentPreview";
import {
  useComposerDraftApiOptional,
  useComposerDraftValueOptional,
} from "@/features/chat/context/ComposerDraftContext";
import { useAuthToken } from "@/contexts/AuthContext";
import { useComposerFieldLayout } from "@/features/chat/hooks/useComposerFieldLayout";
import { useMathKeyboardInsert } from "@/features/chat/hooks/useMathKeyboardInsert";
import type { PendingAttachment } from "@/features/attachments/model/attachments";
import {
  CHAT_COMPOSER_MIN_BOTTOM_PAD,
  COMPOSER_GAP_FADE_OVERLAP,
  composerNativeInputTraits,
  composerShowsMic,
  composerShowsSend,
} from "@/features/chat/model/composerLogic";
import { liveTalkShowsSideChrome } from "@/features/speech/model/liveTalkLogic";
import { caretAfterExpression, caretBeforeExpression } from "@/lib/math/draftSlots";
import { Space } from "@/lib/space";
import { useTheme, withAlpha } from "@/lib/theme";
import { DYNAMIC_TYPE_MAX } from "@/lib/type";
import { IconSize } from "@/ui/icons/sizes";

function noopComposerInput(_text: string) {}

const GAP_FADE_LOCATIONS = [0, 1] as const;

/** Washed out at both ends. A clear stop left a sharp line directly under the pill. */
function gapFadeColors(bg: string): [string, string] {
  return [withAlpha(bg, 0.92), bg];
}

// 36 pt row + 4 pt card padding above and below + 6 pt shell air above and below.
export const COMPOSER_HEIGHT = 56;
const COMPOSER_STATUS_LINE_HEIGHT = 18;

/** Mic mute and close beside the real composer while live talk is open. */
export type LiveTalkComposerChrome = {
  muted: boolean;
  onClose: () => void;
  onMutePress: () => void;
  /** The user went back to the composer (focus, attach, send): live talk closes. */
  onYield: () => void;
};

type Props = {
  visible: boolean;
  animatedContainerStyle?: AnimatedStyle<ViewStyle>;
  streaming: boolean;
  /** A picked file is still being prepared: Send and Attach wait for it. */
  attachPicking?: boolean;
  sendBusy?: boolean;
  sendStatus?: string;
  pendingAttachment: PendingAttachment | null;
  onRemoveAttachment: () => void;
  onCloseAttachSheet: () => void;
  onPickAttachment: () => void;
  onSend: (text?: string) => void;
  onStop: () => void;
  isOffline: boolean;
  voiceAvailable?: boolean;
  voiceRecording?: boolean;
  voiceTranscribing?: boolean;
  voiceMeterLevel?: MeterLevel;
  onVoicePress?: () => void;
  /** Drops the open mic take, including a transcription already in flight. */
  onCancelVoice?: () => void;
  onLiveTalkPress?: () => void;
  liveTalkChrome?: LiveTalkComposerChrome | null;
  onOpenMathScanner?: () => void;
  onMathChromeHeightChange?: (height: number) => void;
  /** Extra field height past one line, so the thread moves up with the pill. */
  onInputFrameExtraChange?: (extra: number) => void;
};

export const ChatComposer = memo(function ChatComposer({
  visible,
  animatedContainerStyle,
  streaming,
  attachPicking = false,
  sendBusy = false,
  sendStatus,
  pendingAttachment,
  onRemoveAttachment,
  onCloseAttachSheet,
  onPickAttachment,
  onSend,
  onStop,
  isOffline,
  voiceAvailable = false,
  voiceRecording = false,
  voiceTranscribing = false,
  voiceMeterLevel,
  onVoicePress,
  onCancelVoice,
  onLiveTalkPress,
  liveTalkChrome = null,
  onOpenMathScanner,
  onMathChromeHeightChange,
  onInputFrameExtraChange,
}: Props) {
  const { t } = useTranslation();
  const token = useAuthToken();
  const insets = useSafeAreaInsets();
  // Native text scales the field's line box with the system text size.
  const { fontScale } = useWindowDimensions();
  const theme = useTheme();
  const s = useMemo(() => makeChatComposerStyles(theme), [theme]);
  const draft = useComposerDraftValueOptional();
  const draftApi = useComposerDraftApiOptional();
  const input = draft?.input ?? "";
  const onChangeInput = draftApi ? draftApi.typeInput : noopComposerInput;
  const [scanHint, setScanHint] = useState(false);
  const inputRef = useRef<TextInput>(null);
  const math = useMathKeyboardInsert({
    input,
    draftRevision: draft?.revision,
    setInput: onChangeInput,
    onImageOnlyPaste: onOpenMathScanner ? () => setScanHint(true) : undefined,
  });
  const showMathPreview = math.showMathPreview;
  const mathBarOpen = math.mathBarOpen;
  const toggleMathBar = math.toggleMathBar;
  const showMathButton = !mathBarOpen;
  const mathChromeHeight =
    (math.mathBarOpen ? math.padHeight : 0) +
    (showMathPreview ? MATH_DRAFT_PREVIEW_HEIGHT : 0) +
    (scanHint ? COMPOSER_SCAN_HINT_HEIGHT : 0) +
    (sendStatus ? COMPOSER_STATUS_LINE_HEIGHT : 0);

  // Kept while the drawer hides the composer, so opening it does not re-lay out the chat.
  useEffect(() => {
    onMathChromeHeightChange?.(mathChromeHeight);
  }, [mathChromeHeight, onMathChromeHeightChange]);

  useEffect(() => {
    if (!math.mathBarOpen) return;
    const id = requestAnimationFrame(() => inputRef.current?.focus());
    return () => cancelAnimationFrame(id);
  }, [math.mathBarOpen]);

  // The system keyboard dismisses on send and stays down while a reply streams.
  // The math pad is not a system keyboard, so close it the same way.
  useEffect(() => {
    if (!streaming || !math.mathBarOpen) return;
    toggleMathBar();
  }, [streaming, math.mathBarOpen, toggleMathBar]);

  // Scanner/expanded chrome belongs to the active draft, not the mounted screen.
  // Switching threads can keep ChatComposer mounted, so clear transient UI explicitly.
  useEffect(() => {
    setScanHint(false);
  }, [draft?.revision]);

  const voiceActive = voiceRecording || voiceTranscribing;
  const {
    composerExpanded,
    toggleExpanded,
    inputContentWidth,
    onTextMeasure,
    field,
    textBoxHeight,
    fieldOverflows,
    singleLineComposer,
    showExpandControl,
    stackedLayout,
    onInputLayout,
    onInputContentSizeChange,
  } = useComposerFieldLayout({
    input,
    draftRevision: draft?.revision,
    fontScale,
    voiceActive,
    onInputFrameExtraChange,
  });

  const bottomPad = Math.max(insets.bottom, CHAT_COMPOSER_MIN_BOTTOM_PAD);
  const keyboard = useAnimatedKeyboard();
  const gapFadeStyle = useAnimatedStyle(() => {
    "worklet";
    // The math pad fills the home-indicator gap. A scrim there would paint
    // across the keys instead of the messages above the pill.
    const pad =
      keyboard.height.value > 0 || composerExpanded || mathBarOpen ? 0 : bottomPad;
    // Inline the height. Calling an imported helper here runs on the UI
    // thread and aborts the app.
    const height = pad <= 0 ? 0 : pad * 2 + COMPOSER_GAP_FADE_OVERLAP;
    return {
      height,
      bottom: pad > 0 ? -pad : 0,
    };
  }, [bottomPad, composerExpanded, mathBarOpen]);

  const onToggleMathBar = useCallback(() => {
    if (streaming && !mathBarOpen) return;
    const wasOpen = mathBarOpen;
    toggleMathBar();
    if (wasOpen) {
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [mathBarOpen, streaming, toggleMathBar]);

  const sendAndCloseMath = useCallback(
    (text?: string) => {
      if (math.mathBarOpen) toggleMathBar();
      onSend(text);
    },
    [math.mathBarOpen, onSend, toggleMathBar],
  );

  if (!visible) return null;

  const hasSendableContent = Boolean(input.trim() || pendingAttachment);
  const attachmentDisabled = attachPicking || sendBusy || streaming;
  const showLiveTalkSideChrome =
    Boolean(liveTalkChrome) && liveTalkShowsSideChrome(input);
  const parkInput = showMathPreview;
  const showEmptyCaret = math.mathBarOpen && !showMathPreview && !input.trim();
  const showMic = composerShowsMic({
    voiceAvailable: Boolean(voiceAvailable && onVoicePress && token && !liveTalkChrome),
    voiceRecording,
    voiceTranscribing,
    hasSendableContent,
  });
  const showSend = composerShowsSend({
    voiceRecording,
    voiceTranscribing,
    hasSendableContent,
  });
  const blockStyle = s.composerBlock;
  const expandedBlockStyle = composerExpanded
    ? [s.composerBlockExpanded, { top: insets.top + Space.xs }]
    : null;
  const containerStyle = animatedContainerStyle
    ? [blockStyle, animatedContainerStyle, expandedBlockStyle]
    : [blockStyle, expandedBlockStyle];
  const attachButton = (
    <ComposerAttachButton
      s={s}
      voiceActive={voiceActive}
      disabled={attachmentDisabled}
      picking={attachPicking}
      onPress={() => {
        if (voiceActive) {
          onCancelVoice?.();
          return;
        }
        liveTalkChrome?.onYield();
        onPickAttachment();
      }}
    />
  );
  const trailingControls = (
    <View style={s.trailingControls}>
      {showMathButton ? (
        <Pressable
          onPress={onToggleMathBar}
          style={({ pressed }) => [s.attachBtn, pressed && s.controlDisabled]}
          accessibilityRole="button"
          accessibilityLabel={t("chat.math_keyboard_show")}
          testID="math-keyboard-toggle"
          hitSlop={4}
        >
          <Icon name="calculator" size={IconSize.sm} color={theme.text} />
        </Pressable>
      ) : null}
      <ComposerSendControls
        s={s}
        streaming={streaming}
        onStop={onStop}
        onSend={() => sendAndCloseMath()}
        showSend={showSend}
        sendBusy={sendBusy}
        isOffline={isOffline}
        attachBusy={attachPicking}
        showMic={showMic}
        voiceRecording={voiceRecording}
        voiceTranscribing={voiceTranscribing}
        onVoicePress={onVoicePress}
        onLiveTalkPress={onLiveTalkPress}
        liveTalkOpen={Boolean(liveTalkChrome)}
      />
    </View>
  );

  return (
    <Animated.View
      style={containerStyle}
      pointerEvents="box-none"
      testID="chat-composer"
    >
      <Animated.View
        pointerEvents="none"
        style={[s.bottomFade, gapFadeStyle]}
        testID="composer-bottom-fade"
      >
        <LinearGradient
          colors={gapFadeColors(theme.bg)}
          locations={[...GAP_FADE_LOCATIONS]}
          style={StyleSheet.absoluteFill}
        />
      </Animated.View>
      <View style={[s.composerAnchor, composerExpanded && s.expandedFill]}>
        <View style={[s.composer, composerExpanded && s.expandedFill]}>
          {scanHint && onOpenMathScanner ? (
            <ComposerScanHint
              s={s}
              onOpenScanner={() => {
                setScanHint(false);
                onOpenMathScanner();
              }}
              onDismiss={() => setScanHint(false)}
            />
          ) : null}
          <View style={[s.inputStack, composerExpanded && s.expandedFill]}>
          <View
            style={[
              showLiveTalkSideChrome ? s.liveTalkRow : null,
              composerExpanded && s.expandedFill,
            ]}
          >
          <View
            testID="composer-surface"
            style={[
              s.inputWrap,
              showLiveTalkSideChrome ? s.inputWrapFlex : null,
              composerExpanded && s.inputWrapExpanded,
            ]}
          >
            {pendingAttachment ? (
              <ComposerAttachmentPreview
                attachment={pendingAttachment}
                uploading={attachPicking}
                onRemove={onRemoveAttachment}
              />
            ) : null}
            {showExpandControl ? (
              <ComposerExpandControl
                s={s}
                expanded={composerExpanded}
                onPress={() => {
                  toggleExpanded();
                  requestAnimationFrame(() => inputRef.current?.focus());
                }}
              />
            ) : null}
            <View
              testID="composer-input-row"
              style={[
                s.inputRowMain,
                singleLineComposer && !stackedLayout && s.inputRowMainSingleLine,
                composerExpanded && s.inputRowMainExpanded,
              ]}
            >
              {stackedLayout ? null : attachButton}
              {voiceRecording || voiceTranscribing ? (
                <VoiceComposerWaveform
                  recording={voiceRecording}
                  transcribing={voiceTranscribing}
                  meterLevel={voiceMeterLevel}
                />
              ) : (
                <Pressable
                  style={[
                    s.inputField,
                    // Keeps one line on the button midline. Extra lines grow above the caret.
                    { paddingBottom: field.slack / 2 },
                    composerExpanded && s.inputFieldExpanded,
                  ]}
                  testID="chat-composer-field"
                  accessible={false} // a tap area; screen readers reach the text field inside
                  onPress={() => {
                    if (math.mathBarOpen || showMathPreview) return;
                    if (math.resumeMathOnFocus) math.openMathBar();
                  }}
                >
                  {showMathPreview ? (
                    <MathDraftPreview
                      input={input}
                      caret={math.selection.start}
                      onMoveCaret={(pos) => {
                        if (math.mathBarOpen) {
                          math.moveCaret(pos);
                          return;
                        }
                        const before = caretBeforeExpression(input);
                        const after = caretAfterExpression(input);
                        if (pos <= before) math.moveCaret(0);
                        else if (pos >= after) math.moveCaret(input.length);
                        else math.moveCaret(pos);
                      }}
                    />
                  ) : null}
                  <ComposerTextMeasure
                    text={input}
                    width={inputContentWidth}
                    onMeasure={onTextMeasure}
                  />
                  <TextInput
                    ref={inputRef}
                    testID="chat-composer-input"
                    style={[
                      s.input,
                      composerExpanded
                        ? s.inputExpanded
                        : {
                            height: textBoxHeight,
                            minHeight: textBoxHeight,
                            maxHeight: field.max,
                            paddingTop: 0,
                            paddingBottom: 0,
                            textAlignVertical: "top" as const,
                          },
                      parkInput ? s.inputParked : null,
                    ]}
                    placeholder={showMathPreview ? "" : t("chat.placeholder")}
                    placeholderTextColor={theme.textDisabled}
                    accessibilityLabel={t("chat.placeholder")}
                    maxFontSizeMultiplier={DYNAMIC_TYPE_MAX}
                    value={input}
                    // Messaging traits while the system keyboard is up. The math
                    // pad dismisses that keyboard before it takes the field, so
                    // correction does not flip mid-word inside one native session.
                    {...composerNativeInputTraits(math.mathBarOpen || showMathPreview)}
                    onChangeText={math.onChangeText}
                    onLayout={onInputLayout}
                    onContentSizeChange={onInputContentSizeChange}
                    scrollEnabled={fieldOverflows && !composerExpanded}
                    onSelectionChange={math.onSelectionChange}
                    selection={
                      showMathPreview
                        ? (math.forcedSelection ?? math.selection)
                        : undefined
                    }
                    caretHidden={showMathPreview || math.mathBarOpen}
                    pointerEvents={parkInput || math.mathBarOpen ? "none" : "auto"}
                    showSoftInputOnFocus={!math.resumeMathOnFocus}
                    onFocus={() => {
                      onCloseAttachSheet();
                      liveTalkChrome?.onYield();
                      math.onComposerFocus();
                    }}
                    multiline
                    returnKeyType="default"
                  />
                  {showEmptyCaret ? (
                    <View style={s.emptyCaret} pointerEvents="none">
                      <MathComposerCaret testID="math-composer-caret" />
                    </View>
                  ) : null}
                </Pressable>
              )}
              {stackedLayout ? null : trailingControls}
            </View>
            {stackedLayout ? (
              <View style={s.stackedControlsRow} testID="composer-stacked-controls">
                {attachButton}
                {trailingControls}
              </View>
            ) : null}
            {sendStatus ? (
              <Text
                style={s.sendStatus}
                testID="composer-send-status"
                accessibilityRole="text"
                accessibilityLiveRegion="polite"
              >
                {sendStatus}
              </Text>
            ) : null}
          </View>
          {liveTalkChrome && showLiveTalkSideChrome ? (
            <LiveTalkComposerControls
              muted={liveTalkChrome.muted}
              onMutePress={liveTalkChrome.onMutePress}
              onClose={liveTalkChrome.onClose}
            />
          ) : null}
          </View>
          {mathBarOpen && !composerExpanded ? (
            <LinearGradient
              pointerEvents="none"
              colors={bottomChromeFadeColors(theme) as [string, string, ...string[]]}
              locations={[...BOTTOM_CHROME_FADE_LOCATIONS]}
              style={[s.keyboardGapFade, { bottom: math.padHeight }]}
              testID="composer-scroll-fade"
            />
          ) : null}
          {math.mathBarOpen ? (
            <MathKeyboardBar
              open
              height={math.padHeight}
              onToggle={onToggleMathBar}
              onInsert={math.insertSymbol}
              onCaret={math.stepCaret}
              onAsk={sendAndCloseMath}
              onStop={onStop}
              streaming={streaming}
              onBackspace={math.backspace}
              onPaste={() => {
                void Clipboard.getStringAsync().then((text) => {
                  if (text) void math.pasteText(text);
                });
              }}
              group={math.mathGroup}
              onGroupChange={math.setMathGroup}
            />
          ) : null}
        </View>
        </View>
      </View>
    </Animated.View>
  );
});
