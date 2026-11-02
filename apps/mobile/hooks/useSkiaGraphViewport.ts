/* eslint-disable react-hooks/immutability -- Reanimated shared values mutate `.value` in gestures. */
import { useEffect } from "react";
import { Gesture } from "react-native-gesture-handler";
import { runOnJS, useSharedValue } from "react-native-reanimated";

import {
  clampGraphViewW,
  panGraphViewW,
  unmapPointW,
  zoomGraphViewW,
  type GraphViewW,
} from "@/lib/math/graphWorklets";
import type { GraphView } from "@/lib/math/graphViewport";

const TRACE_HOLD_DELAY_MS = 180;

type Args = {
  width: number;
  height: number;
  pad: number;
  initialView: GraphView;
  /** Called once per gesture end so the JS side can resample for the new window. */
  onCommit: (bounds: GraphView) => void;
};

/**
 * UI-thread viewport for the Skia explorer: bounds live in a shared value and
 * gestures mutate them in worklets, so pan/zoom never round-trips through
 * React state. JS is notified once per gesture end (onCommit) to resample.
 */
export function useSkiaGraphViewport({
  width,
  height,
  pad,
  initialView,
  onCommit,
}: Args) {
  const bounds = useSharedValue<GraphViewW>(initialView);
  const gestureStart = useSharedValue<GraphViewW>(initialView);
  const traceActive = useSharedValue(false);
  /** Finger position in pixels while tracing. */
  const tracePos = useSharedValue({ px: 0, py: 0 });

  useEffect(() => {
    bounds.value = initialView;
    gestureStart.value = initialView;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- shared values are mutable refs; reseed only for a new window
  }, [initialView]);

  const commit = (next: GraphViewW) => {
    "worklet";
    runOnJS(onCommit)(next);
  };

  const pinch = Gesture.Pinch()
    .onBegin(() => {
      "worklet";
      gestureStart.value = bounds.value;
    })
    .onUpdate((e) => {
      "worklet";
      const focal = unmapPointW(e.focalX, e.focalY, gestureStart.value, width, height, pad);
      bounds.value = zoomGraphViewW(gestureStart.value, e.scale, focal.x, focal.y);
    })
    .onEnd(() => {
      "worklet";
      commit(bounds.value);
    });

  const tracePan = Gesture.Pan()
    .activateAfterLongPress(TRACE_HOLD_DELAY_MS)
    .maxPointers(1)
    .onStart((e) => {
      "worklet";
      traceActive.value = true;
      tracePos.value = { px: e.x, py: e.y };
    })
    .onUpdate((e) => {
      "worklet";
      tracePos.value = { px: e.x, py: e.y };
    })
    .onFinalize(() => {
      "worklet";
      traceActive.value = false;
    });

  const pan = Gesture.Pan()
    .minDistance(10)
    .maxPointers(1)
    .onBegin(() => {
      "worklet";
      gestureStart.value = bounds.value;
    })
    .onUpdate((e) => {
      "worklet";
      bounds.value = panGraphViewW(
        gestureStart.value,
        e.translationX,
        e.translationY,
        width,
        height,
        pad,
      );
    })
    .onEnd(() => {
      "worklet";
      commit(bounds.value);
    });

  const doubleTap = Gesture.Tap()
    .numberOfTaps(2)
    .onEnd(() => {
      "worklet";
      bounds.value = clampGraphViewW(initialView);
      commit(bounds.value);
    });

  // Moving first claims a normal pan. Holding first claims trace mode. Race is
  // important here: simultaneous recognition let a slow drag become a trace
  // halfway through, which made the viewport look rigid on a real phone.
  const drag = Gesture.Race(pan, tracePan);
  const gesture = Gesture.Simultaneous(pinch, drag, doubleTap);

  return { bounds, gesture, traceActive, tracePos };
}
