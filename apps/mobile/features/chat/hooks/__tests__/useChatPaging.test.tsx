import { useState } from "react";
import { act, renderHook } from "@testing-library/react-native";

import { useChatPaging } from "@/features/chat/hooks/useChatPaging";
import { api, type Message } from "@/lib/api";
import { writeCachedChatMessages } from "@/features/chat/model/messageCache";

jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => 0 }));
jest.mock("@/lib/api", () => ({ api: { listMessages: jest.fn() } }));
jest.mock("@/features/chat/model/messageCache", () => ({ writeCachedChatMessages: jest.fn(async () => undefined) }));

const id = (n: number) => `0190a000-0000-7000-8000-${String(n).padStart(12, "0")}`;
const msg = (n: number): Message => ({ id: id(n), role: n % 2 ? "assistant" : "user", content: `m${n}`, model: null, created_at: "t" });
const range = (from: number, to: number) => Array.from({ length: to - from + 1 }, (_, i) => msg(from + i));
const list = jest.mocked(api.listMessages);

async function setup(initial: Message[] = range(960, 999), more = true) {
  const viewRef = { current: { version: 0 } };
  const activeChatRef = { current: "chat-1" as string | null };
  const banner = jest.fn();
  const hook = await renderHook(() => {
    const [messages, setMessages] = useState(initial);
    const [hasMoreOlder, setHasMoreOlder] = useState(more);
    const paging = useChatPaging({
      token: "token", chatId: "chat-1", chatLoading: false, messages, editThread: setMessages, hasMoreOlder, setHasMoreOlder,
      viewRef, activeChatRef, showActionBanner: banner, t: (key) => key,
    });
    return { paging, messages, hasMoreOlder };
  });
  return { hook, viewRef, banner };
}
const contents = (messages: Message[]) => messages.map((m) => m.content);

beforeEach(() => jest.clearAllMocks());

it("shows the window around a hit, with newer pages to follow (NET-18)", async () => {
  const { hook } = await setup();
  list.mockResolvedValueOnce({ messages: range(80, 119), has_more: true, has_more_after: true });
  let shown = false;
  await act(async () => { shown = await hook.result.current.paging.openAround(id(100)); });
  expect(shown).toBe(true);
  expect(list).toHaveBeenCalledWith("token", "chat-1", { limit: 40, around: id(100) });
  expect(contents(hook.result.current.messages)).toEqual(contents(range(80, 119)));
  expect(hook.result.current.hasMoreOlder).toBe(true);
  expect(hook.result.current.paging.newerPage).toMatchObject({ loading: false });
});

it("loads newer pages until the window meets the newest message", async () => {
  const { hook } = await setup();
  list.mockResolvedValueOnce({ messages: range(80, 119), has_more: true, has_more_after: true });
  await act(async () => { await hook.result.current.paging.openAround(id(100)); });
  list.mockResolvedValueOnce({ messages: range(120, 159), has_more: true, has_more_after: false });
  await act(async () => { await hook.result.current.paging.newerPage?.load(); });
  expect(list).toHaveBeenLastCalledWith("token", "chat-1", { limit: 40, after: id(119) });
  expect(contents(hook.result.current.messages)).toEqual(contents(range(80, 159)));
  expect(hook.result.current.paging.newerPage).toBeNull();
});

it("goes back to the newest page, for a send from a window", async () => {
  const { hook } = await setup();
  list.mockResolvedValueOnce({ messages: range(80, 119), has_more: true, has_more_after: true });
  await act(async () => { await hook.result.current.paging.openAround(id(100)); });
  list.mockResolvedValueOnce({ messages: range(960, 999), has_more: true });
  await act(async () => { await hook.result.current.paging.jumpToLatest(); });
  expect(list).toHaveBeenLastCalledWith("token", "chat-1", { limit: 40 });
  expect(contents(hook.result.current.messages)).toEqual(contents(range(960, 999)));
  expect(hook.result.current.paging.newerPage).toBeNull();
  expect(writeCachedChatMessages).toHaveBeenCalledWith("chat-1", range(960, 999), true);
});

it("prepends older pages above the thread", async () => {
  const { hook } = await setup(range(960, 999));
  list.mockResolvedValueOnce({ messages: range(920, 959), has_more: false });
  await act(async () => { await hook.result.current.paging.loadOlderMessages(); });
  expect(list).toHaveBeenCalledWith("token", "chat-1", { limit: 40, before: id(960) });
  expect(contents(hook.result.current.messages)).toEqual(contents(range(920, 999)));
  expect(hook.result.current.hasMoreOlder).toBe(false);
});

it("drops a window that arrives after the view moved on", async () => {
  const { hook, viewRef } = await setup();
  let resolve!: (page: { messages: Message[]; has_more: boolean; has_more_after: boolean }) => void;
  list.mockReturnValueOnce(new Promise((done) => { resolve = done; }));
  let pending!: Promise<boolean>;
  await act(async () => { pending = hook.result.current.paging.openAround(id(100)); });
  viewRef.current.version += 1;
  await act(async () => { resolve({ messages: range(80, 119), has_more: true, has_more_after: true }); await pending; });
  expect(contents(hook.result.current.messages)).toEqual(contents(range(960, 999)));
  expect(hook.result.current.paging.newerPage).toBeNull();
});

it("says so when the window cannot be read", async () => {
  const { hook, banner } = await setup();
  list.mockRejectedValueOnce(new Error("offline"));
  let shown = true;
  await act(async () => { shown = await hook.result.current.paging.openAround(id(100)); });
  expect(shown).toBe(false);
  expect(banner).toHaveBeenCalledWith("common.error", "alert-circle");
});
