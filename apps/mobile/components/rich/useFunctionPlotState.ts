/**
 * The state behind a function plot card and its explorer: the series being
 * edited, the hole markers, the card's plot size and view, and the
 * explorer's plot size, view and samples. `InteractiveFunctionPlot` draws it.
 */
import { useCallback, useId, useMemo, useRef, useState } from "react";
import { useWindowDimensions, type LayoutChangeEvent, type ScrollView } from "react-native";
import { useSafeAreaInsets, type EdgeInsets } from "react-native-safe-area-context";

import { GRAPH_AXIS_PAD, type GraphHoleMarker } from "@/components/rich/GraphCanvas";
import { MODAL_PLOT_MIN } from "@/components/rich/ExplorerModal";
import {
  drawGraphSeries,
  useGraphSeries,
  useGraphViewport,
  type GraphSeriesState,
} from "@/hooks/useInteractiveGraph";
import { useSkiaGraphViewport } from "@/hooks/useSkiaGraphViewport";
import { interactiveFunctionBounds } from "@/lib/math/graphFit";
import { type GraphSpec } from "@/lib/math/graphSpec";
import { expandGraphView } from "@/lib/math/graphViewport";
import { isSkiaAvailable } from "@/lib/skiaAvailability";
import { Space } from "@/lib/space";
import type { Theme } from "@/lib/theme";

export const CHART_HEIGHT = 220;
export const GRAPH_CARD_INSET = Space.sm;
/** Skia explorer samples a 3x window at 3x density for mid-gesture runway. */
const SKIA_SAMPLE_EXPAND = 3;
const SKIA_SAMPLES = 480;

/** What both plots draw: the series, their colours and the plotted variable. */
type Curves = { series: GraphSeriesState[]; palette: readonly string[]; variable: string };

function hasCurve2(spec: GraphSpec): boolean {
  return spec.type === "function" && !!spec.expr2 && !!spec.points2?.length;
}

/** Open points on a seeded curve, while it is shown and still the server's expression. */
function useHoleMarkers(spec: GraphSpec, { series, palette }: Curves): GraphHoleMarker[] {
  return useMemo<GraphHoleMarker[]>(() => {
    if (spec.type !== "function") return [];
    const markers: GraphHoleMarker[] = [];
    const append = (
      row: (typeof series)[number] | undefined,
      points: [number, number][] | undefined,
      color: string,
    ) => {
      if (!row?.visible || row.seedExpr !== row.expr) return;
      for (const point of points ?? []) markers.push({ point, color });
    };
    append(series[0], spec.holes, palette[0]);
    append(series[1], spec.holes2, palette[1 % palette.length]);
    return markers;
  }, [palette, series, spec]);
}

/** The card's plot: its laid-out width, its view and the curves sampled for it. */
function useCardPlot(spec: GraphSpec, chartWidth: number, { series, palette, variable }: Curves) {
  const [plotWidth, setPlotWidth] = useState(
    Math.max(1, chartWidth - GRAPH_CARD_INSET * 2),
  );
  const cardWidth = Math.max(1, plotWidth);
  const cardAspect = (cardWidth - GRAPH_AXIS_PAD * 2) / (CHART_HEIGHT - GRAPH_AXIS_PAD * 2 || 1);
  const cardBounds = useMemo(
    () => interactiveFunctionBounds(spec, cardAspect),
    [cardAspect, spec],
  );
  const ignoreCardCommit = useCallback(() => {}, []);
  const cardSkiaViewport = useSkiaGraphViewport({
    width: cardWidth,
    height: CHART_HEIGHT,
    pad: GRAPH_AXIS_PAD,
    initialView: cardBounds,
    onCommit: ignoreCardCommit,
  });
  const cardDrawn = useMemo(
    () => series.map((row, i) => drawGraphSeries(row, palette[i % palette.length], variable, cardBounds)),
    [cardBounds, palette, series, variable],
  );
  const onCardLayout = (e: LayoutChangeEvent) => {
    const w = Math.round(e.nativeEvent.layout.width - GRAPH_CARD_INSET * 2);
    if (w > 0 && w !== plotWidth) setPlotWidth(w);
  };
  return { width: cardWidth, bounds: cardBounds, drawn: cardDrawn, skiaViewport: cardSkiaViewport, onLayout: onCardLayout };
}

/** The explorer's plot: its laid-out size, its pinch-and-pan view and the curves sampled for it. */
function useExplorerPlot(
  spec: GraphSpec,
  insets: EdgeInsets,
  skiaExplorer: boolean,
  { series, palette, variable }: Curves,
) {
  const { width: screenW, height: screenH } = useWindowDimensions();
  const modalWidth = Math.max(1, screenW - insets.left - insets.right);
  const fallbackModalH = Math.max(MODAL_PLOT_MIN, screenH - insets.top - insets.bottom - 200);
  const [modalPlot, setModalPlot] = useState({ width: modalWidth, height: fallbackModalH });
  const modalAspect =
    (modalPlot.width - GRAPH_AXIS_PAD * 2) / (modalPlot.height - GRAPH_AXIS_PAD * 2 || 1);
  const modalInitialView = useMemo(
    () => interactiveFunctionBounds(spec, modalAspect),
    [modalAspect, spec],
  );
  const viewport = useGraphViewport({
    width: modalPlot.width,
    height: modalPlot.height,
    pad: GRAPH_AXIS_PAD,
    initialView: modalInitialView,
  });
  const onModalPlotLayout = (e: LayoutChangeEvent) => {
    const { width, height } = e.nativeEvent.layout;
    const w = Math.round(width);
    const h = Math.round(height);
    if (w > 0 && h > 0 && (w !== modalPlot.width || h !== modalPlot.height)) {
      setModalPlot({ width: w, height: h });
    }
  };
  // The Skia explorer pans/zooms on the UI thread against samples taken over
  // an expanded window; viewport.bounds only moves on gesture-end commits.
  const sampleBounds = useMemo(
    () => (skiaExplorer ? expandGraphView(viewport.bounds, SKIA_SAMPLE_EXPAND) : viewport.bounds),
    [skiaExplorer, viewport.bounds],
  );
  const modalDrawn = useMemo(
    () =>
      series.map((row, i) =>
        drawGraphSeries(
          row,
          palette[i % palette.length],
          variable,
          sampleBounds,
          skiaExplorer ? SKIA_SAMPLES : 160,
        ),
      ),
    [palette, series, variable, sampleBounds, skiaExplorer],
  );
  return {
    plot: modalPlot,
    onPlotLayout: onModalPlotLayout,
    initialView: modalInitialView,
    viewport,
    drawn: modalDrawn,
  };
}

export function useFunctionPlotState(spec: GraphSpec, chartWidth: number, theme: Theme) {
  const insets = useSafeAreaInsets();
  const [open, setOpen] = useState(false);
  const closeExplorer = useCallback(() => setOpen(false), []);
  const cardClipId = useId().replace(/:/g, "");
  const modalClipId = useId().replace(/:/g, "");
  const seedExprs = hasCurve2(spec) ? [spec.expr, spec.expr2 ?? ""] : [spec.expr];
  const seedFallbacks = hasCurve2(spec)
    ? [
        { points: spec.points, segments: spec.segments },
        { points: spec.points2 ?? [], segments: spec.segments2 },
      ]
    : [{ points: spec.points, segments: spec.segments }];
  const { series, canAdd, setExpr, toggleVisible, removeSeries, addSeries } = useGraphSeries(
    seedExprs,
    seedFallbacks,
  );
  const curves: Curves = { series, palette: theme.graphSeries, variable: spec.variable ?? "x" };
  const holes = useHoleMarkers(spec, curves);
  const card = useCardPlot(spec, chartWidth, curves);
  const skia = isSkiaAvailable();
  const explorer = useExplorerPlot(spec, insets, skia, curves);
  const seriesListRef = useRef<ScrollView>(null);
  const addSeriesAndReveal = () => {
    addSeries();
    requestAnimationFrame(() => {
      seriesListRef.current?.scrollToEnd({ animated: true });
    });
  };

  return {
    open,
    openExplorer: () => setOpen(true),
    closeExplorer,
    insets,
    skia,
    verticalX: spec.type === "vertical" ? spec.x : undefined,
    holes,
    editor: { canAdd, setExpr, toggleVisible, removeSeries, addSeries, addSeriesAndReveal, seriesListRef },
    card: { ...card, clipId: cardClipId },
    explorer: { ...explorer, clipId: modalClipId },
  };
}
