import { lazy, Suspense, useId, useMemo } from "react";
import { StyleSheet, Text, View } from "react-native";
import { useTranslation } from "react-i18next";
import Svg, { Circle, G, Polygon, Polyline } from "react-native-svg";

import { CartesianAxes } from "@/components/rich/CartesianAxes";
import {
  GRAPH_CHART_PAD,
  INEQUALITY_REGION_OPACITY,
  STRICT_BOUNDARY_DASH,
} from "@/components/rich/graphPaint";
import {
  formatGraphExpr,
  formatInequalityExpr,
  graphPolylinePoints,
  mapGraphPoint,
} from "@/lib/math/graphBlock";
import { type InequalityGraphSpec } from "@/lib/math/graphSpec";
import { clipInequalityRegion } from "@/lib/math/inequalityGraph";
import { isSkiaAvailable } from "@/lib/skiaAvailability";
import { useTheme } from "@/lib/theme";
import { Space } from "@/lib/space";
import { Type } from "@/lib/type";

const CHART_HEIGHT = 220;

const SkiaInequalityGraphChartLazy = lazy(() =>
  import("@/components/rich/skia/SkiaInequalityGraphChart").then((module) => ({
    default: module.SkiaInequalityGraphChart,
  })),
);

/** Verified half-plane rendered by Skia, with SVG as a compatibility fallback. */
export function InequalityGraphChart({ spec, width }: { spec: InequalityGraphSpec; width: number }) {
  const theme = useTheme();
  const { t } = useTranslation();
  const clipId = useId().replace(/:/g, "");
  const geometry = useMemo(() => clipInequalityRegion(spec), [spec]);
  const bounds = { xMin: spec.x_min, xMax: spec.x_max, yMin: spec.y_min, yMax: spec.y_max };
  const title = formatInequalityExpr(formatGraphExpr(spec.title ?? spec.expr));
  const formula = formatInequalityExpr(formatGraphExpr(spec.expr));
  const strict = spec.comparator === "<" || spec.comparator === ">";
  const regionLabel = t("rich.graph_solution_region");
  const boundaryLabel = t(strict ? "rich.graph_boundary_excluded" : "rich.graph_boundary_included");
  const accessibilityLabel = `${formula}. ${regionLabel}. ${boundaryLabel}.`;
  const mapped = (points: [number, number][]) => graphPolylinePoints(points, width, CHART_HEIGHT, bounds);

  if (!geometry) {
    return <Text style={{ color: theme.textSecondary }}>{t("rich.graph_error")}</Text>;
  }
  const includedCorner = !strict && geometry.boundary.length === 1
    ? mapGraphPoint(geometry.boundary[0][0], geometry.boundary[0][1], bounds, width, CHART_HEIGHT)
    : null;

  const svgCanvas = (
    <Svg
        width={width}
        height={CHART_HEIGHT}
        accessible
        accessibilityRole="image"
        accessibilityLabel={accessibilityLabel}
        testID="inequality-graph"
      >
        {/* The polygon is already clipped to the viewport. Draw it before
            axes so grid/tick contrast is not reduced by the fill. */}
        {geometry.region.length >= 3 ? (
          <Polygon testID="inequality-region" points={mapped(geometry.region)} fill={theme.primary} fillOpacity={INEQUALITY_REGION_OPACITY} />
        ) : null}
        <CartesianAxes
          width={width} height={CHART_HEIGHT} pad={GRAPH_CHART_PAD} bounds={bounds} clipId={clipId}
          axisColor={theme.textSecondary} labelColor={theme.textSecondary} gridColor={theme.border}
          xName="x" yName="y" keepAxesInView fractionalTicks
        />
        <G clipPath={`url(#${clipId})`}>
          {geometry.boundary.length >= 2 ? (
            <Polyline
              testID="inequality-boundary"
              points={mapped(geometry.boundary)} fill="none" stroke={theme.primary}
              strokeWidth={2.5} strokeDasharray={strict ? STRICT_BOUNDARY_DASH : undefined}
              strokeLinecap="butt"
            />
          ) : null}
        </G>
        {includedCorner ? (
          <Circle testID="inequality-boundary-point" cx={includedCorner.px} cy={includedCorner.py} r={3.5} fill={theme.primary} />
        ) : null}
    </Svg>
  );

  return (
    <View style={styles.wrap}>
      <Text style={[styles.title, { color: theme.text }]}>{title}</Text>
      {isSkiaAvailable() ? (
        <Suspense fallback={svgCanvas}>
          <SkiaInequalityGraphChartLazy
            spec={spec}
            width={width}
            height={CHART_HEIGHT}
            theme={theme}
            accessibilityLabel={accessibilityLabel}
          />
        </Suspense>
      ) : (
        svgCanvas
      )}
      <View style={styles.legend}>
        <View style={styles.legendItem}>
          <View style={[styles.swatch, { backgroundColor: theme.primary, opacity: INEQUALITY_REGION_OPACITY }]} />
          <Text style={[styles.legendText, { color: theme.textSecondary }]}>{regionLabel}</Text>
        </View>
        <View style={styles.legendItem}>
          <View
            style={[
              styles.boundarySwatch,
              { borderTopColor: theme.primary, borderStyle: strict ? "dashed" : "solid" },
            ]}
          />
          <Text style={[styles.legendText, { color: theme.textSecondary }]}>{boundaryLabel}</Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginVertical: Space.xs, alignItems: "center", maxWidth: "100%" },
  title: { ...Type.callout, marginBottom: Space.xs, textAlign: "center" },
  legend: { gap: Space.xs, alignSelf: "stretch", paddingHorizontal: GRAPH_CHART_PAD },
  legendItem: { flexDirection: "row", alignItems: "center", gap: Space.xs },
  legendText: { ...Type.meta, lineHeight: 17, flexShrink: 1 },
  swatch: { width: 24, height: 12, borderRadius: 2 },
  boundarySwatch: { width: 24, height: 1, borderTopWidth: 2.5 },
});
