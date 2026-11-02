import {
  allChatsFromGroups,
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
    });
  });

  it("allChatsFromGroups lists pinned first, then the dated groups", () => {
    const groups = emptyChatList();
    groups.pinned.push({
      id: "p",
      title: null,
      pinned: true,
      created_at: "",
      updated_at: "",
    });
    groups.today.push({
      id: "t",
      title: null,
      pinned: false,
      created_at: "",
      updated_at: "",
    });
    expect(allChatsFromGroups(groups).map((c) => c.id)).toEqual(["p", "t"]);
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
  const chat = (id: string) => ({ id, title: id, pinned: false, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" });

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
});
