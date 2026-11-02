import React from "react";
import { Text } from "react-native";
import { act, render } from "@testing-library/react-native";
import { useDrawerChatList } from "@/features/chat/drawer/useDrawerChatList";
import { api, type ChatList } from "@/lib/api";
import { getCachedChatList, invalidateChatListCache, setChatListCache } from "@/features/chat/model/chatListCache";
import { readStoredChatList } from "@/features/chat/model/chatListFile";
import { emptyChatList } from "@/features/chat/model/listSections";
import { patchChatGlobal, subscribeChatChanges } from "@/features/chat/drawer/drawer";

let mockSession = 0;
jest.mock("@/lib/auth", () => ({
  getSessionGeneration: () => mockSession,
  requireTokenSession: jest.fn(),
  SessionChangedError: class SessionChangedError extends Error {},
}));
jest.mock("@/lib/api", () => ({ api: { listChats: jest.fn(), listOlderChats: jest.fn() } }));
// The read after an outage needs the screen's focus (requestCensus covers it).
jest.mock("expo-router", () => ({ useFocusEffect: () => undefined }));
jest.mock("@/features/chat/model/chatListFile", () => ({
  readStoredChatList: jest.fn(async () => null),
  writeStoredChatList: jest.fn(async () => undefined),
  clearStoredChatList: jest.fn(async () => undefined),
}));
// The signed-in account (per session) and its access token, which rotates hourly.
let mockToken: string | null = "token";
const mockGetToken = () => mockToken;
jest.mock("@/contexts/accountSession", () => ({
  useAccountSession: () => ({ account: mockToken ? `account:${mockSession}` : null, getToken: mockGetToken }),
}));
const mockIdle: (() => void)[] = [];
jest.mock("@/lib/scheduleIdle", () => ({
  scheduleIdleTask: (task: () => void) => { mockIdle.push(task); return jest.fn(); },
}));
const mockWarn = jest.fn();
jest.mock("@/lib/reportRecoverableError", () => ({
  reportRecoverableWarning: (_feedback: unknown, message: string) => mockWarn(message),
}));
const chat = { id: "old", title: "Original", model: "free-chat", pinned: false, updated_at: "2026-01-01T00:00:00Z", created_at: "2026-01-01T00:00:00Z" };
const initial = { ...emptyChatList(), older: [chat] };
let current: ReturnType<typeof useDrawerChatList>;
function Probe({ open = true }: { open?: boolean }) {
  const result = useDrawerChatList({ isDrawerOpen: open });
  React.useLayoutEffect(() => { current = result; });
  return <Text>{result.allChats.map((row) => row.title).join(",")}</Text>;
}
beforeEach(() => {
  jest.clearAllMocks(); mockSession = 0; mockToken = "token"; mockIdle.length = 0; invalidateChatListCache();
});

it("hides account A immediately and rejects its late read after account B signs in", async () => {
  let finish!: (value: ChatList) => void;
  (api.listChats as jest.Mock).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
  const view = await render(<Probe />);
  mockSession++;
  (api.listChats as jest.Mock).mockResolvedValueOnce({ ...emptyChatList(), today: [{ ...chat, id: "b", title: "Account B" }] });
  mockToken = "b-token";
  await view.rerender(<Probe />);
  expect(current.allChats.map((row) => row.id)).toEqual(["b"]);
  await act(async () => { finish(initial); });
  expect(current.allChats.map((row) => row.id)).toEqual(["b"]);
  expect(current.error).toBe(false);
});

it("retains loaded rows through access-token refresh without another list request", async () => {
  setChatListCache(initial);
  const view = await render(<Probe />);
  mockToken = "rotated-token";
  await view.rerender(<Probe />);
  expect(current.allChats).toEqual([chat]);
  expect(api.listChats).not.toHaveBeenCalled();
});

it("reconciles pin/rename edits over a stale refresh and broadcasts the same metadata", async () => {
  setChatListCache(initial);
  await render(<Probe />);
  let finish!: (value: ChatList) => void;
  (api.listChats as jest.Mock).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
  const changed = jest.fn();
  const unsubscribe = subscribeChatChanges(changed);
  let read!: Promise<void>;
  await act(async () => { read = current.handleRefresh(); });
  await act(async () => { patchChatGlobal(chat.id, { pinned: true, title: "Renamed" }); });
  await act(async () => { finish(initial); await read; });
  expect(current.groups.pinned[0]).toMatchObject({ id: "old", title: "Renamed", pinned: true });
  expect(current.groups.older).toEqual([]);
  expect(getCachedChatList()).toEqual(current.groups);
  expect(changed).toHaveBeenCalledWith(chat.id, { pinned: true, title: "Renamed" });
  unsubscribe();
});

it("preserves visible history and allows retry after a failed refresh", async () => {
  setChatListCache(initial);
  await render(<Probe />);
  (api.listChats as jest.Mock).mockRejectedValueOnce(new Error("offline"));
  await act(async () => { await current.handleRefresh(); });
  expect(current.allChats).toEqual([chat]);
  expect(current.error).toBe(true);
  expect(current.refreshing).toBe(false);
  (api.listChats as jest.Mock).mockResolvedValueOnce(initial);
  await act(async () => { await current.handleRefresh(); });
  expect(current.error).toBe(false);
});

it.each([
  ["a server error", Object.assign(new Error("Request failed: 500"), { status: 500 }), ["common.error"]],
  ["being offline", new TypeError("Network request failed"), []],
])("warns about %s only while older chats stay listed", async (_name, failure, warnings) => {
  setChatListCache(initial);
  await render(<Probe />);
  (api.listChats as jest.Mock).mockRejectedValueOnce(failure);
  await act(async () => { await current.handleRefresh(); });
  expect(current.allChats).toEqual([chat]);
  expect(mockWarn.mock.calls.map(([message]) => message)).toEqual(warnings);
});

it("leaves a first failed load to the error state without a warning", async () => {
  (api.listChats as jest.Mock).mockRejectedValueOnce(Object.assign(new Error("Request failed: 500"), { status: 500 }));
  await render(<Probe />);
  await act(async () => { await Promise.resolve(); });
  expect(current.error).toBe(true);
  expect(mockWarn).not.toHaveBeenCalled();
});

it("does not paint a resolved response over an edit queued before the hook resumes", async () => {
  setChatListCache(initial);
  await render(<Probe />);
  let finish!: (value: ChatList) => void;
  (api.listChats as jest.Mock).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
  let read!: Promise<void>;
  await act(async () => { read = current.handleRefresh(); });
  await act(async () => {
    finish(initial);
    await Promise.resolve();
    patchChatGlobal(chat.id, { title: "Newest edit" });
    await read;
  });
  expect(current.allChats[0].title).toBe("Newest edit");
  expect(getCachedChatList()).toEqual(current.groups);
});

it("paints the chats this account had last time while the list is read again", async () => {
  const encode = (value: unknown) => btoa(JSON.stringify(value)).replace(/=/g, "");
  const token = `${encode({ alg: "HS256" })}.${encode({ sub: "user-1" })}.signature`;
  const stored = { ...emptyChatList(), today: [{ ...chat, id: "stored", title: "From last time" }] };
  (readStoredChatList as jest.Mock).mockResolvedValueOnce(stored);
  let finish!: (value: ChatList) => void;
  (api.listChats as jest.Mock).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
  mockToken = token;
  await render(<Probe />);
  await act(async () => { await Promise.resolve(); });
  expect(readStoredChatList).toHaveBeenCalledWith("user-1");
  expect(current.allChats.map((row) => row.title)).toEqual(["From last time"]);
  expect(api.listChats).toHaveBeenCalledTimes(1);
  await act(async () => { finish(initial); });
  expect(current.allChats).toEqual([chat]);
});

it("reads the list on the next drawer open when the first read after a cold start failed", async () => {
  const encode = (value: unknown) => btoa(JSON.stringify(value)).replace(/=/g, "");
  const token = `${encode({ alg: "HS256" })}.${encode({ sub: "user-1" })}.signature`;
  const stored = { ...emptyChatList(), today: [{ ...chat, id: "stored", title: "From last time" }] };
  (readStoredChatList as jest.Mock).mockResolvedValueOnce(stored);
  (api.listChats as jest.Mock).mockRejectedValueOnce(new TypeError("Network request failed"));
  mockToken = token;
  const view = await render(<Probe open={false} />);
  await act(async () => { await Promise.resolve(); });
  expect(current.allChats.map((row) => row.title)).toEqual(["From last time"]);
  // The closed drawer's warm-up read fails: the list shown is still the one from disk.
  await act(async () => {
    mockIdle.splice(0).forEach((task) => task());
    for (let i = 0; i < 5; i++) await Promise.resolve();
  });
  expect(api.listChats).toHaveBeenCalledTimes(1);
  expect(current.allChats.map((row) => row.title)).toEqual(["From last time"]);
  const laptop = { ...emptyChatList(), today: [{ ...chat, id: "new", title: "Created on laptop" }] };
  (api.listChats as jest.Mock).mockResolvedValueOnce(laptop);
  await view.rerender(<Probe open />);
  await act(async () => { await Promise.resolve(); });
  expect(api.listChats).toHaveBeenCalledTimes(2);
  expect(current.allChats.map((row) => row.title)).toEqual(["Created on laptop"]);
});

it("reads older chats once at a time and appends them (CLAR-12)", async () => {
  (api.listChats as jest.Mock).mockResolvedValueOnce({ ...initial, next_cursor: "after-old" });
  let finish!: (value: ChatList) => void;
  (api.listOlderChats as jest.Mock).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
  await render(<Probe />);
  await act(async () => {});
  expect(current.hasOlderChats).toBe(true);
  let first!: Promise<void>;
  await act(async () => { first = current.loadOlderChats(); void current.loadOlderChats(); });
  expect(api.listOlderChats).toHaveBeenCalledTimes(1);
  await act(async () => { finish({ ...emptyChatList(), older: [{ ...chat, id: "older", title: "Older" }], next_cursor: null }); await first; });
  expect(current.allChats.map((row) => row.id)).toEqual(["old", "older"]);
  expect(current.hasOlderChats).toBe(false);
});

it("keeps the chats shown and warns when an older page fails", async () => {
  (api.listChats as jest.Mock).mockResolvedValueOnce({ ...initial, next_cursor: "after-old" });
  (api.listOlderChats as jest.Mock).mockRejectedValueOnce(Object.assign(new Error("Server error"), { status: 500 }));
  await render(<Probe />);
  await act(async () => {});
  await act(async () => { await current.loadOlderChats(); });
  expect(current.allChats.map((row) => row.id)).toEqual(["old"]);
  expect(current.hasOlderChats).toBe(true);
  expect(mockWarn).toHaveBeenCalledTimes(1);

});
