/**
 * One haptic per tap on a chat's actions menu (the header's ⋮ and the drawer row's
 * long-press). The Menu plays it; the actions behind the rows play none of their own.
 */
import React, { useLayoutEffect } from "react";
import { Alert, Text } from "react-native";
import { act, fireEvent, render } from "@testing-library/react-native";

import { ChatActionsMenu } from "@/features/chat/components/ChatActionsMenu";
import { ConversationList } from "@/features/chat/drawer/ConversationList";
import { useChatActions } from "@/features/chat/hooks/useChatActions";
import { api, type Chat } from "@/lib/api";
import { impactMedium, notifySuccess, notifyWarning, selection, tap } from "@/lib/haptics";

jest.mock("@/lib/haptics", () => ({
  tap: jest.fn(),
  selection: jest.fn(),
  impactMedium: jest.fn(),
  notifySuccess: jest.fn(),
  notifyWarning: jest.fn(),
  notifyDestructive: jest.fn(),
}));
jest.mock("@/lib/reduceMotion", () => ({ useReduceMotion: () => false }));
jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => 0 }));
jest.mock("@/lib/api", () => ({
  api: {
    setPin: jest.fn(),
    setArchive: jest.fn(),
    listAllMessages: jest.fn(async () => []),
  },
}));
jest.mock("@/features/chat/model/chatListCache", () => ({
  getCachedChat: () => undefined,
  peekCreatedChat: () => undefined,
}));
jest.mock("@/features/chat/model/messageCache", () => ({
  clearCachedChatMessages: jest.fn(),
  writeCachedChatMessages: jest.fn(async () => undefined),
  patchCachedChatMessage: jest.fn(async () => undefined),
}));
jest.mock("@/features/chat/model/exportMessagePdf", () => ({ exportConversationAsPdf: jest.fn() }));
jest.mock("@/contexts/actionFeedbackCore", () => ({ useActionFeedbackOptional: () => null }));

// The drawer: only the row menu is real.
const chat: Chat = { id: "chat-1", title: "Trip ideas", model: "free-chat", pinned: false, archived: false } as Chat;
const mockMenu = {
  menuChat: chat as Chat | null,
  closeMenu: jest.fn(),
  openShareChat: jest.fn(),
  openRenameFromMenu: jest.fn(),
  togglePinChat: jest.fn(async () => undefined),
  toggleArchiveChat: jest.fn(async () => undefined),
  confirmDeleteChat: jest.fn(),
  showRowMenu: jest.fn(),
};
jest.mock("@/contexts/AuthContext", () => ({ useAuthToken: () => "tok" }));
jest.mock("@/contexts/DrawerContext", () => ({ useDrawerOpen: () => true }));
jest.mock("expo-router", () => ({ useRouter: () => ({ setParams: jest.fn(), push: jest.fn() }) }));
jest.mock("expo-linear-gradient", () => ({ LinearGradient: () => null }));
jest.mock("@/features/attachments/model/galleryListCache", () => ({ prefetchGallery: jest.fn() }));
jest.mock("@/features/chat/drawer/drawer", () => ({
  clearChatHighlightGlobal: jest.fn(),
  closeDrawer: jest.fn(),
  getActiveChatIdGlobal: () => null,
  startNewChatGlobal: jest.fn(),
  insertChatGlobal: jest.fn(),
  patchChatGlobal: jest.fn(),
  removeChatGlobal: jest.fn(),
  abandonActiveChatIfDeleted: jest.fn(),
}));
jest.mock("@/features/chat/drawer/useDrawerChatList", () => ({ useDrawerChatList: () => ({
  groups: { pinned: [], today: [], yesterday: [], last_7_days: [], this_month: [], older: [], archived: [] },
  allChats: [], load: jest.fn(), isSectionCollapsed: () => false,
}) }));
jest.mock("@/features/chat/hooks/useChatBulkActions", () => ({ useChatBulkActions: () => ({}) }));
jest.mock("@/features/chat/hooks/useChatMenuActions", () => ({ useChatMenuActions: () => mockMenu }));
jest.mock("@/features/chat/drawer/useDrawerChatSelection", () => ({
  useDrawerChatSelection: () => ({ selectedIds: new Set(), selectedCount: 0, enterSelectionMode: jest.fn() }),
}));
jest.mock("@/features/todos/hooks/useReminderBadgeCount", () => ({ useReminderBadgeCount: () => ({}) }));
jest.mock("@/ui/feedback/ActionBanner", () => ({ ActionBanner: () => null }));
jest.mock("@/features/chat/components/ChatRenameSheet", () => ({ ChatRenameSheet: () => null }));
jest.mock("@/features/chat/components/ChatShareSheet", () => ({ ChatShareSheet: () => null }));
jest.mock("@/features/chat/drawer/DrawerListHeader", () => ({ DrawerListHeader: () => null }));
jest.mock("@/features/chat/drawer/DrawerFooter", () => ({ DrawerFooter: () => null }));
jest.mock("@/features/chat/drawer/DrawerNavLinks", () => ({ DrawerNavLinks: () => null }));
jest.mock("@/features/chat/drawer/DrawerSelectionBar", () => ({ DrawerSelectionBar: () => null }));
jest.mock("@/features/chat/drawer/DrawerHeader", () => ({ DrawerHeader: () => null }));
jest.mock("@/features/chat/drawer/DrawerChatFlashList", () => ({ DrawerChatFlashList: () => null }));

const haptics = [tap, selection, impactMedium, notifySuccess, notifyWarning];
const hapticCount = () => haptics.reduce((sum, fn) => sum + jest.mocked(fn).mock.calls.length, 0);

let actions: ReturnType<typeof useChatActions>;

function HeaderMenu() {
  const result = useChatActions({
    token: "tok",
    chatId: "chat-1",
    chatTitle: "Trip ideas",
    messages: [],
    pinned: false,
    setPinned: jest.fn(),
    archived: false,
    setArchived: jest.fn(),
    setChatTitle: jest.fn(),
    editThread: jest.fn(),
    t: (key) => key,
  });
  useLayoutEffect(() => { actions = result; });
  return (
    <>
      <Text>chat</Text>
      <ChatActionsMenu
        visible
        title="Trip ideas"
        pinned={false}
        archived={false}
        onClose={jest.fn()}
        onShare={result.onShareFromMenu}
        onExportPdf={result.onExportPdfFromMenu}
        onRename={result.onRenameFromMenu}
        onTogglePin={result.onTogglePinFromMenu}
        onToggleArchive={result.onToggleArchiveFromMenu}
        onDelete={result.onDeleteFromMenu}
      />
    </>
  );
}

beforeEach(() => {
  jest.clearAllMocks();
  jest.spyOn(Alert, "alert").mockImplementation(() => {});
  jest.mocked(api.setPin).mockResolvedValue({ ...chat, pinned: true });
  jest.mocked(api.setArchive).mockResolvedValue({ ...chat, archived: true });
});

const ROWS = ["chat.share", "chat.export_pdf", "chat.rename", "chat.pin", "chat.archive", "common.delete"];

it.each(ROWS)("the chat header's ⋮ %s plays one haptic", async (row) => {
  const view = await render(<HeaderMenu />);
  expect(actions).toBeDefined();
  await act(async () => {
    fireEvent.press(view.getByRole("menuitem", { name: row }));
  });
  expect(hapticCount()).toBe(1);
  expect(selection).toHaveBeenCalledTimes(1);
});

it.each([...ROWS.filter((row) => row !== "chat.export_pdf"), "drawer.select"])(
  "the drawer row's long-press menu %s plays one haptic",
  async (row) => {
    const view = await render(<ConversationList />);
    await act(async () => {
      fireEvent.press(view.getByRole("menuitem", { name: row }));
    });
    expect(hapticCount()).toBe(1);
    expect(selection).toHaveBeenCalledTimes(1);
  },
);
