import React from "react";
import { Alert, Text } from "react-native";
import { act, render } from "@testing-library/react-native";

import { useChatActions } from "@/features/chat/hooks/useChatActions";
import { api, type Chat } from "@/lib/api";
import { getCachedChat } from "@/features/chat/model/chatListCache";
import { abandonActiveChatIfDeleted, insertChatGlobal, patchChatGlobal } from "@/features/chat/drawer/drawer";
import { clearCachedChatMessages } from "@/features/chat/model/messageCache";

let mockSession = 0;
const mockError = jest.fn();
const mockDestructive = jest.fn();
jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => mockSession }));
jest.mock("@/contexts/actionFeedbackCore", () => ({ useActionFeedbackOptional: () => ({ error: mockError }) }));
jest.mock("@/features/chat/model/chatListCache", () => ({ getCachedChat: jest.fn(), peekCreatedChat: jest.fn() }));
jest.mock("@/lib/api", () => ({ api: { getChat: jest.fn(), renameChat: jest.fn(), setPin: jest.fn(), setArchive: jest.fn(), deleteChat: jest.fn() } }));
jest.mock("@/features/chat/drawer/drawer", () => ({
  insertChatGlobal: jest.fn(), patchChatGlobal: jest.fn(),
  removeChatGlobal: jest.fn(), abandonActiveChatIfDeleted: jest.fn(),
}));
jest.mock("@/features/chat/model/messageCache", () => ({ clearCachedChatMessages: jest.fn() }));
jest.mock("@/features/chat/model/exportMessagePdf", () => ({ exportConversationAsPdf: jest.fn() }));
jest.mock("@/lib/haptics", () => ({
  ...jest.requireActual("@/lib/haptics"),
  notifyDestructive: (...args: unknown[]) => mockDestructive(...args),
  tap: jest.fn(),
}));

const chat: Chat = {
  id: "chat-1", title: "Old title", model: "free-chat", pinned: false, archived: false,
  created_at: "2026-01-01", updated_at: "2026-01-01",
};
const setChatTitle = jest.fn();
const setPinned = jest.fn();
const setArchived = jest.fn();
let actions: ReturnType<typeof useChatActions>;
function Probe({ chatId = "chat-1", token = "token", pinned = false, archived = false }: {
  chatId?: string; token?: string; pinned?: boolean; archived?: boolean;
}) {
  const value = useChatActions({
    token, chatId, chatTitle: "Old title", messages: [], pinned, archived,
    setPinned, setArchived, setChatTitle, editThread: jest.fn(), t: (key) => key,
  });
  React.useLayoutEffect(() => { actions = value; });
  return <Text>Actions</Text>;
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function deletePress() {
  const buttons = (Alert.alert as jest.Mock).mock.calls.at(-1)?.[2] as { style?: string; onPress?: () => Promise<void> }[];
  return buttons.find((button) => button.style === "destructive")!.onPress!;
}
beforeEach(() => {
  jest.clearAllMocks(); mockSession = 0;
  jest.mocked(getCachedChat).mockReturnValue(undefined);
  jest.spyOn(Alert, "alert").mockImplementation(() => {});
});

describe.each([
  ["rename", "renameChat", "confirmRename", setChatTitle],
  ["pin", "setPin", "togglePin", setPinned],
  ["archive", "setArchive", "toggleArchive", setArchived],
] as const)("%s lifetime", (_name, apiMethod, action, setter) => {
  it.each(["resolve", "reject"] as const)("does not update a different chat when its request %ss", async (outcome) => {
    const request = deferred<Chat>();
    (api[apiMethod] as jest.Mock).mockReturnValue(request.promise);
    const view = await render(<Probe />);
    await act(async () => { actions.setRenameText("New title"); });
    let pending!: Promise<void>;
    await act(async () => { pending = actions[action](); });
    await view.rerender(<Probe chatId="chat-2" />);
    setter.mockClear();
    await act(async () => {
      if (outcome === "resolve") request.resolve({ ...chat, title: "Saved", pinned: apiMethod === "setPin", archived: apiMethod === "setArchive" });
      else request.reject(new Error("offline"));
      await pending;
    });
    expect(setter).not.toHaveBeenCalled();
    expect(mockError).not.toHaveBeenCalled();
    expect(actions.actionBanner).toBeNull();
  });
});

it("does not reconcile an old account's rename into the next account", async () => {
  const request = deferred<Chat>();
  (api.renameChat as jest.Mock).mockReturnValue(request.promise);
  const view = await render(<Probe />);
  await act(async () => { actions.setRenameText("New title"); });
  let pending!: Promise<void>;
  await act(async () => { pending = actions.confirmRename(); });
  mockSession++;
  await view.rerender(<Probe token="account-2" />);
  jest.mocked(patchChatGlobal).mockClear(); setChatTitle.mockClear();
  await act(async () => { request.resolve({ ...chat, title: "Old account" }); await pending; });
  expect(setChatTitle).not.toHaveBeenCalled();
  expect(patchChatGlobal).not.toHaveBeenCalled();
  expect(actions.actionBanner).toBeNull();
});

it("updates the drawer pin immediately and rolls it back on failure", async () => {
  (api.setPin as jest.Mock).mockRejectedValue(new Error("offline"));
  await render(<Probe />);
  await act(async () => { await actions.togglePin(); });
  expect(patchChatGlobal).toHaveBeenNthCalledWith(1, "chat-1", { pinned: true });
  expect(patchChatGlobal).toHaveBeenNthCalledWith(2, "chat-1", { pinned: false });
});

it("ignores a retained delete confirmation after navigating to another chat", async () => {
  const view = await render(<Probe />);
  await act(async () => { actions.confirmDelete(); });
  const confirm = deletePress();
  await view.rerender(<Probe chatId="chat-2" />);
  await act(async () => { await confirm(); });
  expect(api.deleteChat).not.toHaveBeenCalled();
});

it("ignores a retained delete confirmation immediately after account invalidation", async () => {
  await render(<Probe />);
  await act(async () => { actions.confirmDelete(); });
  const confirm = deletePress();
  mockSession++;
  await act(async () => { await confirm(); });
  expect(api.deleteChat).not.toHaveBeenCalled();
});

it("clears the active deleted conversation through the registered new-chat action", async () => {
  (api.deleteChat as jest.Mock).mockResolvedValue(undefined);
  await render(<Probe />);
  await act(async () => { actions.confirmDelete(); });
  await act(async () => { await deletePress()(); });
  expect(clearCachedChatMessages).toHaveBeenCalledWith("chat-1");
  expect(abandonActiveChatIfDeleted).toHaveBeenCalledWith(["chat-1"]);
});

it("haptics only after the confirmed chat deletion succeeds", async () => {
  const request = deferred<void>();
  (api.deleteChat as jest.Mock).mockReturnValue(request.promise);
  await render(<Probe />);

  await act(async () => { actions.confirmDelete(); });
  expect(mockDestructive).not.toHaveBeenCalled();

  let pending!: Promise<void>;
  await act(async () => { pending = deletePress()(); });
  expect(mockDestructive).not.toHaveBeenCalled();

  await act(async () => { request.resolve(); await pending; });
  expect(mockDestructive).toHaveBeenCalledTimes(1);
});

it("coalesces repeated archive taps while the mutation is pending, including token refresh", async () => {
  const request = deferred<Chat>();
  (api.setArchive as jest.Mock).mockReturnValue(request.promise);
  const view = await render(<Probe />);
  let pending!: Promise<void>;
  await act(async () => { pending = actions.toggleArchive(); });
  await view.rerender(<Probe token="refreshed-token" />);
  await act(async () => { void actions.toggleArchive(); });
  expect(api.setArchive).toHaveBeenCalledTimes(1);
  await act(async () => { request.resolve({ ...chat, title: "Saved", archived: true }); await pending; });
  expect(actions.actionBanner?.message).toBe("chat.archived_toast");
  expect(patchChatGlobal).toHaveBeenCalledWith("chat-1", { archived: true, pinned: false });
});

it("closes a rename editor when its conversation changes", async () => {
  const view = await render(<Probe />);
  await act(async () => { actions.openRename(); actions.setRenameText("Unsaved old title"); });
  await view.rerender(<Probe chatId="chat-2" />);
  expect(actions.renameVisible).toBe(false);
  expect(actions.renameText).toBe("");
});

it("restores the original dated project chat after a failed delete", async () => {
  const original = { id: "chat-1", title: "Old project", model: "free-chat", pinned: true,
    archived: false, created_at: "2025-01-01", updated_at: "2025-02-01" } as Chat;
  jest.mocked(getCachedChat).mockReturnValue(original);
  (api.deleteChat as jest.Mock).mockRejectedValue(new Error("offline"));
  await render(<Probe />);
  await act(async () => { actions.confirmDelete(); });
  await act(async () => { await deletePress()(); });
  expect(insertChatGlobal).toHaveBeenCalledWith(original);
  expect(api.getChat).not.toHaveBeenCalled();
});

it("recovers real metadata after a failed delete when the chat was outside the cached list", async () => {
  const original = { id: "chat-1", title: "Older than list", updated_at: "2025-02-01" } as Chat;
  (api.deleteChat as jest.Mock).mockRejectedValue(new Error("offline"));
  (api.getChat as jest.Mock).mockResolvedValue(original);
  await render(<Probe />);
  await act(async () => { actions.confirmDelete(); });
  await act(async () => { await deletePress()(); });
  expect(api.getChat).toHaveBeenCalledWith("token", "chat-1");
  expect(insertChatGlobal).toHaveBeenCalledWith(original);
  expect(mockError).toHaveBeenCalledWith("chat.delete_failed");
});

it.each([
  { name: "pin", action: "togglePin", method: "setPin", initialPinned: false, initialArchived: false, pinned: false, archived: true, toast: "chat.unpinned_toast" },
  { name: "unpin", action: "togglePin", method: "setPin", initialPinned: true, initialArchived: false, pinned: true, archived: false, toast: "chat.pinned_toast" },
  { name: "archive", action: "toggleArchive", method: "setArchive", initialPinned: true, initialArchived: false, pinned: true, archived: false, toast: "chat.unarchived_toast" },
  { name: "unarchive", action: "toggleArchive", method: "setArchive", initialPinned: false, initialArchived: true, pinned: false, archived: true, toast: "chat.archived_toast" },
] as const)("reconciles $name with the returned server flags after another device changes them", async (testCase) => {
  const saved = { ...chat, pinned: testCase.pinned, archived: testCase.archived };
  jest.mocked(api[testCase.method]).mockResolvedValue(saved);
  await render(<Probe pinned={testCase.initialPinned} archived={testCase.initialArchived} />);
  await act(async () => { await actions[testCase.action](); });
  expect(api[testCase.method]).toHaveBeenCalledWith("token", chat.id,
    !(testCase.method === "setPin" ? testCase.initialPinned : testCase.initialArchived));
  expect(setPinned).toHaveBeenLastCalledWith(saved.pinned);
  expect(setArchived).toHaveBeenLastCalledWith(saved.archived);
  expect(patchChatGlobal).toHaveBeenLastCalledWith(chat.id, { pinned: saved.pinned, archived: saved.archived });
  expect(actions.actionBanner?.message).toBe(testCase.toast);
});

it("keeps the rename editor open and says why when the title is blank, like the drawer", async () => {
  await render(<Probe />);
  await act(async () => { actions.openRename(); actions.setRenameText("   "); });
  await act(async () => { await actions.confirmRename(); });
  expect(actions.renameVisible).toBe(true);
  expect(api.renameChat).not.toHaveBeenCalled();
  expect(mockError).toHaveBeenCalledWith("chat.rename_blank");
});

it("names an archive failure the same way the drawer does", async () => {
  (api.setArchive as jest.Mock).mockRejectedValueOnce(new Error("offline"));
  await render(<Probe />);
  await act(async () => { await actions.toggleArchive(); });
  expect(mockError).toHaveBeenCalledWith("chat.archive_failed");
  expect(patchChatGlobal).toHaveBeenLastCalledWith("chat-1", { archived: false, pinned: false });
});
