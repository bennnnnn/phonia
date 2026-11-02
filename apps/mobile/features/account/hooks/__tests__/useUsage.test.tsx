import { act, renderHook } from "@testing-library/react-native";

import { useUsage } from "@/features/account/hooks/useUsage";
import type { Usage } from "@/lib/api";
import { reportDisconnected, reportReconnected } from "@/lib/reconnectRefresh";

// The account key, and its access token, which the hourly rotation changes.
let mockToken: string | null = "account-a";
let mockAccessToken = "token-1";
let mockGeneration = 0;
const mockFetchUsage = jest.fn();
const mockGetCachedUsage = jest.fn();

// Stable, as the provider keeps it.
const mockGetToken = () => (mockToken ? mockAccessToken : null);
jest.mock("@/contexts/accountSession", () => ({
  useAccountSession: () => ({ account: mockToken, getToken: mockGetToken }),
}));
jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => mockGeneration }));
jest.mock("@/lib/cache/usageCache", () => ({
  fetchTodayUsage: (...args: unknown[]) => mockFetchUsage(...args),
  getCachedUsage: (...args: unknown[]) => mockGetCachedUsage(...args),
  invalidateUsageCache: jest.fn(),
  usageReadAt: () => mockReadAt,
}));
/** When the cache last had the usage from the server. */
let mockReadAt: number | undefined;
jest.mock("expo-router", () => {
  const { useEffect } = jest.requireActual<typeof import("react")>("react");
  return { useFocusEffect: (callback: () => void) => useEffect(callback, [callback]) };
});

function usage(used = 12000): Usage {
  return {
    date: new Date().toISOString().slice(0, 10),
    input_tokens: used,
    output_tokens: 0,
    used_tokens: used,
    daily_limit: 100000,
    remaining: 100000 - used,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

beforeEach(() => {
  jest.clearAllMocks();
  mockFetchUsage.mockReset();
  mockToken = "account-a";
  mockAccessToken = "token-1";
  mockGeneration = 0;
  mockReadAt = undefined;
  mockGetCachedUsage.mockReturnValue(undefined);
});

it("moves from indeterminate loading to retryable failure and then loaded data", async () => {
  const pending = deferred<Usage | null>();
  mockFetchUsage.mockReturnValueOnce(pending.promise);
  const { result } = await renderHook(useUsage);
  expect(result.current.usage).toBeNull();
  expect(result.current.loading).toBe(true);
  await act(async () => { pending.resolve(null); });
  expect(result.current.loading).toBe(false);
  expect(result.current.error).toBe(true);
  mockFetchUsage.mockResolvedValueOnce(usage());
  await act(async () => { await result.current.refresh({ force: true }); });
  expect(mockFetchUsage).toHaveBeenLastCalledWith("account-a", "token-1", { force: true });
  expect(result.current.usage?.used_tokens).toBe(12000);
  expect(result.current.error).toBe(false);
});

it("immediately hides the previous account's usage and ignores its late response", async () => {
  const accountA = deferred<Usage | null>();
  const accountB = deferred<Usage | null>();
  mockGetCachedUsage.mockImplementation((account: string) => account === "account-a" ? usage(1000) : undefined);
  mockFetchUsage.mockReturnValueOnce(accountA.promise).mockReturnValueOnce(accountB.promise);
  const { result, rerender } = await renderHook(useUsage);
  expect(result.current.usage?.used_tokens).toBe(1000);
  mockToken = "account-b";
  mockGeneration += 1;
  await rerender(undefined);
  expect(result.current.usage).toBeNull();
  await act(async () => { accountA.resolve(usage(2000)); });
  expect(result.current.usage).toBeNull();
  await act(async () => { accountB.resolve(usage(3000)); });
  expect(result.current.usage?.used_tokens).toBe(3000);
});

it("does not fetch from a retained retry callback after leaving the screen", async () => {
  mockFetchUsage.mockResolvedValueOnce(usage());
  const { result, unmount } = await renderHook(useUsage);
  const retry = result.current.refresh;
  await unmount();
  await act(async () => { await retry({ force: true }); });
  expect(mockFetchUsage).toHaveBeenCalledTimes(1);
});

it("does not present yesterday's cached usage as today's limit", async () => {
  const pending = deferred<Usage | null>();
  mockGetCachedUsage.mockReturnValue({ ...usage(), date: "2000-01-01" });
  mockFetchUsage.mockReturnValueOnce(pending.promise);
  const { result } = await renderHook(useUsage);
  expect(result.current.usage).toBeNull();
  expect(mockFetchUsage).toHaveBeenCalledWith("account-a", "token-1", { force: true });
  await act(async () => { pending.resolve(usage()); });
  expect(result.current.usage?.used_tokens).toBe(12000);
});

it("reads nothing again when the access token rotates (NET-11)", async () => {
  mockFetchUsage.mockResolvedValue(usage());
  const { rerender } = await renderHook(useUsage);
  expect(mockFetchUsage).toHaveBeenCalledTimes(1);
  mockAccessToken = "token-2";
  await rerender(undefined);
  expect(mockFetchUsage).toHaveBeenCalledTimes(1);
});

it("shows the usage the server just sent for its day when the phone's clock is past UTC midnight", async () => {
  // The phone runs a minute ahead: 00:00:30 UTC on its clock, still the 24th on the server's.
  jest.useFakeTimers({ now: new Date("2026-10-25T00:00:30.000Z") });
  try {
    mockFetchUsage.mockResolvedValue({ ...usage(), date: "2026-10-24" });
    const { result } = await renderHook(useUsage);
    await act(async () => {});
    expect(result.current.error).toBe(false);
    expect(result.current.usage?.used_tokens).toBe(12000);
  } finally {
    jest.useRealTimers();
  }
});

it("reads again once the API answers after an outage, 0 to 10 s later, and not after leaving", async () => {
  jest.useFakeTimers();
  try {
    mockFetchUsage.mockResolvedValue(usage());
    const { unmount } = await renderHook(useUsage);
    expect(mockFetchUsage).toHaveBeenCalledTimes(1);
    await act(async () => {
      reportReconnected();
      await jest.advanceTimersByTimeAsync(10_000);
    });
    expect(mockFetchUsage).toHaveBeenCalledTimes(2);
    await unmount();
    await act(async () => {
      reportReconnected();
      await jest.advanceTimersByTimeAsync(10_000);
    });
    expect(mockFetchUsage).toHaveBeenCalledTimes(2);
  } finally {
    jest.useRealTimers();
  }
});

it("leaves the usage a read brought since the connection was lost, not one read before it", async () => {
  jest.useFakeTimers();
  try {
    mockFetchUsage.mockResolvedValue(usage());
    await renderHook(useUsage);
    mockReadAt = Date.now();
    jest.advanceTimersByTime(1000);
    const apiBack = () => act(async () => {
      reportReconnected();
      await jest.advanceTimersByTimeAsync(10_000);
    });
    reportDisconnected();
    await apiBack();
    expect(mockFetchUsage).toHaveBeenCalledTimes(2);

    reportDisconnected();
    jest.advanceTimersByTime(1000);
    mockReadAt = Date.now();
    await apiBack();
    expect(mockFetchUsage).toHaveBeenCalledTimes(2);
  } finally {
    jest.useRealTimers();
  }
});
