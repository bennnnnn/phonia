import { act, renderHook } from "@testing-library/react-native";

import { useSkiaGraphViewport } from "@/hooks/useSkiaGraphViewport";
import { axisTicksW } from "@/lib/math/graphWorklets";

type Handler = (event?: Record<string, number>) => void;
type HandlerBag = Record<string, Handler>;

const mockHandlers: Record<"pinch" | "pan" | "tracePan" | "doubleTap", HandlerBag> = {
  pinch: {},
  pan: {},
  tracePan: {},
  doubleTap: {},
};

jest.mock("react-native-gesture-handler", () => {
  let panCount = 0;
  const chain = (name: keyof typeof mockHandlers) => {
    const api: Record<string, (value?: unknown) => typeof api> = {};
    for (const method of [
      "minDistance",
      "maxPointers",
      "numberOfTaps",
      "minDuration",
      "activateAfterLongPress",
    ]) {
      api[method] = () => api;
    }
    for (const method of ["onBegin", "onUpdate", "onEnd", "onFinalize", "onStart"]) {
      api[method] = (handler?: unknown) => {
        if (typeof handler === "function") mockHandlers[name][method] = handler as Handler;
        return api;
      };
    }
    return api;
  };
  return {
    Gesture: {
      Pinch: () => chain("pinch"),
      Pan: () => chain(panCount++ % 2 === 0 ? "tracePan" : "pan"),
      Tap: () => chain("doubleTap"),
      Race: (...gestures: unknown[]) => gestures,
      Simultaneous: (...gestures: unknown[]) => gestures,
    },
  };
});

const INITIAL = { xMin: -6, xMax: 6, yMin: -4, yMax: 4 };

describe("useSkiaGraphViewport gestures", () => {
  beforeEach(() => {
    for (const handlers of Object.values(mockHandlers)) {
      for (const key of Object.keys(handlers)) delete handlers[key];
    }
  });

  it("pans in both axes, regenerates visible ticks, and commits once", async () => {
    const onCommit = jest.fn();
    const { result } = await renderHook(() =>
      useSkiaGraphViewport({
        width: 360,
        height: 220,
        pad: 28,
        initialView: INITIAL,
        onCommit,
      }),
    );

    await act(() => {
      mockHandlers.pan.onBegin?.();
      mockHandlers.pan.onUpdate?.({ translationX: 120, translationY: -60, x: 180, y: 110 });
      mockHandlers.pan.onEnd?.();
    });

    const moved = result.current.bounds.value;
    expect(moved.xMin).toBeLessThan(INITIAL.xMin);
    expect(moved.yMin).toBeLessThan(INITIAL.yMin);
    expect(moved.xMax - moved.xMin).toBeCloseTo(12);
    expect(moved.yMax - moved.yMin).toBeCloseTo(8);
    expect(axisTicksW(moved.xMin, moved.xMax)).not.toEqual(axisTicksW(-6, 6));
    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(onCommit).toHaveBeenCalledWith(moved);
  });

  it("pinches around the focal point and commits the smaller viewport", async () => {
    const onCommit = jest.fn();
    const { result } = await renderHook(() =>
      useSkiaGraphViewport({
        width: 360,
        height: 220,
        pad: 28,
        initialView: INITIAL,
        onCommit,
      }),
    );

    await act(() => {
      mockHandlers.pinch.onBegin?.();
      mockHandlers.pinch.onUpdate?.({ scale: 2, focalX: 180, focalY: 110 });
      mockHandlers.pinch.onEnd?.();
    });

    const zoomed = result.current.bounds.value;
    expect(zoomed.xMax - zoomed.xMin).toBeCloseTo(6);
    expect(zoomed.yMax - zoomed.yMin).toBeCloseTo(4);
    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(onCommit).toHaveBeenCalledWith(zoomed);
  });

  it("double-tap restores the initial axes after moving", async () => {
    const onCommit = jest.fn();
    const { result } = await renderHook(() =>
      useSkiaGraphViewport({
        width: 360,
        height: 220,
        pad: 28,
        initialView: INITIAL,
        onCommit,
      }),
    );

    await act(() => {
      mockHandlers.pan.onBegin?.();
      mockHandlers.pan.onUpdate?.({ translationX: 90, translationY: 45, x: 180, y: 110 });
      mockHandlers.pan.onEnd?.();
      mockHandlers.doubleTap.onEnd?.();
    });

    expect(result.current.bounds.value).toEqual(INITIAL);
    expect(onCommit).toHaveBeenLastCalledWith(INITIAL);
  });

  it("turns a brief touch into a movable trace without panning the graph", async () => {
    const onCommit = jest.fn();
    const { result } = await renderHook(() =>
      useSkiaGraphViewport({
        width: 360,
        height: 220,
        pad: 28,
        initialView: INITIAL,
        onCommit,
      }),
    );

    await act(() => {
      mockHandlers.tracePan.onStart?.({ x: 140, y: 90 });
      mockHandlers.tracePan.onUpdate?.({ x: 170, y: 110 });
    });

    expect(result.current.traceActive.value).toBe(true);
    expect(result.current.tracePos.value).toEqual({ px: 170, py: 110 });
    expect(result.current.bounds.value).toEqual(INITIAL);

    await act(() => {
      mockHandlers.tracePan.onFinalize?.();
    });
    expect(result.current.traceActive.value).toBe(false);
    expect(onCommit).not.toHaveBeenCalled();
  });
});
