import type { SharedValue } from "react-native-reanimated";
import React from "react";
import { Text } from "react-native";
import { render, renderHook } from "@testing-library/react-native";

import { DrawerProvider } from "@/contexts/DrawerContext";

import { useChatScreenBodyProps } from "@/features/chat/hooks/useChatScreenBodyProps";
import type { Message } from "@/lib/api";
import { lightTheme } from "@/lib/theme";

// One shared value for the screen's life, as the voice hook keeps it.
const METER = { value: 0.12 } as SharedValue<number>;

const mockChatHeader = jest.fn();

jest.mock("@/features/chat/components/ChatHeader", () => ({
  ChatHeader: () => {
    mockChatHeader();
    return null;
  },
}));

jest.mock("@/features/chat/drawer/drawer", () => ({
  openDrawer: jest.fn(),
}));

const message: Message = {
  id: "message-1",
  role: "assistant",
  content: "Hello",
  model: "free-chat",
  created_at: "2026-09-19T00:00:00Z",
};

const renderItem = jest.fn(({ item }: { item: Message }) => <Text>{item.content}</Text>);
const loadOlderMessages = jest.fn(async () => undefined);
const handleScroll = jest.fn();
const handleScrollEnd = jest.fn();
const handleSend = jest.fn();
const scrollToLatest = jest.fn();
const dismissActionBanner = jest.fn();
const startNewChat = jest.fn();
const setMenuVisible = jest.fn();
const closeAttachSheet = jest.fn();
const removePendingAttachment = jest.fn();
const handlePickAttachment = jest.fn();
const handleAttachmentSheetSelect = jest.fn(async () => undefined);
const closeMathScanner = jest.fn();
const handleMathScanCaptured = jest.fn();
const readScan = jest.fn(async () => null);
const handleMathScanSolve = jest.fn();
const quotaDismiss = jest.fn();
const retryChatError = jest.fn();
const dismissChatError = jest.fn();
const stopGeneration = jest.fn();
const toggleVoiceInput = jest.fn(async () => undefined);
const handleHeaderHeightChange = jest.fn();
const styles = {} as never;
const listRef = { current: null };
const menuAnchorRef = { current: null };
const listBottomPadRef = { current: 0 };
const keyboardLift = { value: 0 } as never;

const router = {
  setParams: jest.fn(),
  push: jest.fn(),
} as never;

function useHarness(streaming: boolean, messages: Message[], replySaving = false) {
  return useChatScreenBodyProps({
    styles,
    theme: lightTheme,
    routeChatId: "chat-1",
    layout: {
      headerMinimumHeight: 72,
      headerInset: 72,
      onHeaderHeightChange: handleHeaderHeightChange,
      listBottomPad: 104,
      restingComposerClearance: 96,
      restingListBottomPad: 104,
      emptyHeight: 500,
    },
    listBottomPadRef,
    actionBanner: null,
    dismissActionBanner,
    header: {
      insetsTop: 24,
      router,
      headerTitleLabel: "Trip",
      titleGenerating: false,
      chatTitle: "Trip",
      startNewChat,
      setMenuVisible,
      menuOverlayOpen: false,
      menuAnchorRef,
    },
    list: {
      listRef,
      messages,
      hasMoreOlder: false,
      loadingOlder: false,
      newerPage: null,
      chatLoading: false,
      renderItem,
      loadOlderMessages,
      handleScroll,
      handleScrollEnd,
    },
    handleSend,
    showScrollToBottom: false,
    scrollAwayCount: 0,
    scrollToLatest,
    attachments: {
      attachSheetOpen: false,
      closeAttachSheet,
      attachPicking: false,
      pendingAttachment: null,
      removePendingAttachment,
      handlePickAttachment,
      handleAttachmentSheetSelect,
      mathScannerOpen: false,
      closeMathScanner,
      handleMathScanCaptured,
      readScan,
      handleMathScanSolve,
    },
    quotaNudge: {
      show: false,
      usedPct: 0,
      dismiss: quotaDismiss,
    },
    chatError: null,
    isPaid: false,
    retryChatError,
    dismissChatError,
    keyboardLift,
    streaming,
    replySaving,
    sendBusy: false,
    stopGeneration,
    isOffline: false,
    voice: {
      voiceAvailable: true,
      voiceRecording: false,
      voiceTranscribing: false,
      voiceMeterLevel: METER,
      toggleVoiceInput,
    },
  });
}

describe("useChatScreenBodyProps", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("keeps unaffected groups and FlashList callbacks stable while streaming changes", async () => {
    const firstMessages = [message];
    const { result, rerender } = await renderHook(
      ({ streaming, messages }: { streaming: boolean; messages: Message[] }) => useHarness(streaming, messages),
      { initialProps: { streaming: false, messages: firstMessages } },
    );
    const initial = result.current.bodyProps;
    const initialListCallbacks = {
      renderItem: initial.list.renderItem,
      onLoadOlder: initial.list.onLoadOlder,
      onScroll: initial.list.onScroll,
      onScrollEnd: initial.list.onScrollEnd,
    };

    await rerender({ streaming: true, messages: firstMessages });
    const streaming = result.current.bodyProps;

    expect(streaming.layout).toBe(initial.layout);
    expect(streaming.list).toBe(initial.list);
    expect(streaming.chrome).toBe(initial.chrome);
    expect(streaming.sheets).toBe(initial.sheets);
    expect(streaming.composer).not.toBe(initial.composer);
    expect(streaming.composer.streaming).toBe(true);
    expect({
      renderItem: streaming.list.renderItem,
      onLoadOlder: streaming.list.onLoadOlder,
      onScroll: streaming.list.onScroll,
      onScrollEnd: streaming.list.onScrollEnd,
    }).toEqual(initialListCallbacks);

    await rerender({ streaming: true, messages: firstMessages });
    expect(result.current.bodyProps).toBe(streaming);
  });

  it("tells the composer when the reply is only saving, so Send is offered then", async () => {
    const { result, rerender } = await renderHook(
      ({ replySaving }: { replySaving: boolean }) => useHarness(true, [message], replySaving),
      { initialProps: { replySaving: false } },
    );
    expect(result.current.bodyProps.composer.replySaving).toBe(false);
    await rerender({ replySaving: true });
    expect(result.current.bodyProps.composer).toMatchObject({ streaming: true, replySaving: true });
  });

  it("wires the composer's remove button to the discarding remove, not a bare clear", async () => {
    const { result } = await renderHook(() => useHarness(false, [message]));
    result.current.bodyProps.composer.onRemoveAttachment();
    expect(removePendingAttachment).toHaveBeenCalledTimes(1);
  });

  it("updates only the list group when the message collection changes", async () => {
    const firstMessages = [message];
    const { result, rerender } = await renderHook(
      ({ messages }: { messages: Message[] }) => useHarness(false, messages),
      { initialProps: { messages: firstMessages } },
    );
    const initial = result.current.bodyProps;
    const nextMessages = [
      ...firstMessages,
      { ...message, id: "message-2", content: "Streaming token" },
    ];

    await rerender({ messages: nextMessages });
    const updated = result.current.bodyProps;

    expect(updated.layout).toBe(initial.layout);
    expect(updated.list).not.toBe(initial.list);
    expect(updated.list.messages).toBe(nextMessages);
    expect(updated.list.renderItem).toBe(initial.list.renderItem);
    expect(updated.composer).toBe(initial.composer);
    expect(updated.chrome).toBe(initial.chrome);
    expect(updated.sheets).toBe(initial.sheets);
  });

  it("hides header chrome while the drawer is open without dropping the measured list inset", async () => {
    const { result } = await renderHook(() => useHarness(false, [message]));
    const header = result.current.bodyProps.list.header;
    const controls = { open: jest.fn(), close: jest.fn(), isOpenNow: () => false };

    const view = await render(<DrawerProvider controls={controls} isOpen={false}>{header}</DrawerProvider>);
    expect(mockChatHeader).toHaveBeenCalledTimes(1);

    // The same header element: it reads the drawer itself, so nothing rebuilds it.
    await view.rerender(<DrawerProvider controls={controls} isOpen>{header}</DrawerProvider>);
    expect(mockChatHeader).toHaveBeenCalledTimes(1);
    expect(result.current.bodyProps.list.header).toBe(header);
    expect(result.current.bodyProps.layout.headerInset).toBe(72);

    await view.rerender(<DrawerProvider controls={controls} isOpen={false}>{header}</DrawerProvider>);
    expect(mockChatHeader).toHaveBeenCalledTimes(2);
  });
});
