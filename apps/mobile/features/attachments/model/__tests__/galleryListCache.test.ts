import { getSessionGeneration } from "@/lib/auth";
import { emitAppEvent } from "@/lib/appEvents";
import { api } from "@/lib/api";
import {
  fetchGalleryPage,
  fetchGalleryNextPage,
  getCachedGalleryPage,
  invalidateGalleryCache,
  isGalleryPageFresh,
  prefetchGallery,
  removeCachedGalleryItem,
  setGalleryPage,
} from "@/features/attachments/model/galleryListCache";
jest.mock("@/lib/auth", () => ({
  getSessionGeneration: jest.fn(() => 0),
  requireTokenSession: jest.fn(),
  SessionChangedError: class SessionChangedError extends Error {},
}));
beforeEach(() => { (getSessionGeneration as jest.Mock).mockReturnValue(0); });

jest.mock("@/lib/api", () => ({
  api: {
    listAttachments: jest.fn(),
  },
}));

const listAttachments = api.listAttachments as jest.Mock;

const sample = {
  items: [
    {
      id: "a",
      content_type: "image/png",
      size_bytes: 12,
      download_url: "/attachments/a/file",
      source: "upload" as const,
      created_at: "2026-01-01T00:00:00.000Z",
    },
  ],
  hasMore: false,
};

describe("galleryListCache", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    invalidateGalleryCache();
  });

  it.each([
    ["chats are deleted", () => emitAppEvent("chatsDeleted", { chatIds: ["chat-1"] })],
    ["a picture is saved into a chat", () => emitAppEvent("attachmentAdded", { chatId: "chat-1" })],
  ])("reads again when %s elsewhere (ARCH-10)", (_, announce) => {
    setGalleryPage("all", "", sample);
    announce();
    expect(isGalleryPageFresh("all", "")).toBe(false);
  });

  it("returns a fresh page without refetching", async () => {
    setGalleryPage("all", "", sample);
    expect(isGalleryPageFresh("all", "")).toBe(true);
    expect(getCachedGalleryPage("all", "")).toEqual(sample);

    const result = await fetchGalleryPage("token", "all", "");
    expect(result).toEqual({ data: sample, error: null });
    expect(listAttachments).not.toHaveBeenCalled();
  });

  it("strips an id from every cached tab", () => {
    setGalleryPage("all", "", {
      items: [sample.items[0]!, { ...sample.items[0]!, id: "b" }],
      hasMore: false,
    });
    setGalleryPage("files", "", { items: [sample.items[0]!], hasMore: false });
    removeCachedGalleryItem("a");
    expect(getCachedGalleryPage("all", "")?.items.map((row) => row.id)).toEqual(["b"]);
    expect(getCachedGalleryPage("files", "")?.items).toEqual([]);
  });

  it("prefetch skips when All is already fresh", () => {
    setGalleryPage("all", "", sample);
    prefetchGallery("token");
    expect(listAttachments).not.toHaveBeenCalled();
  });
});


it("does not repopulate an invalidated cache from an earlier request", async () => {
  invalidateGalleryCache();
  let finish!: (value: unknown) => void;
  listAttachments.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
  const loading = fetchGalleryPage("token", "all", "");
  invalidateGalleryCache();
  finish({ items: sample.items, next_cursor: null });
  await loading;
  expect(getCachedGalleryPage("all", "")).toBeUndefined();
});

it("does not let an earlier next page replace a refreshed first page", async () => {
  setGalleryPage("all", "", { ...sample, hasMore: true }, "after-a");
  let finish!: (value: unknown) => void;
  listAttachments.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
  const more = fetchGalleryNextPage("token", "all", "");
  listAttachments.mockResolvedValueOnce({ items: [{ ...sample.items[0], id: "fresh" }], next_cursor: null });
  await fetchGalleryPage("token", "all", "", { force: true });
  finish({ items: [{ ...sample.items[0], id: "older" }], next_cursor: null });
  await more;
  expect(getCachedGalleryPage("all", "")?.items.map((row) => row.id)).toEqual(["fresh"]);
});

it("does not restore a deleted item when an earlier next page completes", async () => {
  setGalleryPage("all", "", { ...sample, hasMore: true }, "after-a");
  let finish!: (value: unknown) => void;
  listAttachments.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
  const more = fetchGalleryNextPage("token", "all", "");
  removeCachedGalleryItem("a");
  listAttachments.mockResolvedValueOnce({ items: [{ ...sample.items[0], id: "b" }], next_cursor: null });
  finish({ items: [{ ...sample.items[0], id: "b" }], next_cursor: null });
  await more;
  expect(getCachedGalleryPage("all", "")?.items.map((row) => row.id)).toEqual(["b"]);
});

it("never exposes a previous account's cached Library page", () => {
  setGalleryPage("all", "", sample);
  (getSessionGeneration as jest.Mock).mockReturnValue(1);
  expect(getCachedGalleryPage("all", "")).toBeUndefined();
});

it("reads each next page from the cursor the server named", async () => {
  invalidateGalleryCache();
  listAttachments.mockReset();
  const row = (id: string) => ({ ...sample.items[0]!, id });
  setGalleryPage("all", "", { items: [row("a")], hasMore: true }, "after-a");
  listAttachments.mockResolvedValueOnce({ items: [row("b")], next_cursor: "after-b" });
  await fetchGalleryNextPage("token", "all", "");
  listAttachments.mockResolvedValueOnce({ items: [row("c")], next_cursor: null });
  await fetchGalleryNextPage("token", "all", "");
  expect(listAttachments.mock.calls.map((call) => call[1].cursor)).toEqual(["after-a", "after-b"]);
  expect(getCachedGalleryPage("all", "")).toEqual({ items: [row("a"), row("b"), row("c")], hasMore: false });
});

it("keeps reading from the same row when a loaded file is deleted meanwhile (CLAR-12)", async () => {
  invalidateGalleryCache();
  listAttachments.mockReset();
  const row = (id: string) => ({ ...sample.items[0]!, id });
  setGalleryPage("all", "", { items: [row("a")], hasMore: true }, "after-a");
  let finish!: (value: unknown) => void;
  listAttachments.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
  const more = fetchGalleryNextPage("token", "all", "");
  removeCachedGalleryItem("a");
  // An offset would now start past b; the cursor still names a, so b is read.
  finish({ items: [row("b"), row("c")], next_cursor: null });
  expect((await more).data?.items.map((item) => item.id)).toEqual(["b", "c"]);
  expect(listAttachments).toHaveBeenCalledTimes(1);
  expect(listAttachments.mock.calls[0][1].cursor).toBe("after-a");
});

it("stops when the server's cursor does not move", async () => {
  invalidateGalleryCache();
  listAttachments.mockReset();
  setGalleryPage("all", "", { ...sample, hasMore: true }, "after-a");
  listAttachments.mockResolvedValueOnce({ items: sample.items, next_cursor: "after-a" });
  expect((await fetchGalleryNextPage("token", "all", "")).data?.hasMore).toBe(false);
});

it("keeps at most twenty searches, dropping the least recently used", () => {
  invalidateGalleryCache();
  for (let i = 0; i < 25; i++) setGalleryPage("all", `query ${i}`, sample);
  expect(getCachedGalleryPage("all", "query 0")).toBeUndefined();
  expect(getCachedGalleryPage("all", "query 5")).toEqual(sample);
  expect(getCachedGalleryPage("all", "query 24")).toEqual(sample);
});
