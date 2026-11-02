import { memo, ReactElement, RefObject, useCallback, useEffect, useMemo } from "react";
import { View, type NativeScrollEvent, type NativeSyntheticEvent, type ViewStyle } from "react-native";
import { FlashListRef, ListRenderItemInfo } from "@shopify/flash-list";
import { type AnimatedStyle, type SharedValue } from "react-native-reanimated";

import { ActionBanner } from "@/ui/feedback/ActionBanner";
import { AttachmentSourceSheet } from "@/features/attachments/components/AttachmentSourceSheet";
import { LazyMathEquationScanner } from "@/features/scanner/components/LazyMathEquationScanner";
import { ChatComposer, type LiveTalkComposerChrome } from "@/features/chat/components/ChatComposer";
import { ChatInlineError } from "@/features/chat/components/ChatInlineError";
import { ChatMessageList } from "@/features/chat/components/ChatMessageList";
import { ChatQuotaNudge } from "@/features/chat/components/ChatQuotaNudge";
import type { ChatScreenStyles } from "@/features/chat/components/chatScreenStyles";
import { ChatScrollFab } from "@/features/chat/components/ChatScrollFab";
import { composerShowsStop } from "@/features/chat/model/composerLogic";
import type { ChatListScroll } from "@/features/chat/hooks/useChatScroll";
import { UpgradeSheet, type UpgradeSource } from "@/features/billing/components/UpgradeSheet";
import { StreamingDraftProvider } from "@/features/chat/context/StreamingDraftContext";
import { useTranslation } from "react-i18next";
import type { AttachmentSource } from "@/features/attachments/components/AttachmentSourceSheet";
import type { Message, ScanReading } from "@/lib/api";
import type { PendingAttachment } from "@/features/attachments/model/attachments";
import type { ReadBackSubject } from "@/features/scanner/model/readBack";
import type { ScannerSubject } from "@/lib/scanner/subjects";
import type { ResolvedChatError } from "@/features/chat/model/errorMessage";
import type { IconName } from "@/ui/icons/names";
import type { Theme } from "@/lib/theme";
import { useDrawerOpen } from "@/contexts/DrawerContext";
import { ChatKeyboardSpacer } from "@/features/chat/components/ChatKeyboardSpacer";

export interface ChatScreenLayoutProps {
  styles: ChatScreenStyles;
  theme: Theme;
  /** Clearance above the composer with the keyboard down; chrome above it rides `keyboardLift`. */
  restingComposerClearance: number;
  headerInset: number;
  /** The list's bottom pad with the keyboard down; a spacer under the list adds `keyboardLift`. */
  restingListBottomPad: number;
  /** How far the keyboard lifts the composer, frame by frame on the UI thread. */
  keyboardLift: SharedValue<number>;
  emptyHeight: number;
}

export interface ChatScreenListProps {
  listRef: RefObject<FlashListRef<Message> | null>;
  messages: Message[];
  hasMoreOlder: boolean;
  loadingOlder: boolean;
  newerPage: { loading: boolean; load: () => Promise<void> } | null;
  chatLoading: boolean;
  routeChatId?: string;
  renderItem: (info: ListRenderItemInfo<Message>) => ReactElement | null;
  onLoadOlder: () => void;
  onScroll: (event: NativeSyntheticEvent<NativeScrollEvent>) => void;
  onScrollEnd: () => void;
  scroll?: ChatListScroll;
  header: ReactElement | null;
}

export interface ChatScreenComposerProps {
  animatedStyle?: AnimatedStyle<ViewStyle>;
  streaming: boolean;
  /** The reply's text is all in and only its save is left: Send works, Stop is gone. */
  replySaving: boolean;
  attachPicking: boolean;
  sendBusy: boolean;
  sendStatus?: string;
  pendingAttachment: PendingAttachment | null;
  onRemoveAttachment: () => void;
  onPickAttachment: () => void;
  onOpenMathScanner?: () => void;
  onMathChromeHeightChange?: (height: number) => void;
  onInputFrameExtraChange?: (extra: number) => void;
  onSend: (text?: string) => void;
  onStop: () => void;
  isOffline: boolean;
  voiceAvailable: boolean;
  voiceRecording: boolean;
  voiceTranscribing: boolean;
  voiceMeterLevel: SharedValue<number>;
  onVoicePress?: () => void;
  onCancelVoice?: () => void;
  onLiveTalkPress?: () => void;
  liveTalkSession?: LiveTalkComposerChrome | null;
}

export interface ChatScreenChromeProps {
  actionBanner: {
    message: string;
    icon?: IconName;
  } | null;
  onDismissActionBanner: () => void;
  showScrollToBottom: boolean;
  scrollAwayCount: number;
  onScrollToLatest: () => void;
  quotaNudgeVisible: boolean;
  quotaUsedPct: number;
  onQuotaUpgrade: () => void;
  onQuotaDismiss: () => void;
  chatError: ResolvedChatError | null;
  isPaid: boolean;
  onUpgrade: () => void;
  onRetryChatError: () => void;
  onChangeModel: () => void;
  onDismissChatError: () => void;
}

export interface ChatScreenSheetsProps {
  attachSheetOpen: boolean;
  onCloseAttachSheet: () => void;
  onAttachmentSource: (source: AttachmentSource) => void;
  mathScannerOpen: boolean;
  onCloseMathScanner: () => void;
  onMathScanCaptured: (
    pending: PendingAttachment,
    subject: ScannerSubject,
    confirmedReading?: string,
  ) => void;
  onReadScan: (
    scan: PendingAttachment,
    subject: ReadBackSubject,
    signal: AbortSignal,
  ) => Promise<ScanReading | { error: string } | null>;
  onMathScanSolve: (reading: string, subject: ScannerSubject) => void;
  upgradeVisible: boolean;
  /** Where the paywall was opened from (analytics only). */
  upgradeSource?: UpgradeSource;
  onCloseUpgrade: () => void;
}

export interface ChatScreenBodyProps {
  layout: ChatScreenLayoutProps;
  list: ChatScreenListProps;
  composer: ChatScreenComposerProps;
  chrome: ChatScreenChromeProps;
  sheets: ChatScreenSheetsProps;
}

export const ChatScreenBody = memo(function ChatScreenBody({
  layout,
  list,
  composer,
  chrome,
  sheets,
}: ChatScreenBodyProps) {
  const { t } = useTranslation();
  const drawerOpen = useDrawerOpen();
  const { styles: s, keyboardLift } = layout;
  const { messages } = list;
  const { liveTalkSession, onSend } = composer;
  const { mathScannerOpen, onCloseMathScanner } = sheets;
  const handleComposerSend = useCallback(
    (text?: string) => {
      liveTalkSession?.onYield();
      onSend(text);
    },
    [liveTalkSession, onSend],
  );

  useEffect(() => {
    if (drawerOpen && mathScannerOpen) onCloseMathScanner();
  }, [drawerOpen, mathScannerOpen, onCloseMathScanner]);
  const keyboardSpacer = useMemo(() => <ChatKeyboardSpacer lift={keyboardLift} />, [keyboardLift]);

  return (
    <View style={s.container}>
      <StreamingDraftProvider>
        <ChatMessageList
          listRef={list.listRef}
          messages={messages}
          headerInset={layout.headerInset}
          listBottomPad={layout.restingListBottomPad}
          hasMoreOlder={list.hasMoreOlder}
          loadingOlder={list.loadingOlder}
          newerPage={list.newerPage}
          chatLoading={list.chatLoading}
          routeChatId={list.routeChatId}
          emptyHeight={layout.emptyHeight}
          renderItem={list.renderItem}
          onLoadOlder={list.onLoadOlder}
          onScroll={list.onScroll}
          onScrollEnd={list.onScrollEnd}
          scroll={list.scroll}
          header={list.header}
          footer={keyboardSpacer}
        />
      </StreamingDraftProvider>

      <ChatComposer
        visible={!drawerOpen}
        animatedContainerStyle={composer.animatedStyle}
        streaming={composerShowsStop(composer)}
        attachPicking={composer.attachPicking}
        sendBusy={composer.sendBusy}
        sendStatus={composer.sendStatus}
        pendingAttachment={composer.pendingAttachment}
        onRemoveAttachment={composer.onRemoveAttachment}
        onCloseAttachSheet={sheets.onCloseAttachSheet}
        onPickAttachment={composer.onPickAttachment}
        onSend={handleComposerSend}
        onStop={composer.onStop}
        isOffline={composer.isOffline}
        voiceAvailable={composer.voiceAvailable}
        voiceRecording={composer.voiceRecording}
        voiceTranscribing={composer.voiceTranscribing}
        voiceMeterLevel={composer.voiceMeterLevel}
        onVoicePress={composer.onVoicePress}
        onCancelVoice={composer.onCancelVoice}
        onLiveTalkPress={composer.onLiveTalkPress}
        liveTalkChrome={composer.liveTalkSession}
        onOpenMathScanner={composer.onOpenMathScanner}
        onMathChromeHeightChange={composer.onMathChromeHeightChange}
        onInputFrameExtraChange={composer.onInputFrameExtraChange}
      />

      <ChatOverlays
        layout={layout}
        drawerOpen={drawerOpen}
        chrome={chrome}
        sheets={sheets}
        onStop={composer.onStop}
        quotaUpgradeLabel={t("chat.quota_nudge_cta")}
      />
    </View>
  );
});

type ChatOverlaysProps = {
  layout: ChatScreenLayoutProps;
  drawerOpen: boolean;
  chrome: ChatScreenChromeProps;
  sheets: ChatScreenSheetsProps;
  onStop: () => void;
  quotaUpgradeLabel: string;
};

const ChatOverlays = memo(function ChatOverlays({
  layout,
  drawerOpen,
  chrome,
  sheets,
  onStop,
  quotaUpgradeLabel,
}: ChatOverlaysProps) {
  const { styles, theme, restingComposerClearance: composerClearance, keyboardLift } = layout;

  return (
    <>
      <ChatScrollFab
        visible={!drawerOpen && chrome.showScrollToBottom}
        bottomOffset={composerClearance + 8}
        lift={keyboardLift}
        scrollAwayCount={chrome.scrollAwayCount}
        onPress={chrome.onScrollToLatest}
      />

      {chrome.quotaNudgeVisible && !chrome.chatError ? (
        <ChatQuotaNudge
          styles={styles}
          theme={theme}
          bottomOffset={composerClearance + 8}
          lift={keyboardLift}
          usedPct={chrome.quotaUsedPct}
          onUpgrade={chrome.onQuotaUpgrade}
          onDismiss={chrome.onQuotaDismiss}
        />
      ) : null}

      <ChatInlineError
        error={chrome.chatError}
        bottom={composerClearance + 8}
        lift={keyboardLift}
        upgradeLabel={!chrome.isPaid ? quotaUpgradeLabel : undefined}
        onUpgrade={!chrome.isPaid ? chrome.onUpgrade : undefined}
        onStop={onStop}
        onRetry={chrome.onRetryChatError}
        onChangeModel={chrome.onChangeModel}
        onDismiss={chrome.onDismissChatError}
      />

      <ActionBanner
        message={chrome.actionBanner?.message ?? null}
        icon={chrome.actionBanner?.icon}
        bottomOffset={composerClearance + 12}
        lift={keyboardLift}
        onDismiss={chrome.onDismissActionBanner}
      />

      <AttachmentSourceSheet
        visible={sheets.attachSheetOpen && !drawerOpen}
        onClose={sheets.onCloseAttachSheet}
        onSelect={sheets.onAttachmentSource}
      />

      <LazyMathEquationScanner
        visible={sheets.mathScannerOpen}
        onClose={sheets.onCloseMathScanner}
        onCaptured={sheets.onMathScanCaptured}
        onReadScan={sheets.onReadScan}
        onSolveReading={sheets.onMathScanSolve}
      />

      <UpgradeSheet
        visible={sheets.upgradeVisible}
        source={sheets.upgradeSource}
        onClose={sheets.onCloseUpgrade}
      />
    </>
  );
});
