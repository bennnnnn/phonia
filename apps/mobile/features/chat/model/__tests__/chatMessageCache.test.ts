import { emitAppEvent } from "@/lib/appEvents";

jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "/mock-cache/",
  getInfoAsync: jest.fn(),
  makeDirectoryAsync: jest.fn(),
  readAsStringAsync: jest.fn(),
  writeAsStringAsync: jest.fn(),
  deleteAsync: jest.fn(),
  readDirectoryAsync: jest.fn(async () => []),
}));

jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => mockSession }));
let mockSession = 0;
const mockIdle: (() => void)[] = [];
jest.mock("@/lib/scheduleIdle", () => ({
  scheduleIdleTask: (task: () => void) => {
    mockIdle.push(task);
    return () => { mockIdle.splice(mockIdle.indexOf(task), 1); };
  },
}));

import {
  clearAllCachedChatMessages,
  cachedChatPageFetchedAt,
  clearCachedChatMessages,
  isCachedChatPageFresh,
  isSettledThread,
  keepCachedChatPage,
  markCachedChatPageStale,
  markCachedChatPagesStale,
  patchCachedChatMessage,
  peekCachedChatPage,
  readCachedChatMessages,
  sweepCachedChatPages,
  writeCachedChatMessages,
} from "@/features/chat/model/messageCache";
import type { Message } from "@/lib/api";
import {
  deleteAsync,
  getInfoAsync,
  readAsStringAsync,
  readDirectoryAsync,
  writeAsStringAsync,
} from "expo-file-system/legacy";

const messages: Message[] = [
  { id: "m1", role: "user", content: "Hi", model: null, created_at: "2026-01-01T00:00:00Z" },
];

describe("chatMessageCache", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSession = 0;
  });

  it("returns null when cache file is missing", async () => {
    (getInfoAsync as jest.Mock).mockResolvedValue({ exists: false });
    await expect(readCachedChatMessages("chat-1")).resolves.toBeNull();
  });

  it("reads cached messages when present", async () => {
    (getInfoAsync as jest.Mock).mockResolvedValue({ exists: true });
    (readAsStringAsync as jest.Mock).mockResolvedValue(
      JSON.stringify({ messages, has_more: false, cached_at: "2026-01-01T00:00:00Z" }),
    );
    await expect(readCachedChatMessages("chat-1")).resolves.toEqual({
      messages,
      has_more: false,
      cached_at: "2026-01-01T00:00:00Z",
    });
  });

  it("writes cached messages to disk", async () => {
    (getInfoAsync as jest.Mock).mockResolvedValue({ exists: true });
    await writeCachedChatMessages("chat-1", messages, true);
    expect(writeAsStringAsync).toHaveBeenCalledWith(
      "/mock-cache/chat-pages/chat-1.json",
      expect.stringContaining('"has_more":true'),
    );
  });

  it("clears cached messages", async () => {
    await clearCachedChatMessages("chat-1");
    expect(deleteAsync).toHaveBeenCalledWith("/mock-cache/chat-pages/chat-1.json", {
      idempotent: true,
    });
  });

  it("forgets a chat whose photo the gallery deleted (ARCH-10)", async () => {
    emitAppEvent("attachmentDeleted", { attachmentId: "a1", chatId: "chat-1" });
    emitAppEvent("attachmentDeleted", { attachmentId: "a2", chatId: null });
    await clearCachedChatMessages("chat-2");
    expect(deleteAsync).toHaveBeenCalledTimes(2);
    expect(deleteAsync).toHaveBeenNthCalledWith(1, "/mock-cache/chat-pages/chat-1.json", { idempotent: true });
  });

  it("patches one cached message without dropping has_more", async () => {
    (getInfoAsync as jest.Mock).mockResolvedValue({ exists: true });
    (readAsStringAsync as jest.Mock).mockResolvedValue(
      JSON.stringify({
        messages: [
          { id: "m1", role: "assistant", content: "old", model: null, created_at: "2026-01-01T00:00:00Z" },
        ],
        has_more: true,
        cached_at: "2026-01-01T00:00:00.000Z",
      }),
    );
    await patchCachedChatMessage("chat-1", "m1", { content: "new" });
    expect(writeAsStringAsync).toHaveBeenCalledWith(
      "/mock-cache/chat-pages/chat-1.json",
      expect.stringContaining('"content":"new"'),
    );
    expect(writeAsStringAsync).toHaveBeenCalledWith(
      "/mock-cache/chat-pages/chat-1.json",
      expect.stringContaining('"has_more":true'),
    );
  });

  it("parses cached_at for the silent-refetch stale window", () => {
    expect(cachedChatPageFetchedAt({ cached_at: "2026-01-01T00:00:00.000Z" })).toBe(
      Date.parse("2026-01-01T00:00:00.000Z"),
    );
    expect(cachedChatPageFetchedAt({ cached_at: "nope" })).toBeUndefined();
    expect(cachedChatPageFetchedAt(null)).toBeUndefined();
  });
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

describe("saved history invalidation", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSession = 0;
    (getInfoAsync as jest.Mock).mockResolvedValue({ exists: true });
    (writeAsStringAsync as jest.Mock).mockResolvedValue(undefined);
    (deleteAsync as jest.Mock).mockResolvedValue(undefined);
  });

  it.each([false, true])("does not recreate a cleared cache while preparing a write (all: %s)", async (all) => {
    const info = deferred<{ exists: boolean }>();
    (getInfoAsync as jest.Mock).mockReturnValueOnce(info.promise);
    const writing = writeCachedChatMessages("chat-1", messages, false);
    await Promise.resolve();
    const clearing = all ? clearAllCachedChatMessages() : clearCachedChatMessages("chat-1");
    info.resolve({ exists: true });
    await Promise.all([writing, clearing]);
    expect(writeAsStringAsync).not.toHaveBeenCalled();
    expect(deleteAsync).toHaveBeenCalled();
  });

  it("orders deletion after an already-started disk write", async () => {
    const disk = deferred<void>();
    (writeAsStringAsync as jest.Mock).mockReturnValueOnce(disk.promise);
    const writing = writeCachedChatMessages("chat-1", messages, false);
    for (let i = 0; i < 10; i++) await Promise.resolve();
    expect(writeAsStringAsync).toHaveBeenCalled();
    const clearing = clearCachedChatMessages("chat-1");
    await Promise.resolve();
    expect(deleteAsync).not.toHaveBeenCalled();
    disk.resolve();
    await Promise.all([writing, clearing]);
    expect(deleteAsync).toHaveBeenCalled();
  });

  it("discards a read that finishes after the chat cache is cleared", async () => {
    const disk = deferred<string>();
    (readAsStringAsync as jest.Mock).mockReturnValueOnce(disk.promise);
    const reading = readCachedChatMessages("chat-1");
    await Promise.resolve();
    const clearing = clearCachedChatMessages("chat-1");
    disk.resolve(JSON.stringify({ messages, has_more: false, cached_at: "2026-01-01" }));
    await expect(reading).resolves.toBeNull();
    await clearing;
  });

  it("discards writes from a session that ended during file preparation", async () => {
    const info = deferred<{ exists: boolean }>();
    (getInfoAsync as jest.Mock).mockReturnValueOnce(info.promise);
    const writing = writeCachedChatMessages("chat-1", messages, false);
    await Promise.resolve();
    mockSession++;
    info.resolve({ exists: true });
    await writing;
    expect(writeAsStringAsync).not.toHaveBeenCalled();
  });

  it("does not let an older message patch overwrite a newer fetched page", async () => {
    const disk = deferred<string>();
    (readAsStringAsync as jest.Mock).mockReturnValueOnce(disk.promise);
    const patching = patchCachedChatMessage("chat-1", "m1", { content: "Patched" });
    for (let i = 0; i < 10; i++) await Promise.resolve();
    const latest = [...messages, { ...messages[0], id: "m2", content: "Latest saved reply" }];
    const writing = writeCachedChatMessages("chat-1", latest, false);
    disk.resolve(JSON.stringify({ messages, has_more: true, cached_at: "2026-01-01" }));
    await Promise.all([patching, writing]);
    const writes = (writeAsStringAsync as jest.Mock).mock.calls;
    expect(JSON.parse(writes[writes.length - 1][1]).messages).toEqual(latest);
  });

  it("preserves the page fetch time when patching one message", async () => {
    (readAsStringAsync as jest.Mock).mockResolvedValue(JSON.stringify({
      messages, has_more: true, cached_at: "2026-01-01T00:00:00Z",
    }));
    await patchCachedChatMessage("chat-1", "m1", { content: "Updated" });
    expect(JSON.parse((writeAsStringAsync as jest.Mock).mock.calls[0][1])).toEqual({
      messages: [{ ...messages[0], content: "Updated" }], has_more: true,
      cached_at: "2026-01-01T00:00:00Z",
    });
  });
});

const uuid = (n: number) => `0190a000-0000-7000-8000-${String(n).padStart(12, "0")}`;
const row = (id: string, role: Message["role"], extra: Partial<Message> = {}): Message => ({
  id, role, content: id, model: null, created_at: "2026-01-01T00:00:00Z", ...extra,
});
const turn = (n: number): Message[] => [row(uuid(2 * n), "user"), row(uuid(2 * n + 1), "assistant")];
const FETCHED = Date.parse("2026-01-01T00:00:00Z");

describe("kept chat pages", () => {
  let now = FETCHED;
  beforeEach(async () => {
    jest.clearAllMocks();
    mockSession = 0;
    mockIdle.length = 0;
    now = FETCHED;
    jest.spyOn(Date, "now").mockImplementation(() => now);
    (getInfoAsync as jest.Mock).mockResolvedValue({ exists: true });
    (writeAsStringAsync as jest.Mock).mockResolvedValue(undefined);
    await clearAllCachedChatMessages();
  });
  afterEach(() => jest.restoreAllMocks());

  it("keeps the shown thread at once and writes it to the file when idle", async () => {
    keepCachedChatPage("chat-1", turn(1), false, FETCHED);
    expect(peekCachedChatPage("chat-1")).toEqual({
      messages: turn(1), has_more: false, cached_at: "2026-01-01T00:00:00.000Z",
    });
    expect(writeAsStringAsync).not.toHaveBeenCalled();
    mockIdle.splice(0).forEach((task) => task());
    for (let i = 0; i < 10; i++) await Promise.resolve();
    expect((writeAsStringAsync as jest.Mock).mock.calls[0][0]).toBe("/mock-cache/chat-pages/chat-1.json");
    expect(JSON.parse((writeAsStringAsync as jest.Mock).mock.calls[0][1])).toEqual({
      messages: turn(1), has_more: false, cached_at: "2026-01-01T00:00:00.000Z",
    });
  });

  it("drops list keys and a saved row's local preview, but keeps a sent bubble's", () => {
    const sent = row("local-1", "user", { local_image_uri: "file:///photo.jpg", renderKey: "local-1" });
    const reply = row(uuid(2), "assistant", { renderKey: "stream-1" });
    const saved = row(uuid(1), "user", { local_image_uri: "file:///old.jpg" });
    keepCachedChatPage("chat-1", [saved, row(uuid(3), "assistant"), sent, reply], false, FETCHED);
    expect(peekCachedChatPage("chat-1")?.messages).toEqual([
      row(uuid(1), "user"),
      row(uuid(3), "assistant"),
      row("local-1", "user", { local_image_uri: "file:///photo.jpg" }),
      row(uuid(2), "assistant"),
    ]);
  });

  it("keeps the newest page, starting on a saved row so Load earlier has a cursor", () => {
    const thread = Array.from({ length: 21 }, (_, n) => [row(`local-${n}`, "user"), row(uuid(n), "assistant")]).flat();
    keepCachedChatPage("chat-1", thread, false, FETCHED);
    const page = peekCachedChatPage("chat-1");
    expect(page?.has_more).toBe(true);
    expect(page?.messages[0].id).toBe(uuid(0));
    expect(page?.messages).toHaveLength(41);
  });

  it("is fresh for a reopen inside the stale window only", () => {
    keepCachedChatPage("chat-1", turn(1), false, FETCHED, "2026-01-01T00:00:00Z");
    now = FETCHED + 19_000;
    expect(isCachedChatPageFresh("chat-1", "2026-01-01T00:00:00Z")).toBe(true);
    expect(isCachedChatPageFresh("chat-1", "2026-01-01T00:00:05Z")).toBe(false);
    now = FETCHED + 20_000;
    expect(isCachedChatPageFresh("chat-1", "2026-01-01T00:00:00Z")).toBe(false);
  });

  it("is not fresh after the clock is set back", () => {
    keepCachedChatPage("chat-1", turn(1), false, FETCHED, "2026-01-01T00:00:00Z");
    now = FETCHED - 60 * 60_000;
    expect(isCachedChatPageFresh("chat-1", "2026-01-01T00:00:00Z")).toBe(false);
  });

  it("is not fresh once a turn started or the app went to the background", () => {
    keepCachedChatPage("chat-1", turn(1), false, FETCHED);
    keepCachedChatPage("chat-2", turn(2), false, FETCHED);
    markCachedChatPageStale("chat-1");
    expect(isCachedChatPageFresh("chat-1", undefined)).toBe(false);
    expect(isCachedChatPageFresh("chat-2", undefined)).toBe(true);
    markCachedChatPagesStale();
    expect(isCachedChatPageFresh("chat-2", undefined)).toBe(false);
    expect(peekCachedChatPage("chat-2")?.messages).toEqual(turn(2));
  });

  it("stays stale after the background until a read made after it, whatever changes here", () => {
    keepCachedChatPage("chat-1", turn(1), false, FETCHED);
    now = FETCHED + 1_000;
    markCachedChatPagesStale();
    now = FETCHED + 2_000;
    // A thumbs-up on the reply changes the thread, but no read since the background backs it.
    keepCachedChatPage("chat-1", [turn(1)[0], { ...turn(1)[1], feedback: "up" }], false, FETCHED);
    expect(isCachedChatPageFresh("chat-1", undefined)).toBe(false);
    keepCachedChatPage("chat-1", [...turn(1), ...turn(2)], false, FETCHED + 1_500);
    expect(isCachedChatPageFresh("chat-1", undefined)).toBe(true);
  });

  it("never keeps a thread that shows a row twice, and leaves the page stale", () => {
    keepCachedChatPage("chat-1", turn(1), false, FETCHED);
    keepCachedChatPage("chat-1", [...turn(1), ...turn(2), { ...turn(2)[1] }], false, FETCHED);
    expect(peekCachedChatPage("chat-1")?.messages).toEqual(turn(1));
    expect(isCachedChatPageFresh("chat-1", undefined)).toBe(false);
  });

  it("keeps a sent picture's preview in memory but never in the file", async () => {
    const sent = row("local-1", "user", { local_image_uri: "file:///picked.jpg" });
    const file = row("local-2", "user", {
      local_file_uri: "file:///picked.pdf", local_file_name: "notes.pdf", local_file_content_type: "application/pdf",
    });
    keepCachedChatPage("chat-1", [sent, row(uuid(1), "assistant"), file, row(uuid(2), "assistant")], false, FETCHED);
    expect(peekCachedChatPage("chat-1")?.messages[0].local_image_uri).toBe("file:///picked.jpg");
    mockIdle.splice(0).forEach((task) => task());
    for (let i = 0; i < 10; i++) await Promise.resolve();
    const written = JSON.parse((writeAsStringAsync as jest.Mock).mock.calls[0][1]).messages as Message[];
    expect(written[0]).toEqual(row("local-1", "user"));
    expect(written[2]).toEqual(row("local-2", "user", {
      local_file_name: "notes.pdf", local_file_content_type: "application/pdf",
    }));
  });

  it("does not make a page fresher when the same thread is kept again", () => {
    keepCachedChatPage("chat-1", turn(1), false, FETCHED);
    now = FETCHED + 15_000;
    keepCachedChatPage("chat-1", turn(1).map((message) => ({ ...message, renderKey: "x" })), false, FETCHED);
    now = FETCHED + 21_000;
    expect(isCachedChatPageFresh("chat-1", undefined)).toBe(false);
    keepCachedChatPage("chat-1", [...turn(1), ...turn(2)], false, FETCHED);
    expect(isCachedChatPageFresh("chat-1", undefined)).toBe(true);
  });

  it("forgets kept pages when the chat or every chat is cleared, before any write", async () => {
    keepCachedChatPage("chat-1", turn(1), false, FETCHED);
    keepCachedChatPage("chat-2", turn(2), false, FETCHED);
    await clearCachedChatMessages("chat-1");
    expect(peekCachedChatPage("chat-1")).toBeNull();
    expect(peekCachedChatPage("chat-2")).not.toBeNull();
    await clearAllCachedChatMessages();
    mockIdle.splice(0).forEach((task) => task());
    expect(peekCachedChatPage("chat-2")).toBeNull();
    expect(writeAsStringAsync).not.toHaveBeenCalled();
  });

  it("never shows one account's kept page to the next", () => {
    keepCachedChatPage("chat-1", turn(1), false, FETCHED);
    mockSession++;
    expect(peekCachedChatPage("chat-1")).toBeNull();
    expect(isCachedChatPageFresh("chat-1", undefined)).toBe(false);
  });

  it("patches a kept page with a saved edit", async () => {
    keepCachedChatPage("chat-1", turn(1), false, FETCHED);
    await patchCachedChatMessage("chat-1", uuid(3), { content: "Edited" });
    expect(peekCachedChatPage("chat-1")?.messages[1].content).toBe("Edited");
  });
});

describe("isSettledThread", () => {
  it.each([
    ["saved rows", [...turn(1)], true],
    ["a sent message its saved reply confirms", [row("local-1", "user"), row(uuid(1), "assistant")], true],
    ["a reply still streaming", [row("local-1", "user"), row("streaming", "assistant")], false],
    ["a sent message without a reply", [...turn(1), row("local-2", "user")], false],
    ["a stopped reply the server has not confirmed", [row(uuid(1), "user"), row("streamed-1", "assistant")], false],
    ["nothing", [], false],
  ])("%s", (_name, thread, settled) => {
    expect(isSettledThread(thread)).toBe(settled);
  });
});

describe("chat page sweep (LEAK-07)", () => {
  beforeEach(() => jest.clearAllMocks());

  it("keeps the newest 100 chats and none older than 30 days", async () => {
    const now = Date.parse("2026-10-21T00:00:00Z");
    const day = 24 * 60 * 60_000;
    // chat-0 is the newest, then chat-1 and so on; chat-5 was last opened 31 days ago,
    // so the newest 100 are chat-0 to chat-100 without it.
    const names = Array.from({ length: 102 }, (_, index) => `chat-${index}.json`);
    (readDirectoryAsync as jest.Mock).mockResolvedValueOnce(names);
    (getInfoAsync as jest.Mock).mockImplementation(async (path: string) => {
      const index = Number(path.match(/chat-(\d+)\.json$/)?.[1]);
      const age = index === 5 ? 31 * day : index * 60_000;
      return { exists: true, modificationTime: (now - age) / 1000 };
    });
    await sweepCachedChatPages(now);
    const deleted = (deleteAsync as jest.Mock).mock.calls.map(([path]) => path).sort();
    expect(deleted).toEqual([
      "/mock-cache/chat-pages/chat-101.json",
      "/mock-cache/chat-pages/chat-5.json",
    ]);
  });
});
