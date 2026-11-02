import React from "react";
import { Text } from "react-native";
import { act, render } from "@testing-library/react-native";
import { useChatBulkActions } from "@/features/chat/hooks/useChatBulkActions";
import { api, type Chat } from "@/lib/api";
import { abandonActiveChatIfDeleted } from "@/features/chat/drawer/drawer";
import { clearCachedChatMessages } from "@/features/chat/model/messageCache";
import { getCachedChat } from "@/features/chat/model/chatListCache";
import { onAppEvent } from "@/lib/appEvents";

let mockSession = 0;
const mockError = jest.fn();
const mockDestructive = jest.fn();
const mockT = jest.fn((key: string, _options?: Record<string, unknown>) => key);
jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => mockSession }));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: mockT }) }));
jest.mock("@/contexts/actionFeedbackCore", () => ({ useActionFeedbackOptional: () => ({ error: mockError }) }));
jest.mock("@/lib/api", () => ({ api: { bulkChats: jest.fn() } }));
jest.mock("@/features/chat/drawer/drawer", () => ({ abandonActiveChatIfDeleted: jest.fn() }));
jest.mock("@/features/chat/model/messageCache", () => ({ clearCachedChatMessages: jest.fn() }));
jest.mock("@/features/chat/model/chatListCache", () => ({ getCachedChat: jest.fn() }));
const chatsDeleted = jest.fn();
onAppEvent("chatsDeleted", chatsDeleted);
jest.mock("@/lib/haptics", () => ({
  ...jest.requireActual("@/lib/haptics"),
  notifyDestructive: (...args: unknown[]) => mockDestructive(...args),
}));
const first: Chat = {
  id: "first", title: "First", pinned: true, archived: false, model: "free-chat",
  created_at: "2026-01-01", updated_at: "2026-01-01",
};
const second: Chat = { ...first, id: "second", title: "Second", pinned: false };
const insertChatInGroups = jest.fn();
const patchChatInGroups = jest.fn();
const moveChatArchiveState = jest.fn();
const removeChatFromGroupsById = jest.fn();
const reloadChats = jest.fn();
const showActionBanner = jest.fn();
let actions: ReturnType<typeof useChatBulkActions>;
function Probe({ token = "token", isDrawerOpen = true }: { token?: string; isDrawerOpen?: boolean }) {
  const value = useChatBulkActions({ token, isDrawerOpen, insertChatInGroups, patchChatInGroups, moveChatArchiveState,
    removeChatFromGroupsById, reloadChats, showActionBanner });
  React.useLayoutEffect(() => { actions = value; });
  return <Text>Bulk actions</Text>;
}
// The test answers the confirm dialog for the person. Answering returns the
// rest of the flow so a test can wait for it.
let mockAnswer: ((ok: boolean) => Promise<void>) | null = null;
jest.mock("@/ui/overlay/dialogs", () => ({
  confirmDialog: () => ({
    then: (handler: (ok: boolean) => Promise<void>) => {
      mockAnswer = handler;
    },
  }),
}));
function confirmation() {
  const answer = mockAnswer!;
  return () => answer(true);
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
type Changed = { changed: string[] };
const bulkChats = api.bulkChats as jest.Mock;
beforeEach(() => {
  jest.clearAllMocks(); mockSession = 0; mockAnswer = null;
  jest.mocked(getCachedChat).mockReturnValue(undefined);
});

it("keeps successful deletes removed, clears their cache and abandons only deleted active chats on partial failure", async () => {
  bulkChats.mockResolvedValue({ changed: [first.id] });
  await render(<Probe />);
  const complete = jest.fn();
  await act(async () => { actions.bulkDeleteChats([first, second], complete); });
  await act(async () => { await confirmation()(); });
  expect(bulkChats).toHaveBeenCalledTimes(1);
  expect(bulkChats).toHaveBeenCalledWith("token", "delete", [first.id, second.id]);
  expect(insertChatInGroups).toHaveBeenCalledTimes(1);
  expect(insertChatInGroups).toHaveBeenCalledWith(second);
  expect(clearCachedChatMessages).toHaveBeenCalledWith(first.id);
  expect(clearCachedChatMessages).not.toHaveBeenCalledWith(second.id);
  expect(chatsDeleted).toHaveBeenCalledWith({ chatIds: [first.id] });
  expect(abandonActiveChatIfDeleted).toHaveBeenCalledWith([first.id]);
  expect(complete).not.toHaveBeenCalled();
  expect(mockError).toHaveBeenCalledWith("chat.delete_failed");
  expect(mockDestructive).not.toHaveBeenCalled();
});

it("haptics once only after confirmed bulk deletion has a successful result", async () => {
  const request = deferred<Changed>();
  bulkChats.mockReturnValue(request.promise);
  await render(<Probe />);

  await act(async () => { actions.bulkDeleteChats([first]); });
  expect(mockDestructive).not.toHaveBeenCalled();

  let pending!: Promise<void>;
  await act(async () => { pending = confirmation()(); });
  expect(mockDestructive).not.toHaveBeenCalled();

  await act(async () => { request.resolve({ changed: [first.id] }); await pending; });
  expect(mockDestructive).toHaveBeenCalledTimes(1);
});

it("waits for the archive result and restores only the chats it did not change, pins included", async () => {
  const request = deferred<Changed>();
  bulkChats.mockReturnValue(request.promise);
  await render(<Probe />);
  await act(async () => { actions.bulkArchiveChats([first, second]); });
  let pending!: Promise<void>;
  await act(async () => { pending = confirmation()(); });
  expect(reloadChats).not.toHaveBeenCalled();
  expect(insertChatInGroups).not.toHaveBeenCalled();
  await act(async () => { request.resolve({ changed: [second.id] }); await pending; });
  expect(bulkChats).toHaveBeenCalledWith("token", "archive", [first.id, second.id]);
  expect(patchChatInGroups).toHaveBeenCalledTimes(2);
  expect(patchChatInGroups).toHaveBeenCalledWith(first.id, first);
  expect(patchChatInGroups).toHaveBeenCalledWith(second.id, { pinned: false, archived: true });
  expect(moveChatArchiveState).not.toHaveBeenCalledWith(second.id, false);
  expect(mockError).toHaveBeenCalledWith("chat.archive_failed");
});

it("restores every chat when the archive request fails", async () => {
  bulkChats.mockRejectedValue(new Error("offline"));
  await render(<Probe />);
  await act(async () => { actions.bulkArchiveChats([first, second]); });
  await act(async () => { await confirmation()(); });
  expect(patchChatInGroups).toHaveBeenCalledWith(first.id, first);
  expect(patchChatInGroups).toHaveBeenCalledWith(second.id, second);
  expect(reloadChats).toHaveBeenCalledTimes(1);
  expect(mockError).toHaveBeenCalledWith("chat.archive_failed");
});

it("sends a selection past the server's cap in parts of 200", async () => {
  const many = Array.from({ length: 450 }, (_, index) => ({ ...second, id: `c${index}` }));
  bulkChats.mockImplementation(async (_token: string, _action: string, ids: string[]) => ({ changed: ids }));
  await render(<Probe />);
  await act(async () => { actions.bulkDeleteChats(many); });
  await act(async () => { await confirmation()(); });
  expect(bulkChats.mock.calls.map((call) => (call[2] as string[]).length)).toEqual([200, 200, 50]);
  expect(chatsDeleted).toHaveBeenCalledWith({ chatIds: many.map((chat) => chat.id) });
});

it.each(["bulkArchiveChats", "bulkDeleteChats"] as const)("ignores %s confirmation after drawer closes", async (method) => {
  const view = await render(<Probe />);
  await act(async () => { actions[method]([first]); });
  const confirm = confirmation();
  await view.rerender(<Probe isDrawerOpen={false} />);
  await act(async () => { await confirm(); });
  expect(bulkChats).not.toHaveBeenCalled();
});

it("ignores an old batch's result after account invalidation before a rerender", async () => {
  const request = deferred<Changed>();
  bulkChats.mockReturnValue(request.promise);
  await render(<Probe />);
  await act(async () => { actions.bulkDeleteChats([first]); });
  let pending!: Promise<void>;
  await act(async () => { pending = confirmation()(); });
  mockSession++;
  await act(async () => { request.resolve({ changed: [first.id] }); await pending; });
  expect(clearCachedChatMessages).not.toHaveBeenCalled();
  expect(abandonActiveChatIfDeleted).not.toHaveBeenCalled();
  expect(showActionBanner).not.toHaveBeenCalled();
});

it("does not apply an old batch's success callback to a reopened drawer", async () => {
  const request = deferred<Changed>();
  bulkChats.mockReturnValue(request.promise);
  const view = await render(<Probe />);
  const complete = jest.fn();
  await act(async () => { actions.bulkDeleteChats([first], complete); });
  let pending!: Promise<void>;
  await act(async () => { pending = confirmation()(); });
  await view.rerender(<Probe isDrawerOpen={false} />);
  await view.rerender(<Probe />);
  await act(async () => { request.resolve({ changed: [first.id] }); await pending; });
  expect(clearCachedChatMessages).toHaveBeenCalledWith(first.id);
  expect(complete).not.toHaveBeenCalled();
  expect(showActionBanner).not.toHaveBeenCalled();
});

it("uses the latest row at confirmation when restoring a failed archive", async () => {
  const latest = { ...first, title: "Renamed before confirmation", pinned: false };
  bulkChats.mockRejectedValue(new Error("offline"));
  await render(<Probe />);
  await act(async () => { actions.bulkArchiveChats([first]); });
  jest.mocked(getCachedChat).mockReturnValue(latest);
  await act(async () => { await confirmation()(); });
  expect(patchChatInGroups).toHaveBeenCalledWith(first.id, latest);
});

it("reports the number of chats the server archived", async () => {
  bulkChats.mockResolvedValue({ changed: [first.id, second.id] });
  const complete = jest.fn();
  await render(<Probe />);
  await act(async () => { actions.bulkArchiveChats([first, second], complete); });
  await act(async () => { await confirmation()(); });
  expect(patchChatInGroups).toHaveBeenCalledWith(first.id, { pinned: false, archived: true });
  expect(patchChatInGroups).toHaveBeenCalledWith(second.id, { pinned: false, archived: true });
  expect(mockT).toHaveBeenCalledWith("drawer.bulk_archived_toast", { count: 2 });
  expect(complete).toHaveBeenCalledTimes(1);
  expect(mockError).not.toHaveBeenCalled();
});
