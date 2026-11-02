import Svg, { Circle, G, Polygon, Polyline } from "react-native-svg";

import { CartesianAxes } from "@/components/rich/CartesianAxes";
import { type DrawnSeries } from "@/hooks/useInteractiveGraph";
import {
  graphPolylinePoints,
  graphXIntercepts,
  interiorVertex,
  mapGraphPoint,
  SHIFTED_VERTEX_MIN,
} from "@/lib/math/graphBlock";
import { xAxisInPi } from "@/lib/math/graphFit";
import { type GraphSpec } from "@/lib/math/graphSpec";
import { inequalityFillPoints, type GraphCmp } from "@/lib/math/graphExpr";
import { type GraphView } from "@/lib/math/graphViewport";
import { Theme } from "@/lib/theme";

export const GRAPH_AXIS_PAD = 16;
const MAX_MARKED_POINTS = 20;
const INEQUALITY_DASH = "6 5";

type Props = {
  spec: GraphSpec;
  theme: Theme;
  clipId: string;
  width: number;
  height: number;
  bounds: GraphView;
  drawn: DrawnSeries[];
  holes?: GraphHoleMarker[];
  verticalX?: number;
};

export type GraphHoleMarker = {
  point: [number, number];
  color: string;
};

export function GraphCanvas({
  spec,
  theme,
  clipId,
  width,
  height,
  bounds,
  drawn,
  holes = [],
  verticalX,
}: Props) {
  const isVerticalLine = verticalX != null;
  const visibleSeries = drawn.filter((row) => row.visible);
  const primary = drawn[0];
  const inView = ([x, y]: [number, number]) =>
    x >= bounds.xMin && x <= bounds.xMax && y >= bounds.yMin && y <= bounds.yMax;
  const scatterMarkers =
    !isVerticalLine &&
    visibleSeries.length === 1 &&
    primary.points.length <= MAX_MARKED_POINTS
      ? primary.points.filter(inView).map(([x, y]) => mapGraphPoint(x, y, bounds, width, height, GRAPH_AXIS_PAD))
      : [];
  const vertex =
    !isVerticalLine && visibleSeries.length === 1 ? interiorVertex(primary.points) : null;
  const rootMarkers =
    vertex && Math.abs(vertex.y) >= SHIFTED_VERTEX_MIN
      ? graphXIntercepts(primary.points)
          .filter((x) => x >= bounds.xMin && x <= bounds.xMax)
          .slice(0, 3)
          .map((x) => mapGraphPoint(x, 0, bounds, width, height, GRAPH_AXIS_PAD))
      : [];
  const clip = `url(#${clipId})`;
  const holeMarkers = holes
    .filter(({ point }) => inView(point))
    .map(({ point: [x, y], color }) => ({
      ...mapGraphPoint(x, y, bounds, width, height, GRAPH_AXIS_PAD),
      color,
    }));

  return (
    <Svg width={width} height={height}>
      <CartesianAxes
        width={width}
        height={height}
        pad={GRAPH_AXIS_PAD}
        bounds={bounds}
        clipId={clipId}
        axisColor={theme.textSecondary}
        labelColor={theme.textSecondary}
        gridColor={theme.border}
        xName={spec.variable ?? "x"}
        yName="y"
        fractionalTicks
        piTicks={xAxisInPi(spec)}
      />
      <G clipPath={clip}>
        {isVerticalLine ? (
          <Polyline
            points={graphPolylinePoints(
              [
                [verticalX, bounds.yMin],
                [verticalX, bounds.yMax],
              ],
              width,
              height,
              bounds,
              GRAPH_AXIS_PAD,
            )}
            fill="none"
            stroke={theme.primary}
            strokeWidth={2.5}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ) : (
          visibleSeries.map((row) => (
            <SeriesPolylines key={row.id} row={row} width={width} height={height} bounds={bounds} />
          ))
        )}
      </G>
      {scatterMarkers.map(({ px, py }, i) => (
        <Circle key={i} cx={px} cy={py} r={4} fill={primary.color} />
      ))}
      {rootMarkers.map(({ px, py }, i) => (
        <Circle key={`root-${i}`} cx={px} cy={py} r={4} fill={theme.danger} />
      ))}
      {holeMarkers.map(({ px, py, color }, i) => (
        <Circle
          key={`hole-${i}`}
          testID={`graph-hole-${i}`}
          cx={px}
          cy={py}
          r={5}
          fill={theme.elevated}
          stroke={color}
          strokeWidth={2.25}
        />
      ))}
    </Svg>
  );
}

function isStrictInequality(cmp: GraphCmp): boolean {
  return cmp === "<" || cmp === ">";
}

function SeriesPolylines({
  row,
  width,
  height,
  bounds,
}: {
  row: DrawnSeries;
  width: number;
  height: number;
  bounds: GraphView;
}) {
  const segs = row.segments?.filter((seg) => seg.length >= 2);
  const curves = segs && segs.length > 1 ? segs : row.points.length >= 2 ? [row.points] : [];
  if (curves.length === 0) return null;
  const dashed = isStrictInequality(row.cmp);
  return (
    <>
      {curves.map((seg, i) => {
        const fill = inequalityFillPoints(seg, bounds.yMin, bounds.yMax, row.cmp);
        return (
          <G key={`${row.id}-${i}`}>
            {fill.length > 0 ? (
              <Polygon
                testID={`graph-shade-${row.id}`}
                points={graphPolylinePoints(fill, width, height, bounds, GRAPH_AXIS_PAD)}
                fill={row.color}
                fillOpacity={0.16}
                stroke="none"
              />
            ) : null}
            <Polyline
              points={graphPolylinePoints(seg, width, height, bounds, GRAPH_AXIS_PAD)}
              fill="none"
              stroke={row.color}
              strokeWidth={2.5}
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeDasharray={dashed ? INEQUALITY_DASH : undefined}
            />
          </G>
        );
      })}
    </>
  );
}
