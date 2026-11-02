import { keepCachedChatPage, shouldSkipChatPageRead } from "@/features/chat/model/messageCache";
import { chatPageReadAt, noteChatPageRead } from "@/features/chat/model/pageReads";
import type { Message } from "@/lib/api";

jest.mock("expo-file-system/legacy", () => ({ cacheDirectory: null }));
jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => mockSession }));
let mockSession = 1;

const row = (id: string): Message => ({
  id, role: "user", content: "Hi", model: null, created_at: "2026-10-24T12:00:00Z",
} as Message);
const SAVED = "00000000-0000-4000-8200-000000000001";

beforeEach(() => {
  jest.useFakeTimers();
  jest.setSystemTime(Date.parse("2026-10-24T12:00:00Z"));
});
afterEach(() => jest.useRealTimers());

it("counts a read of the chat's page within the stale window, any path's, by this sign-in only", async () => {
  noteChatPageRead("a");
  jest.advanceTimersByTime(19_000);
  expect(await shouldSkipChatPageRead("a")).toBe(true);
  expect(await shouldSkipChatPageRead("a", true)).toBe(false);
  jest.advanceTimersByTime(1_000);
  expect(await shouldSkipChatPageRead("a")).toBe(false);

  noteChatPageRead("b");
  mockSession = 2;
  expect(await shouldSkipChatPageRead("b")).toBe(false);
  expect(chatPageReadAt("b")).toBeUndefined();
});

it("counts the page kept for the chat as this sign-in's read then", async () => {
  const since = Date.now();
  jest.advanceTimersByTime(1_000);
  keepCachedChatPage("c", [row(SAVED)], false, Date.now());
  expect(chatPageReadAt("c")).toBeUndefined();
  expect(await shouldSkipChatPageRead("c")).toBe(true);
  expect(chatPageReadAt("c")).toBe(since + 1_000);
});
