import {
  archiveBulkTargets,
  bulkInParts,
  chatsFromSelection,
  clearChatSelection,
  selectAllChatIds,
  selectableChats,
  toggleChatSelection,
} from "@/features/chat/drawer/drawerChatSelection";
import { emptyChatList } from "@/features/chat/drawer/drawerChatList";
import type { Chat } from "@/lib/api";

function chat(id: string, patch: Partial<Chat> = {}): Chat {
  return {
    id,
    title: null,
    model: "free-chat",
    pinned: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...patch,
  };
}

describe("drawerChatSelection", () => {
  it("toggles ids in a set copy", () => {
    expect([...toggleChatSelection(new Set(["a"]), "a")]).toEqual([]);
    expect([...toggleChatSelection(new Set(), "b")]).toEqual(["b"]);
  });

  it("selects all chat ids and clears", () => {
    expect([...selectAllChatIds([chat("a"), chat("b")])]).toEqual(["a", "b"]);
    expect(clearChatSelection().size).toBe(0);
  });

  it("resolves selected chats from groups", () => {
    const groups = {
      ...emptyChatList(),
      today: [chat("a"), chat("b")],
      archived: [chat("z", { archived: true })],
    };
    const selected = new Set(["a", "z"]);
    expect(chatsFromSelection(groups, selected).map((c) => c.id)).toEqual(["a", "z"]);
  });

  it("filters archive targets to non-archived chats", () => {
    const targets = archiveBulkTargets([
      chat("a"),
      chat("b", { archived: true }),
    ]);
    expect(targets.map((c) => c.id)).toEqual(["a"]);
  });
});

describe("select all and bulk parts", () => {
  it("selects the chats on screen: pinned and dated, not collapsed, never archived", () => {
    const groups = {
      ...emptyChatList(),
      pinned: [chat("p", { pinned: true })],
      today: [chat("t")],
      older: [chat("o")],
      archived: [chat("a", { archived: true })],
    };
    const ids = selectableChats(groups, (key) => key === "older").map((row) => row.id);
    expect(ids).toEqual(["p", "t"]);
  });

  it("sends at most 200 ids per request, and a failed part changes none of its ids", async () => {
    const ids = Array.from({ length: 401 }, (_, index) => `c${index}`);
    const sizes: number[] = [];
    const changed = await bulkInParts(ids, async (part) => {
      sizes.push(part.length);
      if (part[0] === "c200") throw new Error("offline");
      return { changed: part };
    });
    expect(sizes).toEqual([200, 200, 1]);
    expect(changed.has("c0") && changed.has("c400")).toBe(true);
    expect(changed.has("c200") || changed.has("c399")).toBe(false);
  });
});
