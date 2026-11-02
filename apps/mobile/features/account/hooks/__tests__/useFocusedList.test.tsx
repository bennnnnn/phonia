import { act, renderHook } from "@testing-library/react-native";

import { useFocusedList } from "@/features/account/hooks/useFocusedList";
import { reportDisconnected, reportReconnected } from "@/lib/reconnectRefresh";

jest.mock("expo-router", () => {
  const { useEffect } = jest.requireActual<typeof import("react")>("react");
  return { useFocusEffect: (effect: () => void | (() => void)) => useEffect(effect, [effect]) };
});

const read = jest.fn(async () => ["row"]);

/** The API back, then the longest wait. */
const apiBack = () => act(async () => {
  reportReconnected();
  await jest.advanceTimersByTimeAsync(10_000);
});

beforeEach(() => {
  jest.useFakeTimers();
  read.mockClear();
});
afterEach(() => jest.useRealTimers());

it("reads again once the API is back after a read before the connection was lost, not after one since", async () => {
  await renderHook(() => useFocusedList("token", read));
  await act(async () => {});
  expect(read).toHaveBeenCalledTimes(1);
  jest.advanceTimersByTime(1000);
  reportDisconnected();
  await apiBack();
  expect(read).toHaveBeenCalledTimes(2);

  // That read landed since the connection was lost the first time; not since the second.
  await apiBack();
  expect(read).toHaveBeenCalledTimes(2);
  jest.advanceTimersByTime(1000);
  reportDisconnected();
  await apiBack();
  expect(read).toHaveBeenCalledTimes(3);
});
