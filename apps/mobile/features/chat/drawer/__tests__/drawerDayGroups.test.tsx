/**
 * @jest-environment ./jest.timeZoneEnvironment.js
 */
/**
 * The drawer's headings are today's, in the phone's zone, for a list read earlier too: the
 * disk copy a cold start paints was grouped on the day and in the zone it was read in, and
 * a list held in memory keeps its headings across midnight. The phone files the chats it
 * inserts by the day now, so the two could sit under different headings.
 */
import React from "react";
import { Text } from "react-native";
import { act, render } from "@testing-library/react-native";
import { useDrawerChatList } from "@/features/chat/drawer/useDrawerChatList";
import { api, type Chat, type ChatList } from "@/lib/api";
import { invalidateChatListCache, setChatListCache } from "@/features/chat/model/chatListCache";
import { readStoredChatList } from "@/features/chat/model/chatListFile";
import { CHAT_DATE_SECTIONS, emptyChatList } from "@/features/chat/model/listSections";
import { insertChatGlobal } from "@/features/chat/drawer/drawer";

declare const setTestTimeZone: (zone: string) => void;

jest.mock("@/lib/auth", () => ({
  getSessionGeneration: () => 0,
  requireTokenSession: jest.fn(),
  SessionChangedError: class SessionChangedError extends Error {},
}));
jest.mock("@/lib/api", () => ({ api: { listChats: jest.fn(), listOlderChats: jest.fn() } }));
jest.mock("expo-router", () => ({ useFocusEffect: () => undefined }));
jest.mock("@/features/chat/model/chatListFile", () => ({
  readStoredChatList: jest.fn(async () => null),
  writeStoredChatList: jest.fn(async () => undefined),
  clearStoredChatList: jest.fn(async () => undefined),
}));
const encode = (value: unknown) => btoa(JSON.stringify(value)).replace(/=/g, "");
const mockToken = `${encode({ alg: "HS256" })}.${encode({ sub: "user-1" })}.signature`;
jest.mock("@/contexts/accountSession", () => ({
  useAccountSession: () => ({ account: "account", getToken: () => mockToken }),
}));
jest.mock("@/lib/scheduleIdle", () => ({ scheduleIdleTask: () => jest.fn() }));

/** Holds only `Date`: the hook's promises and effects run as in the app. */
function holdClockAt(iso: string): void {
  jest.useFakeTimers({
    now: new Date(iso),
    doNotFake: [
      "hrtime", "nextTick", "performance", "queueMicrotask", "requestAnimationFrame", "cancelAnimationFrame",
      "requestIdleCallback", "cancelIdleCallback", "setImmediate", "clearImmediate", "setInterval",
      "clearInterval", "setTimeout", "clearTimeout",
    ],
  });
}

function chat(id: string, updatedAt: string): Chat {
  return { id, title: id, model: "free-chat", pinned: false, created_at: updatedAt, updated_at: updatedAt };
}

let current: ReturnType<typeof useDrawerChatList>;
function Probe({ open }: { open: boolean }) {
  const result = useDrawerChatList({ isDrawerOpen: open });
  React.useLayoutEffect(() => { current = result; });
  return <Text>{result.allChats.length}</Text>;
}

/** Each heading the drawer shows, with its chats. */
function headings(): Record<string, string[]> {
  const shown: Record<string, string[]> = {};
  for (const key of CHAT_DATE_SECTIONS) {
    if (current.groups[key].length) shown[key] = current.groups[key].map((row) => row.id);
  }
  return shown;
}

beforeEach(() => {
  jest.clearAllMocks();
  invalidateChatListCache();
  setTestTimeZone("Asia/Kathmandu");
});
afterEach(() => jest.useRealTimers());

it("paints a list kept from before a flight under the headings it has where the phone is now", async () => {
  // 11:45 in Kathmandu. The list on disk was grouped in UTC, where 00:05 today was still yesterday.
  holdClockAt("2026-10-25T06:00:00Z");
  const stored: ChatList = {
    ...emptyChatList(),
    today: [chat("morning", "2026-10-25T05:00:00Z")],
    yesterday: [chat("after-midnight", "2026-10-24T18:20:00Z"), chat("evening-before", "2026-10-24T15:00:00Z")],
  };
  (readStoredChatList as jest.Mock).mockResolvedValueOnce(stored);
  (api.listChats as jest.Mock).mockReturnValueOnce(new Promise(() => {}));
  await render(<Probe open />);
  await act(async () => { await Promise.resolve(); });

  expect(headings()).toEqual({ today: ["morning", "after-midnight"], yesterday: ["evening-before"] });
});

it("moves a list held across midnight to the new day's headings when the drawer opens again", async () => {
  // 23:55 in Kathmandu, a list just read.
  holdClockAt("2026-10-24T18:10:00Z");
  setChatListCache({ ...emptyChatList(), today: [chat("late", "2026-10-24T18:05:00Z")] });
  const view = await render(<Probe open />);
  expect(headings()).toEqual({ today: ["late"] });
  await view.rerender(<Probe open={false} />);

  // 00:15: a new chat is filed under Today; the one from 23:50 is yesterday's now.
  jest.setSystemTime(new Date("2026-10-24T18:30:00Z"));
  await view.rerender(<Probe open />);
  await act(async () => { insertChatGlobal(chat("new", "2026-10-24T18:30:00Z")); });

  expect(headings()).toEqual({ today: ["new"], yesterday: ["late"] });
  expect(api.listChats).not.toHaveBeenCalled();
});
