/**
 * One contract for every session-fenced list cache on the phone: the drawer's
 * chats, the memory list, the memory pages and the Library pages. Each row of
 * the table drives one cache through its public functions, so a cache that
 * drifts from the shared protocol fails here by name.
 */
import { api, type Chat, type ChatList, type Memory } from "@/lib/api";
import type { AttachmentListItem } from "@/features/attachments/types";
import type { MemoryDocument } from "@/features/memory/types";
import {
  fetchChatList,
  getCachedChatList,
  invalidateChatListCache,
  setChatListCache,
  updateChatListCache,
} from "@/features/chat/model/chatListCache";
import {
  fetchMemories,
  getCachedMemories,
  invalidateMemoriesCache,
  setMemoriesCache,
  subscribeMemoriesCache,
  updateMemoriesCache,
} from "@/features/memory/model/memoryListCache";
import {
  fetchMemoryDocuments,
  getCachedMemoryDocuments,
  invalidateMemoryDocuments,
  setMemoryDocuments,
  subscribeMemoryDocuments,
  updateMemoryDocuments,
} from "@/features/memory/model/memoryDocumentsCache";
import {
  fetchGalleryPage,
  getCachedGalleryPage,
  invalidateGalleryCache,
  removeCachedGalleryItem,
  setGalleryPage,
} from "@/features/attachments/model/galleryListCache";
import {
  isExpectedReadFailure,
  SessionResourceCache,
  type ResourceResult,
} from "@/lib/cache/sessionResource";

jest.mock("@/lib/api", () => ({
  api: {
    listChats: jest.fn(),
    listMemories: jest.fn(),
    listMemoryDocuments: jest.fn(),
    listAttachments: jest.fn(),
  },
}));

let mockSession = 0;
jest.mock("@/lib/auth", () => ({
  getSessionGeneration: () => mockSession,
  requireTokenSession: jest.fn(),
  SessionChangedError: class SessionChangedError extends Error {
    name = "SessionChangedError";
  },
}));

const chat = (id: string): Chat => ({
  id,
  title: id,
  model: "free-chat",
  pinned: false,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
});
const chatList = (ids: string[]): ChatList => ({
  pinned: [],
  today: ids.map(chat),
  yesterday: [],
  last_7_days: [],
  this_month: [],
  older: [],
  archived: [],
});
const memory = (id: string): Memory => ({
  id,
  type: "fact",
  text: id,
  confidence: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
});
const page = (id: string): MemoryDocument => ({
  key: id,
  group: "topics",
  title: id,
  summary: "",
  updated_at: null,
  facts: [memory(`${id}-fact`)],
});
const file = (id: string): AttachmentListItem => ({
  id,
  content_type: "image/png",
  size_bytes: 1,
  download_url: `/attachments/${id}/file`,
  source: "upload",
  created_at: "2026-01-01T00:00:00Z",
});

/** One cache, seen through the functions its screens call. */
type CacheUnderTest = {
  name: string;
  read: jest.Mock;
  /** What the server sends for a list holding these rows. */
  response: (ids: string[]) => unknown;
  /** A completed read of these rows, already in the cache. */
  seed: (ids: string[]) => void;
  fetch: (force?: boolean) => Promise<ResourceResult<unknown>>;
  ids: (data: unknown) => string[];
  cachedIds: () => string[] | undefined;
  /** A local edit (a delete), as the screens make it. */
  remove: (id: string) => void;
  invalidate: () => void;
  subscribe?: (listener: () => void) => () => void;
};

const caches: CacheUnderTest[] = [
  {
    name: "drawer chats",
    read: api.listChats as jest.Mock,
    response: chatList,
    seed: (ids) => setChatListCache(chatList(ids)),
    fetch: (force) => fetchChatList("token", { force }),
    ids: (data) => (data as ChatList).today.map((row) => row.id),
    cachedIds: () => getCachedChatList()?.today.map((row) => row.id),
    remove: (id) => {
      updateChatListCache((groups) => ({
        ...groups,
        today: groups.today.filter((row) => row.id !== id),
      }));
    },
    invalidate: invalidateChatListCache,
  },
  {
    name: "memory list",
    read: api.listMemories as jest.Mock,
    response: (ids) => ids.map(memory),
    seed: (ids) => setMemoriesCache(ids.map(memory)),
    fetch: (force) => fetchMemories("token", { force }),
    ids: (data) => (data as Memory[]).map((row) => row.id),
    cachedIds: () => getCachedMemories()?.map((row) => row.id),
    remove: (id) => {
      updateMemoriesCache((rows) => rows.filter((row) => row.id !== id));
    },
    invalidate: invalidateMemoriesCache,
    subscribe: subscribeMemoriesCache,
  },
  {
    name: "memory pages",
    read: api.listMemoryDocuments as jest.Mock,
    response: (ids) => ({ scanning: false, documents: ids.map(page) }),
    seed: (ids) => setMemoryDocuments({ scanning: false, documents: ids.map(page) }, mockSession),
    fetch: () => fetchMemoryDocuments("token"),
    ids: (data) => (data as { documents: MemoryDocument[] }).documents.map((row) => row.key),
    cachedIds: () => getCachedMemoryDocuments()?.documents.map((row) => row.key),
    remove: (id) => {
      updateMemoryDocuments((rows) => rows.filter((row) => row.key !== id), mockSession);
    },
    invalidate: invalidateMemoryDocuments,
    subscribe: subscribeMemoryDocuments,
  },
  {
    name: "Library pages",
    read: api.listAttachments as jest.Mock,
    response: (ids) => ({ items: ids.map(file), next_cursor: null }),
    seed: (ids) => setGalleryPage("all", "", { items: ids.map(file), hasMore: false }),
    fetch: (force) => fetchGalleryPage("token", "all", "", { force }),
    ids: (data) => (data as { items: AttachmentListItem[] }).items.map((row) => row.id),
    cachedIds: () => getCachedGalleryPage("all", "")?.items.map((row) => row.id),
    remove: removeCachedGalleryItem,
    invalidate: invalidateGalleryCache,
  },
];

function deferred() {
  let resolve!: (value: unknown) => void;
  const promise = new Promise<unknown>((done) => { resolve = done; });
  return { promise, resolve };
}

beforeEach(() => {
  jest.clearAllMocks();
  mockSession += 1;
  caches.forEach((cache) => cache.invalidate());
});

describe.each(caches)("$name cache", (cache) => {
  it.each([
    ["sign-out", () => { mockSession += 1; }],
    ["invalidation", () => cache.invalidate()],
  ])("never lands a read started before %s", async (_reason, end) => {
    const server = deferred();
    cache.read.mockReturnValueOnce(server.promise);
    const read = cache.fetch();
    end();
    server.resolve(cache.response(["old-account"]));

    expect(await read).toEqual({ data: null, error: expect.any(Error) });
    expect(cache.cachedIds()).toBeUndefined();
  });

  it("makes one request for two concurrent reads", async () => {
    const server = deferred();
    cache.read.mockReturnValueOnce(server.promise);
    const first = cache.fetch(true);
    const second = cache.fetch(true);
    server.resolve(cache.response(["a"]));
    const [a, b] = await Promise.all([first, second]);

    expect(cache.read).toHaveBeenCalledTimes(1);
    expect(a.error).toBeNull();
    expect(b.error).toBeNull();
    expect(cache.ids(a.data)).toEqual(["a"]);
    expect(cache.ids(b.data)).toEqual(["a"]);
  });

  it("keeps an edit made while a read runs", async () => {
    cache.seed(["a"]);
    const server = deferred();
    cache.read.mockReturnValueOnce(server.promise);
    const read = cache.fetch(true);
    cache.remove("a");
    server.resolve(cache.response(["a", "b"]));
    const result = await read;

    expect(result.error).toBeNull();
    expect(cache.ids(result.data)).toEqual(["b"]);
    expect(cache.cachedIds()).toEqual(["b"]);
  });

  it("says a first read failed instead of returning a bare null", async () => {
    const failure = new Error("Request failed: 500");
    cache.read.mockRejectedValueOnce(failure);

    expect(await cache.fetch(true)).toEqual({ data: null, error: failure });
    expect(cache.cachedIds()).toBeUndefined();
  });

  it("keeps the previous rows with the error when a refresh fails", async () => {
    cache.seed(["a"]);
    const failure = new TypeError("Network request failed");
    cache.read.mockRejectedValueOnce(failure);
    const result = await cache.fetch(true);

    expect(result.error).toBe(failure);
    expect(cache.ids(result.data)).toEqual(["a"]);
    expect(cache.cachedIds()).toEqual(["a"]);
  });
});

describe.each(caches.filter((cache) => cache.subscribe))("$name subscribers", (cache) => {
  it("hear a finished read and a local edit, and stop after unsubscribing", async () => {
    const changed = jest.fn();
    const unsubscribe = cache.subscribe!(changed);
    cache.read.mockResolvedValueOnce(cache.response(["a", "b"]));
    await cache.fetch(true);
    expect(changed).toHaveBeenCalledTimes(1);
    cache.remove("a");
    expect(changed).toHaveBeenCalledTimes(2);
    unsubscribe();
    cache.remove("b");
    expect(changed).toHaveBeenCalledTimes(2);
  });

  it("are not told about a read that lands after sign-out", async () => {
    const changed = jest.fn();
    const unsubscribe = cache.subscribe!(changed);
    const server = deferred();
    cache.read.mockReturnValueOnce(server.promise);
    const read = cache.fetch();
    mockSession += 1;
    server.resolve(cache.response(["a"]));
    await read;
    expect(changed).not.toHaveBeenCalled();
    unsubscribe();
  });
});

describe("failure reports", () => {
  const httpError = (status: number) =>
    Object.assign(new Error(`Request failed: ${status}`), { name: "ApiRequestError", status });

  it.each([
    ["offline", new TypeError("Network request failed"), true],
    ["timeout", Object.assign(new Error("Aborted"), { name: "AbortError" }), true],
    ["refresh timeout", new Error("Could not reach the Recall server. Check your connection and try again."), true],
    ["sign-out", Object.assign(new Error("Your sign-in changed."), { name: "SessionChangedError" }), true],
    ["expired sign-in", httpError(401), true],
    ["server error", httpError(500), false],
    ["unreadable reply", new SyntaxError("Unexpected token <"), false],
    ["bug", new TypeError("Cannot read properties of undefined"), false],
  ])("treat %s as expected: %s", (_name, error, expected) => {
    expect(isExpectedReadFailure(error)).toBe(expected);
  });

  function cacheWithRows() {
    const cache = new SessionResourceCache<string, string[]>({ staleMs: 1_000, sessionState: () => undefined });
    cache.set("rows", ["a"]);
    return cache;
  }

  it("reports an unexpected failure once while older rows stay on screen", async () => {
    const cache = cacheWithRows();
    const report = jest.fn();
    const failure = httpError(500);
    const load = jest.fn().mockRejectedValue(failure);

    expect(await cache.fetch("rows", "token", load, { force: true, report })).toEqual({
      data: ["a"],
      error: failure,
    });
    await cache.fetch("rows", "token", load, { force: true, report });
    expect(report).toHaveBeenCalledTimes(1);
    expect(report).toHaveBeenCalledWith(failure);

    load.mockResolvedValueOnce(["b"]).mockRejectedValueOnce(failure);
    await cache.fetch("rows", "token", load, { force: true, report });
    await cache.fetch("rows", "token", load, { force: true, report });
    expect(report).toHaveBeenCalledTimes(2);
  });

  it("never reports a network failure", async () => {
    const cache = cacheWithRows();
    const report = jest.fn();
    const load = jest.fn().mockRejectedValue(new TypeError("Network request failed"));
    await cache.fetch("rows", "token", load, { force: true, report });
    expect(report).not.toHaveBeenCalled();
  });

  it("leaves a failure with nothing cached to the screen's error state", async () => {
    const cache = new SessionResourceCache<string, string[]>({ staleMs: 1_000, sessionState: () => undefined });
    const report = jest.fn();
    const result = await cache.fetch("rows", "token", () => Promise.reject(httpError(500)), { report });
    expect(result.data).toBeNull();
    expect(report).not.toHaveBeenCalled();
  });

  it("reports through a later caller that joined a background read", async () => {
    const cache = cacheWithRows();
    const report = jest.fn();
    const server = deferred();
    const load = () => server.promise.then(() => Promise.reject(httpError(500)));
    const background = cache.fetch("rows", "token", load, { force: true });
    const shown = cache.fetch("rows", "token", load, { force: true, report });
    server.resolve(undefined);
    await Promise.all([background, shown]);
    expect(report).toHaveBeenCalledTimes(1);
  });
});

describe("a value restored from disk", () => {
  const rowsCache = () => new SessionResourceCache<string, string[]>({ staleMs: 1_000, sessionState: () => undefined });

  it("is shown at once but never counts as fresh or as read", () => {
    const cache = rowsCache();
    expect(cache.seed("rows", ["disk"], mockSession)).toBe(true);
    expect(cache.get("rows")).toEqual(["disk"]);
    expect(cache.isFresh("rows")).toBe(false);
    expect(cache.fetchedAt("rows")).toBeUndefined();
  });

  it("never replaces a value already read or edited, or lands in another session", () => {
    const read = rowsCache();
    read.set("rows", ["server"]);
    expect(read.seed("rows", ["disk"], mockSession)).toBe(false);
    expect(read.get("rows")).toEqual(["server"]);
    const edited = new SessionResourceCache<string, string[]>({
      staleMs: 1_000, empty: () => [], sessionState: () => undefined,
    });
    edited.update("rows", (rows) => [...rows, "local"]);
    expect(edited.seed("rows", ["disk"], mockSession)).toBe(false);
    expect(rowsCache().seed("rows", ["disk"], mockSession + 1)).toBe(false);
  });

  it("gives way to a read that was already running, with the edits made meanwhile", async () => {
    const cache = new SessionResourceCache<string, string[]>({
      staleMs: 1_000, empty: () => [], sessionState: () => undefined,
    });
    let finish!: (rows: string[]) => void;
    const reading = cache.fetch("rows", "token", () => new Promise<string[]>((done) => { finish = done; }));
    cache.seed("rows", ["disk"], mockSession);
    cache.update("rows", (rows) => [...rows, "local"]);
    expect(cache.get("rows")).toEqual(["disk", "local"]);
    finish(["server"]);
    await reading;
    expect(cache.get("rows")).toEqual(["server", "local"]);
    expect(cache.isFresh("rows")).toBe(true);
  });
});
