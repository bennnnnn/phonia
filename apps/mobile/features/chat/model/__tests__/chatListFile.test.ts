import { clearStoredChatList, readStoredChatList, writeStoredChatList } from "@/features/chat/model/chatListFile";
import type { Chat, ChatList } from "@/lib/api";
import { emptyChatList } from "@/features/chat/model/listSections";

const mockFiles = new Map<string, string>();
jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "/mock-cache/",
  getInfoAsync: jest.fn(async (path: string) => ({ exists: mockFiles.has(path) })),
  readAsStringAsync: jest.fn(async (path: string) => mockFiles.get(path)),
  writeAsStringAsync: jest.fn(async (path: string, contents: string) => { mockFiles.set(path, contents); }),
  deleteAsync: jest.fn(async (path: string) => { mockFiles.delete(path); }),
}));

const PATH = "/mock-cache/cached-chat-list.json";
const chat = (id: string, extra: Partial<Chat> = {}): Chat => ({
  id, title: id, model: "free-chat", pinned: false,
  created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", ...extra,
});
const list: ChatList = { ...emptyChatList(), pinned: [chat("p", { pinned: true })], today: [chat("t")], archived: [chat("a", { archived: true })] };

beforeEach(() => mockFiles.clear());

it("reads back the list this account wrote", async () => {
  await writeStoredChatList("user-1", list);
  await expect(readStoredChatList("user-1")).resolves.toEqual(list);
});

it("never shows another account's list", async () => {
  await writeStoredChatList("user-1", list);
  await expect(readStoredChatList("user-2")).resolves.toBeNull();
});

it("reads nothing once cleared", async () => {
  await writeStoredChatList("user-1", list);
  await clearStoredChatList();
  await expect(readStoredChatList("user-1")).resolves.toBeNull();
});

it("leaves out a row it cannot read and keeps the rest", async () => {
  mockFiles.set(PATH, JSON.stringify({
    user_id: "user-1",
    list: { ...list, today: [chat("t"), { id: 7, title: "broken" }, { ...chat("u"), extra: "dropped" }] },
  }));
  const stored = await readStoredChatList("user-1");
  expect(stored?.today).toEqual([chat("t"), chat("u")]);
});

it.each([
  ["unreadable text", "{not json"],
  ["a missing group", JSON.stringify({ user_id: "user-1", list: { pinned: [] } })],
  ["no owner", JSON.stringify({ list })],
])("reads %s as nothing", async (_name, contents) => {
  mockFiles.set(PATH, contents);
  await expect(readStoredChatList("user-1")).resolves.toBeNull();
});
