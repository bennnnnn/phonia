/**
 * The shared play/pause clock behind the physics scene and the trajectory
 * chart: when it starts by itself, when it goes round again, and that a
 * recycled list cell starts over.
 */
import { act, renderHook } from "@testing-library/react-native";
import { withRepeat, withTiming } from "react-native-reanimated";

import { LOOP_LAPS, usePlayback } from "@/components/rich/usePlayback";

jest.mock("react-native-reanimated", () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports -- jest.mock factories cannot import
  const React = require("react");
  const id = (value: unknown) => value;
  return {
    __esModule: true,
    useSharedValue: (value: number) => React.useRef({ value }).current,
    withTiming: jest.fn((to: number) => to),
    withRepeat: jest.fn(id),
    withSequence: jest.fn(id),
    cancelAnimation: jest.fn(),
    runOnJS: (fn: (...args: unknown[]) => void) => fn,
    Easing: {
      linear: id,
      ease: id,
      sin: id,
      inOut: () => id,
      out: () => id,
      in: () => id,
    },
  };
});

const mockSetting = jest.fn<boolean | null, []>(() => false);
jest.mock("@/lib/motion", () => ({
  ...jest.requireActual("@/lib/motion"),
  useReduceMotionSetting: () => mockSetting(),
}));

type Options = Parameters<typeof usePlayback>[0];

const BASE: Options = {
  duration: 4000,
  animated: true,
  autoplay: true,
  loop: false,
  resetKey: "scene-a",
};

beforeEach(() => {
  mockSetting.mockReturnValue(false);
  jest.mocked(withRepeat).mockClear();
  jest.mocked(withTiming).mockClear();
});

describe("usePlayback", () => {
  it("does not start until the Reduce Motion setting is known", async () => {
    mockSetting.mockReturnValue(null);
    const hook = await renderHook((options: Options) => usePlayback(options), {
      initialProps: BASE,
    });
    expect(hook.result.current.isPlaying).toBe(false);
    expect(hook.result.current.progress.value).toBe(0);

    mockSetting.mockReturnValue(false);
    await hook.rerender(BASE);
    expect(hook.result.current.isPlaying).toBe(true);
  });

  it("never starts by itself under Reduce Motion, but plays once when asked", async () => {
    mockSetting.mockReturnValue(true);
    const hook = await renderHook(() => usePlayback({ ...BASE, loop: true }));
    expect(hook.result.current.isPlaying).toBe(false);

    await act(() => hook.result.current.play());
    expect(hook.result.current.isPlaying).toBe(true);
    // A user who asked for one pass gets one pass, even of an orbit.
    expect(withRepeat).not.toHaveBeenCalled();
  });

  it("goes round a few times for periodic motion, then rests on Play", async () => {
    const hook = await renderHook(() => usePlayback({ ...BASE, loop: true }));
    // Never for ever: a looping figure kept drawing while the chat was covered.
    expect(withRepeat).toHaveBeenCalledWith(
      expect.anything(),
      LOOP_LAPS,
      false,
      expect.any(Function),
    );
    expect(hook.result.current.isPlaying).toBe(true);

    const [, , , onDone] = jest.mocked(withRepeat).mock.calls.at(-1)!;
    await act(() => onDone?.(true));
    expect(hook.result.current.isPlaying).toBe(false);
  });

  it("holds the end state otherwise, and shows Play again when it gets there", async () => {
    const hook = await renderHook(() => usePlayback(BASE));
    expect(withRepeat).not.toHaveBeenCalled();
    expect(hook.result.current.isPlaying).toBe(true);

    const [, , onDone] = jest.mocked(withTiming).mock.calls.at(-1)!;
    await act(() => onDone?.(true));
    expect(hook.result.current.isPlaying).toBe(false);
  });

  it("waits for the button when it is not meant to autoplay", async () => {
    const hook = await renderHook(() => usePlayback({ ...BASE, autoplay: false }));
    expect(hook.result.current.isPlaying).toBe(false);
    expect(withTiming).not.toHaveBeenCalled();
  });

  it("rewinds and stops when the content changes", async () => {
    const options = { ...BASE, autoplay: false };
    const hook = await renderHook((props: Options) => usePlayback(props), {
      initialProps: options,
    });
    await act(() => hook.result.current.play());
    expect(hook.result.current.progress.value).toBe(1);

    await hook.rerender({ ...options, resetKey: "scene-b" });
    expect(hook.result.current.isPlaying).toBe(false);
    expect(hook.result.current.progress.value).toBe(0);
  });
});
