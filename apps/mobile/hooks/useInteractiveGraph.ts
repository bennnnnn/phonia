import { useCallback, useMemo, useRef, useState } from "react";
import { Gesture } from "react-native-gesture-handler";
import { runOnJS } from "react-native-reanimated";

import {
  displayGraphExpr,
  formatSeriesExpr,
  parseGraphRelation,
  sampleGraphExpr,
  type GraphCmp,
} from "@/lib/math/graphExpr";
import { defaultInteractiveBounds, type GraphView } from "@/lib/math/graphViewport";
import {
  clampGraphViewW,
  panGraphViewW,
  unmapPointW,
  zoomGraphViewW,
} from "@/lib/math/graphWorklets";

const MAX_GRAPH_SERIES = 4;
const SCATTER_MAX_POINTS = 20;

type SampledCurve = {
  points: [number, number][];
  segments?: [number, number][][];
  cmp?: GraphCmp;
};

export type GraphSeriesState = {
  id: string;
  expr: string;
  visible: boolean;
  /** Original verified function — cannot be removed. */
  locked: boolean;
  seedExpr?: string;
  fallback?: SampledCurve;
};

export type DrawnSeries = GraphSeriesState & {
  color: string;
  points: [number, number][];
  segments?: [number, number][][];
  invalid: boolean;
  cmp: GraphCmp;
};

function sampleInView(
  expr: string,
  variable: string,
  bounds: GraphView,
  samples = 160,
): SampledCurve | null {
  const rel = parseGraphRelation(expr, variable);
  if (!rel) return null;
  const padX = (bounds.xMax - bounds.xMin) * 0.02;
  const sampled = sampleGraphExpr(rel.node, bounds.xMin - padX, bounds.xMax + padX, samples);
  return { ...sampled, cmp: rel.cmp };
}

export function seedGraphSeries(
  exprs: string[],
  fallbacks: (SampledCurve | undefined)[] = [],
): GraphSeriesState[] {
  const out: GraphSeriesState[] = [];
  for (let i = 0; i < exprs.length && i < MAX_GRAPH_SERIES; i += 1) {
    const raw = exprs[i]?.trim() ?? "";
    if (!raw && i > 0) continue;
    out.push({
      id: String(i),
      expr: formatSeriesExpr(raw),
      visible: true,
      // Every server-seeded curve is part of the verified answer. Only rows
      // created later through "Add function" are disposable overlays.
      locked: true,
      seedExpr: formatSeriesExpr(raw),
      fallback: fallbacks[i],
    });
  }
  if (out.length === 0) {
    out.push({ id: "0", expr: "", visible: true, locked: true });
  }
  return out;
}

export function drawGraphSeries(
  series: GraphSeriesState,
  color: string,
  variable: string,
  bounds: GraphView,
  samples = 160,
): DrawnSeries {
  const sampled = series.expr.trim() ? sampleInView(series.expr, variable, bounds, samples) : null;
  const dirty =
    series.seedExpr != null &&
    displayGraphExpr(series.expr) !== displayGraphExpr(series.seedExpr);
  const fallback = series.fallback;
  // Sparse samples keep server points; relations (ellipse) cannot eval as y=f(x).
  const useFallback =
    fallback != null &&
    !dirty &&
    (fallback.points.length <= SCATTER_MAX_POINTS || sampled == null);
  const points = useFallback ? fallback.points : (sampled?.points ?? []);
  const segments = useFallback ? fallback.segments : sampled?.segments;
  const cmp = sampled?.cmp ?? "=";
  const invalid =
    series.expr.trim().length > 0 &&
    !useFallback &&
    !(sampled != null && sampled.points.length > 0);
  return { ...series, color, points, segments, invalid, cmp };
}

export function useGraphSeries(
  seedExprs: string[],
  seedFallbacks: (SampledCurve | undefined)[] = [],
) {
  const [series, setSeries] = useState(() => seedGraphSeries(seedExprs, seedFallbacks));
  const nextId = useRef(series.length);

  const setExpr = useCallback((id: string, expr: string) => {
    setSeries((prev) => prev.map((row) => (row.id === id ? { ...row, expr } : row)));
  }, []);

  const toggleVisible = useCallback((id: string) => {
    setSeries((prev) =>
      prev.map((row) => (row.id === id ? { ...row, visible: !row.visible } : row)),
    );
  }, []);

  const removeSeries = useCallback((id: string) => {
    setSeries((prev) => prev.filter((row) => row.id !== id || row.locked));
  }, []);

  const addSeries = useCallback(() => {
    setSeries((prev) => {
      if (prev.length >= MAX_GRAPH_SERIES) return prev;
      const id = String(nextId.current);
      nextId.current += 1;
      return [...prev, { id, expr: "", visible: true, locked: false }];
    });
  }, []);

  return {
    series,
    canAdd: series.length < MAX_GRAPH_SERIES,
    setExpr,
    toggleVisible,
    removeSeries,
    addSeries,
  };
}

type ViewportArgs = {
  width: number;
  height: number;
  pad: number;
  initialView?: GraphView;
};

export function useGraphViewport({ width, height, pad, initialView: requestedInitialView }: ViewportArgs) {
  const plotAspect = (width - pad * 2) / (height - pad * 2 || 1);
  const initialView = useMemo(
    () => clampGraphViewW(requestedInitialView ?? defaultInteractiveBounds(plotAspect)),
    [plotAspect, requestedInitialView],
  );
  const [bounds, setBounds] = useState<GraphView>(initialView);
  const boundsRef = useRef(bounds);
  boundsRef.current = bounds;
  const startRef = useRef(bounds);

  const captureStart = useCallback(() => {
    startRef.current = boundsRef.current;
  }, []);

  const applyPinch = useCallback(
    (scale: number, focalX: number, focalY: number) => {
      const start = startRef.current;
      const focal = unmapPointW(focalX, focalY, start, width, height, pad);
      setBounds(zoomGraphViewW(start, scale, focal.x, focal.y));
    },
    [height, pad, width],
  );

  const applyPan = useCallback(
    (dx: number, dy: number) => {
      setBounds(panGraphViewW(startRef.current, dx, dy, width, height, pad));
    },
    [height, pad, width],
  );

  const resetView = useCallback(() => setBounds(initialView), [initialView]);

  /** Skia explorer commit: one JS resample per gesture end, not per frame. */
  const commitBounds = useCallback((next: GraphView) => {
    setBounds(clampGraphViewW(next));
  }, []);

  const gesture = useMemo(() => {
    // Pinch must not sit behind Exclusive(doubleTap, …) — that waits for a
    // second tap timeout and the in-chat FlashList never receives the pinch.
    const pinch = Gesture.Pinch()
      .onBegin(() => {
        runOnJS(captureStart)();
      })
      .onUpdate((e) => {
        runOnJS(applyPinch)(e.scale, e.focalX, e.focalY);
      });
    const pan = Gesture.Pan()
      .minDistance(10)
      .maxPointers(1)
      .onBegin(() => {
        runOnJS(captureStart)();
      })
      .onUpdate((e) => {
        runOnJS(applyPan)(e.translationX, e.translationY);
      });
    const doubleTap = Gesture.Tap()
      .numberOfTaps(2)
      .onEnd(() => {
        runOnJS(resetView)();
      });
    return Gesture.Simultaneous(pinch, pan, doubleTap);
  }, [applyPan, applyPinch, captureStart, resetView]);

  return { bounds, gesture, resetView, commitBounds };
}
