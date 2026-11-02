import {
  drawerChatFetchMode,
  insertChatIntoGroups,
  shouldWarmClosedDrawerChatList,
} from "@/features/chat/drawer/drawerChatList";
import {
  chatRecencySection,
  patchChatListGroups,
  regroupChatsByRecency,
  removeChatFromGroups,
} from "@/features/chat/model/listSections";
import type { Chat, ChatList } from "@/lib/api";

const empty: ChatList = {
  pinned: [],
  today: [],
  yesterday: [],
  last_7_days: [],
  this_month: [],
  older: [],
  archived: [],
};

function chat(id: string, overrides: Partial<Chat> = {}): Chat {
  return {
    id,
    title: null,
    model: "free-chat",
    pinned: false,
    created_at: "2026-07-01T12:00:00Z",
    updated_at: "2026-07-01T12:00:00Z",
    ...overrides,
  };
}

beforeEach(() => { jest.useFakeTimers().setSystemTime(new Date(2026, 6, 1, 14)); });
afterEach(() => { jest.useRealTimers(); });

describe("drawerChatFetchMode", () => {
  const base = {
    isDrawerOpen: true,
    hasToken: true,
    hasLoadedOnce: false,
  };

  it("skips spinner path while the drawer is closed (idle warm is separate)", () => {
    expect(drawerChatFetchMode({ ...base, isDrawerOpen: false })).toBe("skip");
  });

  it("full-fetches on first open", () => {
    expect(drawerChatFetchMode(base)).toBe("full");
  });

  it("does not refetch GET /chats when the list is already painted", () => {
    expect(drawerChatFetchMode({ ...base, hasLoadedOnce: true })).toBe("skip");
  });

  it("does not idle-warm GET /chats after the drawer already listed chats", () => {
    expect(
      shouldWarmClosedDrawerChatList({
        hasToken: true,
        isDrawerOpen: false,
        hasLoadedOnce: true,
      }),
    ).toBe(false);
    expect(
      shouldWarmClosedDrawerChatList({
        hasToken: true,
        isDrawerOpen: false,
        hasLoadedOnce: false,
      }),
    ).toBe(true);
    expect(
      shouldWarmClosedDrawerChatList({
        hasToken: true,
        isDrawerOpen: true,
        hasLoadedOnce: false,
      }),
    ).toBe(false);
  });

});

describe("insertChatIntoGroups", () => {
  it("adds a new chat to today", () => {
    const next = insertChatIntoGroups(empty, chat("a"));
    expect(next.today.map((c) => c.id)).toEqual(["a"]);
  });

  it("does not duplicate an existing chat", () => {
    const groups: ChatList = { ...empty, today: [chat("a")] };
    const next = insertChatIntoGroups(groups, chat("a", { title: "Renamed" }));
    expect(next).toBe(groups);
    expect(next.today).toHaveLength(1);
  });

  it("adds pinned chats to pinned", () => {
    const next = insertChatIntoGroups(empty, chat("p", { pinned: true }));
    expect(next.pinned.map((c) => c.id)).toEqual(["p"]);
    expect(next.today).toHaveLength(0);
  });

  it("adds archived chats to archived", () => {
    const next = insertChatIntoGroups(empty, chat("z", { archived: true }));
    expect(next.archived.map((c) => c.id)).toEqual(["z"]);
  });
});

describe("archive/unarchive move (remove + reinsert with flipped field)", () => {
  it("moves an active chat into archived", () => {
    const groups: ChatList = { ...empty, today: [chat("a")] };
    const removed = removeChatFromGroups(groups, "a");
    const next = insertChatIntoGroups(removed, { ...chat("a"), archived: true });
    expect(next.today).toHaveLength(0);
    expect(next.archived.map((c) => c.id)).toEqual(["a"]);
  });

  it("moves an archived chat back to today when unarchived", () => {
    const groups: ChatList = { ...empty, archived: [chat("a", { archived: true })] };
    const removed = removeChatFromGroups(groups, "a");
    const next = insertChatIntoGroups(removed, { ...chat("a"), archived: false });
    expect(next.archived).toHaveLength(0);
    expect(next.today.map((c) => c.id)).toEqual(["a"]);
  });

  it("moves an archived pinned chat back to pinned when unarchived", () => {
    const groups: ChatList = {
      ...empty,
      archived: [chat("a", { archived: true, pinned: true })],
    };
    const removed = removeChatFromGroups(groups, "a");
    const next = insertChatIntoGroups(removed, { ...chat("a"), archived: false, pinned: true });
    expect(next.archived).toHaveLength(0);
    expect(next.pinned.map((c) => c.id)).toEqual(["a"]);
  });
});


it("moves a header pin patch into Pinned and restores the activity bucket on unpin", () => {
  const old = chat("old", { updated_at: new Date(2026, 5, 1).toISOString() });
  const groups = { ...empty, older: [old] };
  const pinned = patchChatListGroups(groups, old.id, { pinned: true });
  expect(pinned.older).toEqual([]);
  expect(pinned.pinned[0].id).toBe(old.id);
  const restored = patchChatListGroups(pinned, old.id, { pinned: false });
  expect(restored.today).toEqual([]);
  expect(restored.older[0].id).toBe(old.id);
});

it("archive clears pinned and rollback restores the original pinned row", () => {
  const old = chat("pinned", { pinned: true });
  const archived = patchChatListGroups({ ...empty, pinned: [old] }, old.id, { archived: true });
  expect(archived.pinned).toEqual([]);
  expect(archived.archived[0]).toMatchObject({ archived: true, pinned: false });
  const rollback = patchChatListGroups(archived, old.id, { archived: false, pinned: true });
  expect(rollback.archived).toEqual([]);
  expect(rollback.pinned[0].id).toBe(old.id);
});

it("restores deleted old chats to their date bucket in newest-first order", () => {
  const first = chat("newer", { updated_at: new Date(2026, 5, 10).toISOString() });
  const restored = insertChatIntoGroups({ ...empty, older: [first] }, chat("old", { updated_at: new Date(2026, 5, 1).toISOString() }));
  expect(restored.today).toEqual([]);
  expect(restored.older.map((row) => row.id)).toEqual(["newer", "old"]);
});

it.each([
  [new Date(2026, 6, 1, 0), "today"],
  [new Date(2026, 5, 30, 23), "yesterday"],
  [new Date(2026, 5, 24, 0), "last_7_days"],
  [new Date(2026, 5, 23, 23), "older"],
])("uses calendar-day boundaries across the start of a month", (updated, section) => {
  expect(chatRecencySection(chat("day", { updated_at: updated.toISOString() }))).toBe(section);
});

describe("regroupChatsByRecency", () => {
  // Local `Date` fields: each case holds in whatever zone the tests run in.
  const at = (...parts: [number, number, number, number, number?]) => new Date(...parts).toISOString();
  const ids = (rows: Chat[]) => rows.map((row) => row.id);

  it("moves a list kept from yesterday to today's headings, leaving pinned and archived as they are", () => {
    const pinned = [chat("pinned", { pinned: true })];
    const archived = [chat("archived", { archived: true })];
    const kept: ChatList = {
      ...empty,
      pinned,
      archived,
      today: [chat("yesterday-morning", { updated_at: at(2026, 5, 30, 9) })],
      yesterday: [chat("two-days-ago", { updated_at: at(2026, 5, 29, 20) })],
    };
    const now = regroupChatsByRecency(kept);
    expect(now.today).toEqual([]);
    expect(ids(now.yesterday)).toEqual(["yesterday-morning"]);
    expect(ids(now.last_7_days)).toEqual(["two-days-ago"]);
    expect(now.pinned).toBe(pinned);
    expect(now.archived).toBe(archived);
  });

  it("files a chat from just after local midnight under Today, where a UTC grouping said Yesterday", () => {
    const kept: ChatList = { ...empty, yesterday: [chat("after-midnight", { updated_at: at(2026, 6, 1, 0, 5) })] };
    expect(ids(regroupChatsByRecency(kept).today)).toEqual(["after-midnight"]);
  });

  it("hands back the same list when no chat moves", () => {
    const fresh: ChatList = {
      ...empty,
      today: [chat("now", { updated_at: at(2026, 6, 1, 13) })],
      older: [chat("old", { updated_at: at(2026, 4, 1, 9) })],
    };
    expect(regroupChatsByRecency(fresh)).toBe(fresh);
  });

  it("keeps newest first where chats filed on different days meet", () => {
    // 08:00 yesterday sat under a stale Today; 09:00 yesterday was filed under Yesterday today.
    const mixed: ChatList = {
      ...empty,
      today: [chat("eight", { updated_at: at(2026, 5, 30, 8) })],
      yesterday: [chat("nine", { updated_at: at(2026, 5, 30, 9) })],
    };
    expect(ids(regroupChatsByRecency(mixed).yesterday)).toEqual(["nine", "eight"]);
  });
});
