import {
  activeChatsFromGroups,
  appendArchivedChats,
  appendOlderChats,
  defaultChatSectionCollapsed,
  drawerSectionTitleKey,
  emptyChatList,
  isCollapsibleChatSection,
  PINNED_CHAT_SECTION,
  removeChatFromGroups,
} from "@/features/chat/model/listSections";

describe("chatListSections", () => {
  it("emptyChatList has all buckets", () => {
    expect(emptyChatList()).toEqual({
      pinned: [],
      today: [],
      yesterday: [],
      last_7_days: [],
      this_month: [],
      older: [],
      archived: [],
    });
  });

  it("activeChatsFromGroups excludes archived", () => {
    const groups = emptyChatList();
    groups.archived.push({
      id: "a",
      title: null,
      model: "free-chat",
      pinned: false,
      archived: true,
      created_at: "",
      updated_at: "",
    });
    groups.today.push({
      id: "t",
      title: null,
      model: "free-chat",
      pinned: false,
      created_at: "",
      updated_at: "",
    });
    expect(activeChatsFromGroups(groups).map((c) => c.id)).toEqual(["t"]);
  });

  it("pinned is not collapsible; only today starts expanded", () => {
    expect(isCollapsibleChatSection(PINNED_CHAT_SECTION)).toBe(false);
    expect(defaultChatSectionCollapsed("today")).toBe(false);
    expect(defaultChatSectionCollapsed("yesterday")).toBe(true);
    expect(defaultChatSectionCollapsed("last_7_days")).toBe(true);
    expect(defaultChatSectionCollapsed("older")).toBe(true);
  });

  it("drawerSectionTitleKey maps to i18n keys", () => {
    expect(drawerSectionTitleKey("last_7_days")).toBe("drawer.last_7_days");
  });
});


describe("older chat pages (CLAR-12)", () => {
  const chat = (id: string) => ({ id, title: id, model: "free-chat", pinned: false, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" });

  it("appends each dated group below what is shown, once, and takes the page's cursor", () => {
    const shown = { ...emptyChatList(), pinned: [chat("p")], older: [chat("a")], next_cursor: "after-a" };
    const page = { ...emptyChatList(), older: [chat("a"), chat("b")], next_cursor: "after-b" };
    const merged = appendOlderChats(shown, page);
    expect(merged.older.map((row) => row.id)).toEqual(["a", "b"]);
    expect(merged.pinned.map((row) => row.id)).toEqual(["p"]);
    expect(merged.next_cursor).toBe("after-b");
  });

  it("keeps the cursor when a chat leaves the list", () => {
    const groups = { ...emptyChatList(), older: [chat("a")], next_cursor: "after-a" };
    expect(removeChatFromGroups(groups, "a").next_cursor).toBe("after-a");
  });

  it("appends a page of archived chats below the ones shown, with the next cursor", () => {
    const shown = { ...emptyChatList(), archived: [chat("a")], archived_next_cursor: "after-a" };
    const merged = appendArchivedChats(shown, { items: [chat("a"), chat("b")], next_cursor: null });
    expect(merged.archived.map((row) => row.id)).toEqual(["a", "b"]);
    expect(merged.archived_next_cursor).toBeNull();
  });
});
