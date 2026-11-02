import { act, renderHook } from "@testing-library/react-native";

import { useLiveTalkMinutes } from "@/features/account/hooks/useLiveTalkMinutes";
import { reportDisconnected, reportReconnected } from "@/lib/reconnectRefresh";

const mockStatus = jest.fn();
let mockFocused = true;
jest.mock("@/contexts/AuthContext", () => ({ useAuthToken: () => "token" }));
jest.mock("@/lib/api", () => ({ api: { liveTalkStatus: (...args: unknown[]) => mockStatus(...args) } }));
jest.mock("expo-router", () => {
  const { useEffect } = jest.requireActual<typeof import("react")>("react");
  return {
    useFocusEffect: (effect: () => void | (() => void)) => {
      const focused = mockFocused;
      useEffect(() => (focused ? effect() : undefined), [effect, focused]);
    },
  };
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

const status = (remaining: number) => ({ entitled: true, remaining, limit: 60 });

/** The API back, then the longest wait. */
const apiBack = () => act(async () => {
  reportReconnected();
  await jest.advanceTimersByTimeAsync(10_000);
});

beforeEach(() => {
  jest.useFakeTimers();
  mockStatus.mockReset();
  mockFocused = true;
});
afterEach(() => jest.useRealTimers());

it("reads the minutes on focus and again once the API answers after an outage", async () => {
  mockStatus.mockRejectedValueOnce(new Error("Network request failed")).mockResolvedValueOnce(status(42));
  const { result } = await renderHook(() => useLiveTalkMinutes(true));
  await act(async () => {});
  expect(result.current).toBeNull();
  await apiBack();
  expect(mockStatus).toHaveBeenCalledTimes(2);
  expect(result.current).toEqual({ remaining: 42, limit: 60 });
});

it("reads nothing for a plan without live talk, and drops a read the screen left", async () => {
  const { result, rerender } = await renderHook(
    ({ enabled }: { enabled: boolean }) => useLiveTalkMinutes(enabled),
    { initialProps: { enabled: false } },
  );
  await apiBack();
  expect(mockStatus).not.toHaveBeenCalled();

  const pending = deferred<ReturnType<typeof status>>();
  mockStatus.mockReturnValueOnce(pending.promise);
  await rerender({ enabled: true });
  mockFocused = false;
  await rerender({ enabled: true });
  await act(async () => { pending.resolve(status(42)); });
  expect(result.current).toBeNull();
  mockFocused = true;
  mockStatus.mockResolvedValueOnce(status(30));
  await rerender({ enabled: true });
  await act(async () => {});
  expect(mockStatus).toHaveBeenCalledTimes(2);
  expect(result.current).toEqual({ remaining: 30, limit: 60 });
});

it("leaves the minutes a read brought since the connection was lost, not one read before it", async () => {
  mockStatus.mockResolvedValue(status(42));
  reportDisconnected();
  jest.advanceTimersByTime(1000);
  await renderHook(() => useLiveTalkMinutes(true));
  await act(async () => {});
  await apiBack();
  expect(mockStatus).toHaveBeenCalledTimes(1);

  jest.advanceTimersByTime(1000);
  reportDisconnected();
  await apiBack();
  expect(mockStatus).toHaveBeenCalledTimes(2);
});
