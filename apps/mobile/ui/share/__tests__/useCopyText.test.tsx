import { act, renderHook } from "@testing-library/react-native";
import { setStringAsync } from "expo-clipboard";

import { useCopyText } from "../useCopyText";

jest.mock("@/lib/haptics", () => ({ notifySuccess: jest.fn() }));

beforeEach(() => {
  jest.useFakeTimers();
  jest.mocked(setStringAsync).mockReset().mockResolvedValue(true);
});
afterEach(() => jest.useRealTimers());

it("copies, shows the check, then clears it", async () => {
  const { result } = await renderHook(() => useCopyText());
  await act(async () => {
    expect(await result.current.copy("hello")).toBe(true);
  });
  expect(setStringAsync).toHaveBeenCalledWith("hello");
  expect(result.current.copied).toBe(true);
  await act(async () => {
    jest.advanceTimersByTime(1500);
  });
  expect(result.current.copied).toBe(false);
});

it("says a refused copy failed instead of throwing", async () => {
  jest.mocked(setStringAsync).mockRejectedValueOnce(new Error("no clipboard"));
  const onFailed = jest.fn();
  const { result } = await renderHook(() => useCopyText(onFailed));
  await act(async () => {
    expect(await result.current.copy("hello")).toBe(false);
  });
  expect(onFailed).toHaveBeenCalledTimes(1);
  expect(result.current.copied).toBe(false);
});

it("copies nothing for blank text", async () => {
  const { result } = await renderHook(() => useCopyText());
  await act(async () => {
    expect(await result.current.copy("   ")).toBe(false);
  });
  expect(setStringAsync).not.toHaveBeenCalled();
});
