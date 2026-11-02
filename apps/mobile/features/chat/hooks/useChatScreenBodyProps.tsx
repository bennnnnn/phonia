import { useCallback, useLayoutEffect, useMemo, useState, type MutableRefObject, type ReactElement, type RefObject } from "react";
import { FlashListRef, ListRenderItemInfo } from "@shopify/flash-list";
import { type NativeScrollEvent, type NativeSyntheticEvent, type View, type ViewStyle } from "react-native";
import { type AnimatedStyle, type SharedValue } from "react-native-reanimated";
import { useRouter } from "expo-router";

import type { UpgradeSource } from "@/features/billing/components/UpgradeSheet";
import type { LiveTalkComposerChrome } from "@/features/chat/components/ChatComposer";
import { WhileDrawerClosed } from "@/contexts/DrawerContext";
import { ChatHeader } from "@/features/chat/components/ChatHeader";
import type {
  ChatScreenBodyProps,
  ChatScreenChromeProps,
  ChatScreenComposerProps,
  ChatScreenLayoutProps,
  ChatScreenListProps,
  ChatScreenSheetsProps,
} from "@/features/chat/components/ChatScreenBody";
import type { ChatScreenStyles } from "@/features/chat/components/chatScreenStyles";
import type { useChatLayoutMetrics } from "@/features/chat/hooks/useChatLayoutMetrics";
import type { ChatListScroll } from "@/features/chat/hooks/useChatScroll";
import type { AttachmentSource } from "@/features/attachments/components/AttachmentSourceSheet";
import type { Message } from "@/lib/api";
import type { PendingAttachment } from "@/features/attachments/model/attachments";
import type { ScannerSubject } from "@/lib/scanner/subjects";
import type { ResolvedChatError } from "@/features/chat/model/errorMessage";
import { openDrawer } from "@/features/chat/drawer/drawer";
import type { Theme } from "@/lib/theme";

type Router = ReturnType<typeof useRouter>;

type QuotaNudge = {
  show: boolean;
  usedPct: number;
  dismiss: () => void;
};

type ChatLayout = ReturnType<typeof useChatLayoutMetrics>;

type UseChatScreenBodyPropsParams = {
  styles: ChatScreenStyles;
  theme: Theme;
  routeChatId?: string;
  layout: Pick<ChatLayout, "headerMinimumHeight" | "headerInset" | "onHeaderHeightChange" | "emptyHeight" |
    "listBottomPad" | "restingComposerClearance" | "restingListBottomPad">;
  listBottomPadRef: MutableRefObject<number>;
  actionBanner: ChatScreenChromeProps["actionBanner"];
  dismissActionBanner: () => void;
  /** Everything needed to render the collapsible ChatHeader (title, nav, menu). */
  header: {
    insetsTop: number;
    router: Router;
    headerTitleLabel: string | null;
    titleGenerating: boolean;
    chatTitle: string | null;
    startNewChat: (opts?: { force?: boolean }) => void;
    setMenuVisible: React.Dispatch<React.SetStateAction<boolean>>;
    menuOverlayOpen: boolean;
    /** The header ⋮ button; the chat menu drops from it. */
    menuAnchorRef: RefObject<View | null>;
  };
  /** Message list data + scroll/pagination handlers for ChatMessageList. */
  list: {
    listRef: RefObject<FlashListRef<Message> | null>;
    messages: Message[];
    hasMoreOlder: boolean;
    loadingOlder: boolean;
    newerPage: ChatScreenListProps["newerPage"];
    chatLoading: boolean;
    renderItem: (info: ListRenderItemInfo<Message>) => ReactElement | null;
    loadOlderMessages: () => Promise<void>;
    handleScroll: (event: NativeSyntheticEvent<NativeScrollEvent>) => void;
    handleScrollEnd: () => void;
    listScroll?: ChatListScroll;
  };
  handleSend: (prompt?: string) => void | Promise<unknown>;
  showScrollToBottom: boolean;
  scrollAwayCount: number;
  scrollToLatest: () => void;
  /** Attachment picker sheet + upload state. */
  attachments: {
    attachSheetOpen: boolean;
    closeAttachSheet: () => void;
    attachPicking: boolean;
    pendingAttachment: PendingAttachment | null;
    /** The user dropped the composer's attachment: its copy and unlinked upload go too. */
    removePendingAttachment: () => void;
    handlePickAttachment: () => void;
    handleAttachmentSheetSelect: (source: AttachmentSource) => void | Promise<void>;
    mathScannerOpen: boolean;
    closeMathScanner: () => void;
    handleMathScanCaptured: ChatScreenSheetsProps["onMathScanCaptured"];
    readScan: ChatScreenSheetsProps["onReadScan"];
    handleMathScanSolve: (reading: string, subject?: ScannerSubject) => void;
    onOpenMathScanner?: () => void;
    onMathChromeHeightChange?: (height: number) => void;
    onInputFrameExtraChange?: (extra: number) => void;
  };
  quotaNudge: QuotaNudge;
  chatError: ResolvedChatError | null;
  isPaid: boolean;
  retryChatError: () => void;
  dismissChatError: () => void;
  composerAnimatedStyle?: AnimatedStyle<ViewStyle>;
  keyboardLift: SharedValue<number>;
  streaming: boolean;
  replySaving: boolean;
  sendBusy: boolean;
  sendStatus?: string;
  stopGeneration: () => void;
  isOffline: boolean;
  voice: {
    voiceAvailable: boolean;
    voiceRecording: boolean;
    voiceTranscribing: boolean;
    voiceMeterLevel: SharedValue<number>;
    toggleVoiceInput: () => void | Promise<void>;
    cancelVoiceInput?: () => void;
    onLiveTalkPress?: () => void;
  };
  liveTalkSession?: LiveTalkComposerChrome | null;
};

export function useChatScreenBodyProps({
  styles,
  theme,
  routeChatId,
  layout,
  listBottomPadRef,
  actionBanner,
  dismissActionBanner,
  header: {
    insetsTop,
    router,
    headerTitleLabel,
    titleGenerating,
    chatTitle,
    startNewChat,
    setMenuVisible,
    menuOverlayOpen,
    menuAnchorRef,
  },
  list: {
    listRef,
    messages,
    hasMoreOlder,
    loadingOlder,
    newerPage,
    chatLoading,
    renderItem,
    loadOlderMessages,
    handleScroll,
    handleScrollEnd,
    listScroll,
  },
  handleSend,
  showScrollToBottom,
  scrollAwayCount,
  scrollToLatest,
  attachments: {
    attachSheetOpen,
    closeAttachSheet,
    attachPicking,
    pendingAttachment,
    removePendingAttachment,
    handlePickAttachment,
    handleAttachmentSheetSelect,
    mathScannerOpen,
    closeMathScanner,
    handleMathScanCaptured,
    readScan,
    handleMathScanSolve,
    onOpenMathScanner,
    onMathChromeHeightChange,
    onInputFrameExtraChange,
  },
  quotaNudge,
  chatError,
  isPaid,
  retryChatError,
  dismissChatError,
  composerAnimatedStyle,
  keyboardLift,
  streaming,
  replySaving,
  sendBusy,
  sendStatus,
  stopGeneration,
  isOffline,
  voice: {
    voiceAvailable,
    voiceRecording,
    voiceTranscribing,
    voiceMeterLevel,
    toggleVoiceInput,
    cancelVoiceInput,
    onLiveTalkPress,
  },
  liveTalkSession = null,
}: UseChatScreenBodyPropsParams): {
  bodyProps: ChatScreenBodyProps;
  openUpgradeSheet: (source?: UpgradeSource) => void;
} {
  const [upgradeVisible, setUpgradeVisible] = useState(false);
  const [upgradeSource, setUpgradeSource] = useState<UpgradeSource>("other");
  const openUpgradeSheet = useCallback((source: UpgradeSource = "other") => {
    setUpgradeSource(source);
    setUpgradeVisible(true);
  }, []);

  const {
    headerMinimumHeight,
    headerInset,
    onHeaderHeightChange,
    listBottomPad,
    restingComposerClearance,
    restingListBottomPad,
    emptyHeight,
  } = layout;
  useLayoutEffect(() => {
    listBottomPadRef.current = listBottomPad;
  }, [listBottomPadRef, listBottomPad]);

  // Keep list-facing callbacks identity-stable. Composer text lives in
  // ComposerDraftContext so keystrokes do not rebuild bodyProps.
  const onLoadOlder = useCallback(() => {
    void loadOlderMessages();
  }, [loadOlderMessages]);
  const onSend = useCallback(
    (text?: string) => {
      void handleSend(text);
    },
    [handleSend],
  );
  const quotaDismiss = quotaNudge.dismiss;
  const onQuotaUpgrade = useCallback(() => {
    quotaDismiss();
    openUpgradeSheet("quota");
  }, [quotaDismiss, openUpgradeSheet]);
  const onUpgrade = useCallback(() => openUpgradeSheet("other"), [openUpgradeSheet]);
  const onChangeModel = useCallback(() => {
    dismissChatError();
    router.push("/settings/models");
  }, [dismissChatError, router]);
  const onAttachmentSource = useCallback(
    (source: AttachmentSource) => {
      void handleAttachmentSheetSelect(source);
    },
    [handleAttachmentSheetSelect],
  );
  const onVoicePress = useCallback(() => {
    void toggleVoiceInput();
  }, [toggleVoiceInput]);
  const onCloseUpgrade = useCallback(() => setUpgradeVisible(false), []);
  const stableLiveTalkSession = useMemo(
    () =>
      liveTalkSession
        ? {
            muted: liveTalkSession.muted,
            onClose: liveTalkSession.onClose,
            onMutePress: liveTalkSession.onMutePress,
            onYield: liveTalkSession.onYield,
          }
        : null,
    [
      liveTalkSession?.muted,
      liveTalkSession?.onClose,
      liveTalkSession?.onMutePress,
      liveTalkSession?.onYield,
    ],
  );

  // Hidden while the drawer is open; it reads that itself, so this screen never re-renders for it.
  const listHeader = useMemo(
    () => (
      <WhileDrawerClosed>
        <ChatHeader
          paddingTop={insetsTop}
          minimumHeight={headerMinimumHeight}
          onHeightChange={onHeaderHeightChange}
          menuOverlayOpen={menuOverlayOpen}
          headerTitleLabel={headerTitleLabel}
          titleGenerating={titleGenerating}
          chatTitle={chatTitle}
          // Prefer routeChatId so actions don't flash off if messages briefly
          // clear during a chat load/refetch; home (no route, no turns) stays clean.
          hasMessages={messages.length > 0 || Boolean(routeChatId)}
          onOpenDrawer={openDrawer}
          onNewChat={startNewChat}
          onOpenMenu={() => setMenuVisible((v) => !v)}
          menuAnchorRef={menuAnchorRef}
        />
      </WhileDrawerClosed>
    ),
    [
      insetsTop,
      headerMinimumHeight,
      onHeaderHeightChange,
      menuOverlayOpen,
      headerTitleLabel,
      titleGenerating,
      chatTitle,
      messages.length,
      routeChatId,
      startNewChat,
      setMenuVisible,
      menuAnchorRef,
    ],
  );

  const layoutProps = useMemo(
    (): ChatScreenLayoutProps => ({
      styles,
      theme,
      restingComposerClearance,
      headerInset,
      restingListBottomPad,
      keyboardLift,
      emptyHeight,
    }),
    [
      styles,
      theme,
      restingComposerClearance,
      headerInset,
      restingListBottomPad,
      keyboardLift,
      emptyHeight,
    ],
  );

  const listProps = useMemo(
    (): ChatScreenListProps => ({
      listRef,
      messages,
      hasMoreOlder,
      loadingOlder,
      newerPage,
      chatLoading,
      routeChatId,
      renderItem,
      onLoadOlder,
      onScroll: handleScroll,
      onScrollEnd: handleScrollEnd,
      scroll: listScroll,
      header: listHeader,
    }),
    [
      listRef,
      messages,
      hasMoreOlder,
      loadingOlder,
      newerPage,
      chatLoading,
      routeChatId,
      renderItem,
      onLoadOlder,
      handleScroll,
      handleScrollEnd,
      listScroll,
      listHeader,
    ],
  );

  const composerProps = useMemo(
    (): ChatScreenComposerProps => ({
      animatedStyle: composerAnimatedStyle,
      streaming,
      replySaving,
      attachPicking,
      sendBusy,
      sendStatus,
      pendingAttachment,
      onRemoveAttachment: removePendingAttachment,
      onPickAttachment: handlePickAttachment,
      onOpenMathScanner,
      onMathChromeHeightChange,
      onInputFrameExtraChange,
      onSend,
      onStop: stopGeneration,
      isOffline,
      voiceAvailable,
      voiceRecording,
      voiceTranscribing,
      voiceMeterLevel,
      onVoicePress,
      onCancelVoice: cancelVoiceInput,
      onLiveTalkPress,
      liveTalkSession: stableLiveTalkSession,
    }),
    [
      composerAnimatedStyle,
      streaming,
      replySaving,
      attachPicking,
      sendBusy,
      sendStatus,
      pendingAttachment,
      removePendingAttachment,
      handlePickAttachment,
      onOpenMathScanner,
      onMathChromeHeightChange,
      onInputFrameExtraChange,
      onSend,
      stopGeneration,
      isOffline,
      voiceAvailable,
      voiceRecording,
      voiceTranscribing,
      voiceMeterLevel,
      onVoicePress,
      cancelVoiceInput,
      onLiveTalkPress,
      stableLiveTalkSession,
    ],
  );

  const chromeProps = useMemo(
    (): ChatScreenChromeProps => ({
      actionBanner,
      onDismissActionBanner: dismissActionBanner,
      showScrollToBottom,
      scrollAwayCount,
      onScrollToLatest: scrollToLatest,
      quotaNudgeVisible: quotaNudge.show,
      quotaUsedPct: quotaNudge.usedPct,
      onQuotaUpgrade,
      onQuotaDismiss: quotaDismiss,
      chatError,
      isPaid,
      onUpgrade,
      onRetryChatError: retryChatError,
      onChangeModel,
      onDismissChatError: dismissChatError,
    }),
    [
      actionBanner,
      dismissActionBanner,
      showScrollToBottom,
      scrollAwayCount,
      scrollToLatest,
      quotaNudge.show,
      quotaNudge.usedPct,
      onQuotaUpgrade,
      quotaDismiss,
      chatError,
      isPaid,
      onUpgrade,
      retryChatError,
      onChangeModel,
      dismissChatError,
    ],
  );

  const sheetsProps = useMemo(
    (): ChatScreenSheetsProps => ({
      attachSheetOpen,
      onCloseAttachSheet: closeAttachSheet,
      onAttachmentSource,
      mathScannerOpen,
      onCloseMathScanner: closeMathScanner,
      onMathScanCaptured: handleMathScanCaptured,
      onReadScan: readScan,
      onMathScanSolve: handleMathScanSolve,
      upgradeVisible,
      upgradeSource,
      onCloseUpgrade,
    }),
    [
      attachSheetOpen,
      closeAttachSheet,
      onAttachmentSource,
      mathScannerOpen,
      closeMathScanner,
      handleMathScanCaptured,
      readScan,
      handleMathScanSolve,
      upgradeVisible,
      upgradeSource,
      onCloseUpgrade,
    ],
  );

  const bodyProps = useMemo(
    (): ChatScreenBodyProps => ({
      layout: layoutProps,
      list: listProps,
      composer: composerProps,
      chrome: chromeProps,
      sheets: sheetsProps,
    }),
    [layoutProps, listProps, composerProps, chromeProps, sheetsProps],
  );

  return { bodyProps, openUpgradeSheet };
}
