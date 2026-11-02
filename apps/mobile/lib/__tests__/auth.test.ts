const mockGetItem = jest.fn();
const mockSetItem = jest.fn();
const mockDeleteItem = jest.fn();

jest.mock("expo-secure-store", () => ({
  getItemAsync: (...args: unknown[]) => mockGetItem(...args),
  setItemAsync: (...args: unknown[]) => mockSetItem(...args),
  deleteItemAsync: (...args: unknown[]) => mockDeleteItem(...args),
}));

jest.mock("@/lib/onboarding", () => ({}));

let auth: typeof import("@/lib/auth");
let storage: Map<string, string>;

beforeEach(async () => {
  jest.resetModules();
  storage = new Map();
  mockGetItem.mockReset().mockImplementation(async (key: string) => storage.get(key) ?? null);
  mockSetItem.mockReset().mockImplementation(async (key: string, value: string) => {
    storage.set(key, value);
  });
  mockDeleteItem.mockReset().mockImplementation(async (key: string) => { storage.delete(key); });
  auth = await import("@/lib/auth");
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => { resolve = res; });
  return { promise, resolve };
}

it("persists both credentials as one secure record and restores them after reload", async () => {
  await auth.setTokenPair("access-a", "refresh-a");
  expect(mockSetItem).toHaveBeenCalledTimes(1);
  jest.resetModules();
  auth = await import("@/lib/auth");
  await expect(auth.getToken()).resolves.toBe("access-a");
  await expect(auth.getRefreshToken()).resolves.toBe("refresh-a");
});

it("rejects storage failures instead of claiming a memory-only sign-in succeeded", async () => {
  mockSetItem.mockRejectedValue(new Error("Keychain unavailable"));
  await expect(auth.setTokenPair("access-a", "refresh-a")).rejects.toThrow(/secure/i);
  await expect(auth.getToken()).resolves.toBeNull();
  await expect(auth.getRefreshToken()).resolves.toBeNull();
});

it("preserves the complete previous pair when a replacement write fails", async () => {
  await auth.setTokenPair("access-a", "refresh-a");
  mockSetItem.mockRejectedValueOnce(new Error("Keychain unavailable"));
  await expect(auth.setTokenPair("access-b", "refresh-b")).rejects.toThrow();
  await expect(auth.getToken()).resolves.toBe("access-a");
  await expect(auth.getRefreshToken()).resolves.toBe("refresh-a");
});

it("reports read failures instead of returning a stale memory credential", async () => {
  await auth.setTokenPair("access-a", "refresh-a");
  mockGetItem.mockRejectedValue(new Error("Keychain locked"));
  await expect(auth.getToken()).rejects.toThrow(/secure/i);
  await expect(auth.getRefreshToken()).rejects.toThrow(/secure/i);
});

it("reads only the one session record (no pre-launch build kept two, DEAD-07)", async () => {
  storage.set("recall_access_token", "never-shipped");
  await expect(auth.getToken()).resolves.toBeNull();
  expect(mockSetItem).not.toHaveBeenCalled();
});

it("serializes logout behind an in-progress write so credentials cannot survive it", async () => {
  const write = deferred<void>();
  mockSetItem.mockImplementationOnce(async (key: string, value: string) => {
    await write.promise;
    storage.set(key, value);
  });
  const save = auth.setTokenPair("access-a", "refresh-a");
  await Promise.resolve();
  const logout = auth.clearToken();
  write.resolve();
  await Promise.all([save, logout]);
  await expect(auth.getToken()).resolves.toBeNull();
  await expect(auth.getRefreshToken()).resolves.toBeNull();
  jest.resetModules();
  auth = await import("@/lib/auth");
  await expect(auth.getToken()).resolves.toBeNull();
});

it("deletes the session record when signing out cannot overwrite it", async () => {
  await auth.setTokenPair("access-a", "refresh-a");
  mockSetItem.mockRejectedValueOnce(new Error("Keychain full"));
  await auth.clearToken();
  expect(mockDeleteItem).toHaveBeenCalledWith("recall_session_v1");
  jest.resetModules();
  auth = await import("@/lib/auth");
  await expect(auth.getToken()).resolves.toBeNull();
});

it("does not write refresh credentials belonging to an invalidated session", async () => {
  await auth.setTokenPair("access-a", "refresh-a");
  const generation = auth.getSessionGeneration();
  await auth.clearToken();
  await expect(auth.setTokenPair("late-access", "late-refresh", generation)).resolves.toBe(false);
  await expect(auth.getToken()).resolves.toBeNull();
});

it("captures the old refresh for remote logout before queued local removal", async () => {
  await auth.setTokenPair("access-a", "refresh-a");
  const refresh = auth.getRefreshToken();
  const cleared = auth.clearToken();
  await expect(refresh).resolves.toBe("refresh-a");
  await cleared;
  await expect(auth.getRefreshToken()).resolves.toBeNull();
});

it("reports an invalid secure record instead of reimporting old credentials", async () => {
  await auth.setTokenPair("access-a", "refresh-a");
  const canonicalKey = mockSetItem.mock.calls[0][0] as string;
  storage.set(canonicalKey, "{truncated");
  storage.set("recall_access_token", "legacy-access");
  await expect(auth.getToken()).rejects.toThrow(/secure/i);
});

it("removes a stale native write even when the replacement login never saves", async () => {
  const write = deferred<void>();
  const started = deferred<void>();
  mockSetItem.mockImplementationOnce(async (key: string, value: string) => {
    started.resolve();
    await write.promise;
    storage.set(key, value);
  });
  const pending = auth.setTokenPair("old-access", "old-refresh");
  await started.promise;
  auth.invalidateSession();
  write.resolve();
  await expect(pending).resolves.toBe(false);
  jest.resetModules();
  auth = await import("@/lib/auth");
  await expect(auth.getToken()).resolves.toBeNull();
});

it("rejects prior-account tokens but permits earlier tokens in the current session", async () => {
  await auth.setTokenPair("access-a", "refresh-a");
  await auth.setTokenPair("access-a2", "refresh-a2");
  expect(() => auth.requireTokenSession("access-a")).not.toThrow();
  expect(() => auth.requireTokenSession("access-a2")).not.toThrow();
  auth.invalidateSession();
  await auth.setTokenPair("access-b", "refresh-b");
  expect(() => auth.requireTokenSession("access-a")).toThrow(auth.SessionChangedError);
  expect(() => auth.requireTokenSession("access-b")).not.toThrow();
});

describe("a record that is there but is no session", () => {
  it.each([
    ["cut short", "{truncated"],
    ["not a pair", '{"accessToken":5,"refreshToken":"refresh-a"}'],
    ["an empty token", '{"accessToken":"","refreshToken":"refresh-a"}'],
    ["a bare string", '"access-a"'],
  ])("is reported as corrupt when %s", async (_case, record) => {
    storage.set("recall_session_v1", record);
    await expect(auth.getToken()).rejects.toBeInstanceOf(auth.CorruptSessionError);
    await expect(auth.getRefreshToken()).rejects.toBeInstanceOf(auth.CorruptSessionError);
  });

  it("is not confused with a keychain that cannot be read now", async () => {
    await auth.setTokenPair("access-a", "refresh-a");
    mockGetItem.mockRejectedValue(new Error("User interaction is not allowed"));
    const read = auth.getToken();
    await expect(read).rejects.toThrow(/secure/i);
    await expect(read).rejects.not.toBeInstanceOf(auth.CorruptSessionError);
  });

  it("is gone after sign-out clears it", async () => {
    storage.set("recall_session_v1", "{truncated");
    await auth.clearToken();
    await expect(auth.getToken()).resolves.toBeNull();
  });
});
