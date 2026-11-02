/**
 * The full-screen function plot: a sheet with a drag handle and a close
 * button over a pinch-and-pan plot (Skia when it is available, SVG
 * otherwise), with the series editor under it.
 */
import { Suspense, useMemo, type ReactNode } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  View,
  type LayoutChangeEvent,
} from "react-native";
import { GestureDetector, GestureHandlerRootView } from "react-native-gesture-handler";
import Animated from "react-native-reanimated";
import { useTranslation } from "react-i18next";

import { GraphCanvas, GRAPH_AXIS_PAD, type GraphHoleMarker } from "@/components/rich/GraphCanvas";
import { SkiaGraphCanvasLazy } from "@/components/rich/skia/SkiaGraphCanvasLazy";
import { type DrawnSeries, useGraphViewport } from "@/hooks/useInteractiveGraph";
import { useSkiaGraphViewport } from "@/hooks/useSkiaGraphViewport";
import { xAxisInPi } from "@/lib/math/graphFit";
import { type GraphSpec } from "@/lib/math/graphSpec";
import { defaultInteractiveBounds } from "@/lib/math/graphViewport";
import { Radius } from "@/lib/radius";
import { useReduceMotion } from "@/lib/reduceMotion";
import { Space } from "@/lib/space";
import { Theme } from "@/lib/theme";
import { HeaderButton } from "@/ui/controls/HeaderButton";
import { FullScreenModal } from "@/ui/overlay/FullScreenModal";
import { useSheetPanDismiss } from "@/ui/overlay/useSheetPanDismiss";

export const MODAL_PLOT_MIN = 200;

export function ExplorerModal({
  open,
  onClose,
  theme,
  insets,
  spec,
  clipId,
  plot,
  onPlotLayout,
  bounds,
  gesture,
  drawn,
  holes,
  verticalX,
  editor,
  skia,
  initialView,
  onCommitBounds,
}: {
  open: boolean;
  onClose: () => void;
  theme: Theme;
  insets: { top: number; bottom: number };
  spec: GraphSpec;
  clipId: string;
  plot: { width: number; height: number };
  onPlotLayout: (e: LayoutChangeEvent) => void;
  bounds: ReturnType<typeof defaultInteractiveBounds>;
  gesture: ReturnType<typeof useGraphViewport>["gesture"];
  drawn: DrawnSeries[];
  holes: GraphHoleMarker[];
  verticalX?: number;
  editor: ReactNode;
  skia: boolean;
  initialView: ReturnType<typeof defaultInteractiveBounds>;
  onCommitBounds: (next: ReturnType<typeof defaultInteractiveBounds>) => void;
}) {
  const { t } = useTranslation();
  const styles = useMemo(() => makeExplorerModalStyles(theme), [theme]);
  const reduceMotion = useReduceMotion();
  const { pan, panStyle } = useSheetPanDismiss(open, reduceMotion, onClose);
  const skiaViewport = useSkiaGraphViewport({
    width: plot.width,
    height: plot.height,
    pad: GRAPH_AXIS_PAD,
    initialView,
    onCommit: onCommitBounds,
  });

  return (
    <FullScreenModal
      visible={open}
      transparent
      animationType="slide"
      onRequestClose={onClose}
    >
      {open ? (
        <GestureHandlerRootView
          style={[styles.modalRoot, styles.modalBackdrop]}
          testID="graph-modal-backdrop"
        >
          <KeyboardAvoidingView
            style={styles.modalRoot}
            testID="graph-modal-keyboard-host"
            behavior={Platform.OS === "ios" ? "padding" : undefined}
          >
            <Animated.View
              testID="graph-modal-sheet"
              style={[
                styles.modalSheet,
                {
                  backgroundColor: theme.elevated,
                  marginTop: Math.max(insets.top, Space.sm),
                  paddingBottom: insets.bottom,
                },
                panStyle,
              ]}
            >
              <GestureDetector gesture={pan}>
                <View style={styles.modalToolbar} testID="graph-sheet-handle">
                  <View style={styles.handle} />
                  <HeaderButton
                    icon="close"
                    onPress={onClose}
                    testID="graph-close"
                    accessibilityLabel={t("preview.close")}
                    style={styles.closeBtn}
                  />
                </View>
              </GestureDetector>
              {skia ? (
                // Own the native touch surface here, just like the SVG
                // fallback below. Keeping the detector inside a box-only
                // parent made the parent swallow every pinch and pan.
                <GestureDetector gesture={skiaViewport.gesture}>
                  <View
                    collapsable={false}
                    pointerEvents="box-only"
                    accessible
                    accessibilityLabel={t("rich.graph_plot_a11y")}
                    testID="graph-interaction-surface"
                    onLayout={onPlotLayout}
                    style={styles.modalPlot}
                  >
                    <Suspense
                      fallback={
                        <View style={styles.skiaLoading}>
                          <ActivityIndicator color={theme.textSecondary} />
                        </View>
                      }
                    >
                      <SkiaGraphCanvasLazy
                        drawn={drawn}
                        holes={holes}
                        verticalX={verticalX}
                        xName={spec.variable ?? "x"}
                        yName="y"
                        xInPi={xAxisInPi(spec)}
                        width={plot.width}
                        height={plot.height}
                        pad={GRAPH_AXIS_PAD}
                        theme={theme}
                        viewport={skiaViewport}
                      />
                    </Suspense>
                  </View>
                </GestureDetector>
              ) : (
                <GestureDetector gesture={gesture}>
                  <View
                    collapsable={false}
                    pointerEvents="box-only"
                    accessible
                    accessibilityLabel={t("rich.graph_plot_a11y")}
                    onLayout={onPlotLayout}
                    style={styles.modalPlot}
                  >
                    <GraphCanvas
                      spec={spec}
                      theme={theme}
                      clipId={clipId}
                      width={plot.width}
                      height={plot.height}
                      bounds={bounds}
                      drawn={drawn}
                      holes={holes}
                      verticalX={verticalX}
                    />
                  </View>
                </GestureDetector>
              )}
              {editor}
            </Animated.View>
          </KeyboardAvoidingView>
        </GestureHandlerRootView>
      ) : null}
    </FullScreenModal>
  );
}

const makeExplorerModalStyles = (theme: Theme) =>
  StyleSheet.create({
    modalRoot: {
      flex: 1,
    },
    modalBackdrop: {
      backgroundColor: theme.scrim,
    },
    modalSheet: {
      flex: 1,
      borderTopLeftRadius: Radius.sheet,
      borderTopRightRadius: Radius.sheet,
      borderTopWidth: StyleSheet.hairlineWidth,
      borderColor: theme.border,
      overflow: "hidden",
    },
    modalToolbar: {
      alignSelf: "stretch",
      minHeight: 60,
    },
    handle: {
      alignSelf: "center",
      width: 48,
      height: 5,
      borderRadius: Radius.full,
      backgroundColor: theme.textTertiary,
      marginTop: Space.sm,
      marginBottom: Space.xs,
    },
    closeBtn: {
      alignSelf: "flex-start",
      marginLeft: Space.sm,
    },
    modalPlot: {
      flex: 1,
      minHeight: MODAL_PLOT_MIN,
      marginHorizontal: Space.sm,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: theme.border,
      borderRadius: Radius.md,
      backgroundColor: theme.surface,
      overflow: "hidden",
    },
    skiaLoading: {
      flex: 1,
      alignItems: "center",
      justifyContent: "center",
    },
  });
