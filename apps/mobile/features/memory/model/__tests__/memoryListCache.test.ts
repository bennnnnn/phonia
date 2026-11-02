import { api, type Memory } from "@/lib/api";
import { requireTokenSession } from "@/lib/auth";
import { emitAppEvent } from "@/lib/appEvents";
import {
  fetchMemories,
  getCachedMemories,
  invalidateMemoriesCache,
  memoriesReadAt,
  prefetchMemories,
  setMemoriesCache,
  subscribeMemoriesCache,
} from "@/features/memory/model/memoryListCache";

jest.mock("@/lib/api", () => ({
  api: {
    listMemories: jest.fn(),
  },
}));

let mockSession = 0;
jest.mock("@/lib/auth", () => ({
  getSessionGeneration: () => mockSession,
  requireTokenSession: jest.fn(),
  SessionChangedError: class SessionChangedError extends Error {},
}));

const ok = <T>(data: T) => ({ data, error: null });
const failed = <T>(data: T | null = null) => ({ data, error: expect.any(Error) });

const listMemories = api.listMemories as jest.Mock;

const sample: Memory[] = [
  {
    id: "m1",
    type: "profile",
    text: "Name is Bini.",
    confidence: 0.9,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
];

function deferred() {
  let resolve!: (value: typeof sample) => void;
  const promise = new Promise<typeof sample>((finish) => { resolve = finish; });
  return { promise, resolve };
}

describe("memoryListCache", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.mocked(requireTokenSession).mockReset();
    mockSession = 0;
    invalidateMemoriesCache();
  });

  it("reads fresh when memory changes from a chat's settings card (ARCH-10)", () => {
    setMemoriesCache(sample);
    emitAppEvent("memoryChanged", {});
    expect(memoriesReadAt()).toBeUndefined();
  });

  it("returns cached memories without refetching when fresh", async () => {
    setMemoriesCache(sample);
    expect(getCachedMemories()).toEqual(sample);

    const result = await fetchMemories("token");
    expect(result).toEqual(ok(sample));
    expect(listMemories).not.toHaveBeenCalled();
  });

  it("dedupes concurrent fetches", async () => {
    let resolveFetch!: (value: typeof sample) => void;
    listMemories.mockReturnValue(
      new Promise((resolve) => {
        resolveFetch = resolve;
      }),
    );

    const first = fetchMemories("token", { force: true });
    const second = fetchMemories("token", { force: true });
    resolveFetch(sample);

    const [a, b] = await Promise.all([first, second]);
    expect(a).toEqual(ok(sample));
    expect(b).toEqual(ok(sample));
    expect(listMemories).toHaveBeenCalledTimes(1);
  });

  it("prefetch skips when cache is already fresh", () => {
    setMemoriesCache(sample);
    prefetchMemories("token");
    expect(listMemories).not.toHaveBeenCalled();
  });

  it("shares a pending prefetch across token refresh within the same session", async () => {
    const read = deferred();
    listMemories.mockReturnValueOnce(read.promise);
    prefetchMemories("token");
    const load = fetchMemories("refreshed-token", { force: true });
    read.resolve(sample);
    expect(await load).toEqual(ok(sample));
    expect(listMemories).toHaveBeenCalledTimes(1);
    expect(await fetchMemories("refreshed-token")).toEqual(ok(sample));
    expect(listMemories).toHaveBeenCalledTimes(1);
  });

  it("clears cached memories immediately when the account session changes", () => {
    setMemoriesCache(sample);
    mockSession++;
    expect(getCachedMemories()).toBeUndefined();
    expect(memoriesReadAt()).toBeUndefined();
  });

  it("rejects an old account token before returning a fresh cache or prefetching", async () => {
    setMemoriesCache(sample);
    jest.mocked(requireTokenSession).mockImplementation(() => { throw new Error("old account"); });
    expect(await fetchMemories("old-token")).toEqual(failed());
    prefetchMemories("old-token");
    expect(listMemories).not.toHaveBeenCalled();
    expect(getCachedMemories()).toEqual(sample);
    jest.mocked(requireTokenSession).mockReset();
  });

  it.each(["invalidation", "account change"])("discards an old read after %s without disturbing the new request", async (reason) => {
    const oldRead = deferred();
    const newRead = deferred();
    listMemories.mockReturnValueOnce(oldRead.promise).mockReturnValueOnce(newRead.promise);
    const oldLoad = fetchMemories("token");
    if (reason === "account change") mockSession++;
    else invalidateMemoriesCache();
    const newLoad = fetchMemories("new-token");
    oldRead.resolve(sample);
    expect(await oldLoad).toEqual(failed());
    expect(getCachedMemories()).toBeUndefined();
    const joinedLoad = fetchMemories("new-token", { force: true });
    const incoming = [{ ...sample[0], id: "new-account" }];
    newRead.resolve(incoming);
    expect(await newLoad).toEqual(ok(incoming));
    expect(await joinedLoad).toEqual(ok(incoming));
    expect(getCachedMemories()).toEqual(incoming);
    expect(listMemories).toHaveBeenCalledTimes(2);
  });

  it("ignores a list written for an old account", () => {
    const session = mockSession;
    mockSession++;
    const current = [{ ...sample[0], id: "current-account" }];
    setMemoriesCache(current);
    setMemoriesCache(sample, session);
    expect(getCachedMemories()).toEqual(current);
  });

  it("retries a failed read and counts only a finished one as read", async () => {
    listMemories.mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(sample);
    expect(await fetchMemories("token")).toEqual(failed());
    expect(memoriesReadAt()).toBeUndefined();
    expect(await fetchMemories("token")).toEqual(ok(sample));
    expect(memoriesReadAt()).toEqual(expect.any(Number));
    expect(listMemories).toHaveBeenCalledTimes(2);
  });

  it("notifies subscribers after cache mutations and stops after unsubscribe", () => {
    const snapshots: (Memory[] | undefined)[] = [];
    const unsubscribe = subscribeMemoriesCache(() => { snapshots.push(getCachedMemories()); });
    try {
      setMemoriesCache(sample);
      // Clear all memory (useClearAllMemories).
      setMemoriesCache([]);
      invalidateMemoriesCache();
      expect(snapshots).toEqual([sample, [], undefined]);
    } finally {
      unsubscribe();
    }
    setMemoriesCache(sample);
    expect(snapshots).toHaveLength(3);
  });

  it("notifies for a committed fetch but not an invalidated response", async () => {
    const changed = jest.fn();
    const unsubscribe = subscribeMemoriesCache(changed);
    try {
      const read = deferred();
      listMemories.mockReturnValueOnce(read.promise).mockResolvedValueOnce(sample);
      const oldLoad = fetchMemories("token");
      invalidateMemoriesCache();
      expect(changed).toHaveBeenCalledTimes(1);
      read.resolve(sample);
      expect(await oldLoad).toEqual(failed());
      expect(changed).toHaveBeenCalledTimes(1);
      expect(await fetchMemories("token")).toEqual(ok(sample));
      expect(changed).toHaveBeenCalledTimes(2);
    } finally {
      unsubscribe();
    }
  });

  it("does not notify while lazily clearing an account's cache during a read", () => {
    setMemoriesCache(sample);
    const changed = jest.fn();
    const unsubscribe = subscribeMemoriesCache(changed);
    try {
      const oldSession = mockSession++;
      expect(getCachedMemories()).toBeUndefined();
      setMemoriesCache(sample, oldSession);
      expect(changed).not.toHaveBeenCalled();
    } finally {
      unsubscribe();
    }
  });
});

describe("memory mutation recovery", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.mocked(requireTokenSession).mockReset();
    mockSession++;
    invalidateMemoriesCache();
  });

  it("starts an authoritative read after a pending read", async () => {
    setMemoriesCache(sample);
    const read = deferred();
    listMemories.mockReturnValueOnce(read.promise).mockResolvedValueOnce([]);
    const oldLoad = fetchMemories("token", { force: true });
    const recovery = fetchMemories("token", { force: true, afterPending: true });
    expect(listMemories).toHaveBeenCalledTimes(1);
    read.resolve(sample);
    expect(await oldLoad).toEqual(ok(sample));
    expect(await recovery).toEqual(ok([]));
    expect(getCachedMemories()).toEqual([]);
    expect(listMemories).toHaveBeenCalledTimes(2);
  });

  it.each(["account change", "invalidation"])("abandons recovery after %s while waiting", async (reason) => {
    const read = deferred();
    listMemories.mockReturnValueOnce(read.promise);
    const oldLoad = fetchMemories("old-token", { force: true });
    const recovery = fetchMemories("old-token", { force: true, afterPending: true });
    if (reason === "account change") mockSession++;
    else invalidateMemoriesCache();
    const current = [{ ...sample[0], id: "current" }];
    setMemoriesCache(current);
    read.resolve(sample);
    expect(await oldLoad).toEqual(failed());
    expect(await recovery).toEqual(failed());
    expect(getCachedMemories()).toEqual(current);
    expect(listMemories).toHaveBeenCalledTimes(1);
  });
});
