import type { SharedValue } from "react-native-reanimated";
import React from "react";
import { Text } from "react-native";
import { render } from "@testing-library/react-native";

import { DrawerProvider } from "@/contexts/DrawerContext";

import {
  ChatScreenBody,
  type ChatScreenBodyProps,
} from "@/features/chat/components/ChatScreenBody";
import type { Message } from "@/lib/api";
import { lightTheme } from "@/lib/theme";

const mockChatMessageList = jest.fn();
const mockChatComposer = jest.fn();
const mockAttachmentSourceSheet = jest.fn();
const mockScrollFab = jest.fn();
const mockActionBanner = jest.fn();

// Memoized like the real list, so a test sees when the body hands it new props.
jest.mock("@/features/chat/components/ChatMessageList", () => {
  const { memo } = jest.requireActual("react") as typeof import("react");
  const { View: MockView } = jest.requireActual("react-native") as typeof import("react-native");
  return {
    ChatMessageList: memo(function MockChatMessageList(props: {
      messages: Message[];
      renderItem: (info: {
        item: Message;
        index: number;
        target: "Cell";
        extraData: unknown;
      }) => React.ReactElement | null;
    }) {
      mockChatMessageList(props);
      return (
        <MockView testID="message-list">
          {props.messages[0]
            ? props.renderItem({
                item: props.messages[0],
                index: 0,
                target: "Cell",
                extraData: undefined,
              })
            : null}
        </MockView>
      );
    }),
  };
});

jest.mock("@/features/chat/components/ChatComposer", () => ({
  ChatComposer: (props: { streaming: boolean; visible: boolean }) => {
    const { View: MockView } = jest.requireActual("react-native") as typeof import("react-native");
    mockChatComposer(props);
    if (!props.visible) return null;
    return <MockView testID={props.streaming ? "composer-streaming" : "composer-idle"} />;
  },
}));

jest.mock("@/features/chat/context/StreamingDraftContext", () => ({
  StreamingDraftProvider: ({ children }: { children: React.ReactNode }) => children,
}));

jest.mock("@/ui/feedback/ActionBanner", () => ({
  ActionBanner: (props: unknown) => {
    mockActionBanner(props);
    return null;
  },
}));
jest.mock("@/features/attachments/components/AttachmentSourceSheet", () => ({
  AttachmentSourceSheet: (props: { visible?: boolean }) => {
    mockAttachmentSourceSheet(props);
    return null;
  },
}));
jest.mock("@/features/scanner/components/MathEquationScanner", () => ({
  MathEquationScanner: () => null,
}));
jest.mock("@/features/billing/components/UpgradeSheet", () => ({ UpgradeSheet: () => null }));
jest.mock("@/features/chat/components/ChatInlineError", () => ({ ChatInlineError: () => null }));
jest.mock("@/features/chat/components/ChatQuotaNudge", () => ({ ChatQuotaNudge: () => null }));
jest.mock("@/features/chat/components/ChatScrollFab", () => ({
  ChatScrollFab: (props: unknown) => {
    mockScrollFab(props);
    return null;
  },
}));

const noop = jest.fn();
const message: Message = {
  id: "message-1",
  role: "assistant",
  content: "Hello",
  model: "free-chat",
  created_at: "2026-09-19T00:00:00Z",
};
const listScroll = {
  onContentSizeChange: jest.fn(),
  onListLayout: jest.fn(),
  onLayoutCommit: jest.fn(),
  onReaderScrollBegin: jest.fn(),
  onReaderScrollEndDrag: jest.fn(),
  hidden: false,
};
const renderItem = jest.fn(({ item }: { item: Message }) => <Text>{item.content}</Text>);
const onScroll = jest.fn();
const onScrollEnd = jest.fn();
const onLoadOlder = jest.fn();
const keyboardLift = { value: 0 } as never;
const drawerControls = { open: noop, close: noop, isOpenNow: () => false };

const baseProps: ChatScreenBodyProps = {
  layout: {
    styles: { container: {} } as never,
    theme: lightTheme,
    restingComposerClearance: 96,
    headerInset: 72,
    restingListBottomPad: 104,
    keyboardLift,
    emptyHeight: 500,
  },
  list: {
    listRef: { current: null },
    messages: [message],
    hasMoreOlder: false,
    loadingOlder: false,
    newerPage: null,
    chatLoading: false,
    routeChatId: "chat-1",
    renderItem,
    onLoadOlder,
    onScroll,
    onScrollEnd,
    scroll: listScroll,
    header: null,
  },
  composer: {
    streaming: false,
    replySaving: false,
    attachPicking: false,
    sendBusy: false,
    pendingAttachment: null,
    onRemoveAttachment: noop,
    onPickAttachment: noop,
    onSend: noop,
    onStop: noop,
    isOffline: false,
    voiceAvailable: true,
    voiceRecording: false,
    voiceTranscribing: false,
    voiceMeterLevel: { value: 0.12 } as SharedValue<number>,
  },
  chrome: {
    actionBanner: null,
    onDismissActionBanner: noop,
    showScrollToBottom: false,
    scrollAwayCount: 0,
    onScrollToLatest: noop,
    quotaNudgeVisible: false,
    quotaUsedPct: 0,
    onQuotaUpgrade: noop,
    onQuotaDismiss: noop,
    chatError: null,
    isPaid: false,
    onUpgrade: noop,
    onRetryChatError: noop,
    onChangeModel: noop,
    onDismissChatError: noop,
  },
  sheets: {
    attachSheetOpen: false,
    onCloseAttachSheet: noop,
    onAttachmentSource: noop,
    mathScannerOpen: false,
    onCloseMathScanner: noop,
    onMathScanCaptured: noop,
    onReadScan: async () => null,
    onMathScanSolve: noop,
    upgradeVisible: false,
    onCloseUpgrade: noop,
  },
};

describe("ChatScreenBody", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders the grouped screen contract and forwards stable list callbacks", async () => {
    const { getByText, getByTestId, rerender } = await render(
      <ChatScreenBody {...baseProps} />,
    );

    expect(getByText("Hello")).toBeTruthy();
    expect(getByTestId("composer-idle")).toBeTruthy();
    expect(mockChatMessageList).toHaveBeenLastCalledWith(
      expect.objectContaining({
        renderItem,
        onLoadOlder,
        onScroll,
        onScrollEnd,
        scroll: listScroll,
        headerInset: 72,
      }),
    );

    await rerender(
      <ChatScreenBody
        {...baseProps}
        composer={{ ...baseProps.composer, streaming: true }}
      />,
    );

    expect(getByTestId("composer-streaming")).toBeTruthy();
    expect(mockAttachmentSourceSheet).toHaveBeenLastCalledWith(
      expect.objectContaining({ visible: false }),
    );
    expect(mockAttachmentSourceSheet.mock.calls.at(-1)?.[0]).not.toHaveProperty("bottomOffset");
    expect(mockChatMessageList).toHaveBeenLastCalledWith(
      expect.objectContaining({
        renderItem,
        onLoadOlder,
        onScroll,
        onScrollEnd,
      }),
    );
  });

  it("shows a busy Send, not Stop, while a send is on its way", async () => {
    const { getByTestId } = await render(
      <ChatScreenBody
        {...baseProps}
        composer={{ ...baseProps.composer, streaming: true, sendBusy: true }}
      />,
    );
    expect(getByTestId("composer-idle")).toBeTruthy();
    expect(mockChatComposer).toHaveBeenLastCalledWith(expect.objectContaining({ streaming: false, sendBusy: true }));
  });

  it("offers Send, not Stop, once the reply's text is in and only its save is left", async () => {
    const { getByTestId } = await render(
      <ChatScreenBody
        {...baseProps}
        composer={{ ...baseProps.composer, streaming: true, replySaving: true }}
      />,
    );
    expect(getByTestId("composer-idle")).toBeTruthy();
  });

  it("lays the list out at rest and lets the keyboard spacer and lifted chrome follow the keyboard", async () => {
    await render(
      <ChatScreenBody
        {...baseProps}
        chrome={{ ...baseProps.chrome, showScrollToBottom: true, actionBanner: { message: "Saved" } }}
      />,
    );

    const listProps = mockChatMessageList.mock.calls.at(-1)?.[0];
    expect(listProps).toEqual(expect.objectContaining({ listBottomPad: 104 }));
    expect(listProps.footer.props).toEqual({ lift: keyboardLift });
    expect(mockScrollFab).toHaveBeenLastCalledWith(
      expect.objectContaining({ visible: true, bottomOffset: 104, lift: keyboardLift }),
    );
    expect(mockActionBanner).toHaveBeenLastCalledWith(
      expect.objectContaining({ bottomOffset: 108, lift: keyboardLift }),
    );
  });

  it("steps the composer and the chrome aside while the drawer is open, without new props", async () => {
    const props = {
      ...baseProps,
      chrome: { ...baseProps.chrome, showScrollToBottom: true },
      sheets: { ...baseProps.sheets, attachSheetOpen: true },
    };
    const view = await render(
      <DrawerProvider controls={drawerControls} isOpen={false}>
        <ChatScreenBody {...props} />
      </DrawerProvider>,
    );
    expect(view.getByTestId("composer-idle")).toBeTruthy();
    expect(mockScrollFab).toHaveBeenLastCalledWith(expect.objectContaining({ visible: true }));
    expect(mockAttachmentSourceSheet).toHaveBeenLastCalledWith(expect.objectContaining({ visible: true }));
    const listRenders = mockChatMessageList.mock.calls.length;

    await view.rerender(
      <DrawerProvider controls={drawerControls} isOpen>
        <ChatScreenBody {...props} />
      </DrawerProvider>,
    );
    expect(view.queryByTestId("composer-idle")).toBeNull();
    expect(mockScrollFab).toHaveBeenLastCalledWith(expect.objectContaining({ visible: false }));
    expect(mockAttachmentSourceSheet).toHaveBeenLastCalledWith(expect.objectContaining({ visible: false }));
    // The thread itself is untouched by the drawer.
    expect(mockChatMessageList).toHaveBeenCalledTimes(listRenders);
  });

  it("closes the math scanner when the drawer opens over it", async () => {
    const onCloseMathScanner = jest.fn();
    const props = { ...baseProps, sheets: { ...baseProps.sheets, mathScannerOpen: true, onCloseMathScanner } };
    const view = await render(
      <DrawerProvider controls={drawerControls} isOpen={false}>
        <ChatScreenBody {...props} />
      </DrawerProvider>,
    );
    expect(onCloseMathScanner).not.toHaveBeenCalled();

    await view.rerender(
      <DrawerProvider controls={drawerControls} isOpen>
        <ChatScreenBody {...props} />
      </DrawerProvider>,
    );
    expect(onCloseMathScanner).toHaveBeenCalledTimes(1);
  });
});
