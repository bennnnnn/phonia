import React, { lazy, Suspense } from "react";
import Svg, { Circle, Line, Polygon, Text as SvgText } from "react-native-svg";

import { GRAPH_CHART_PAD } from "@/components/rich/graphPaint";
import {
  formatInequalityExpr,
  mapGraphPoint,
  numberLineBounds,
  numberLineTicks,
} from "@/lib/math/graphBlock";
import { GraphSpec, NumberLineInterval } from "@/lib/math/graphSpec";
import { isSkiaAvailable } from "@/lib/skiaAvailability";
import { UI_FONT } from "@/lib/uiFont";

type Props = {
  spec: GraphSpec;
  width: number;
  height: number;
  color: string;
  axisColor: string;
  labelColor: string;
  surfaceColor: string;
};

const LINE_HEIGHT = 80;

const SkiaNumberLineChartLazy = lazy(() =>
  import("@/components/rich/skia/SkiaNumberLineChart").then((module) => ({
    default: module.SkiaNumberLineChart,
  })),
);

function formatTick(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

/** Map a value on the number line to its pixel x coordinate. */
function valueToPx(
  value: number,
  bounds: { xMin: number; xMax: number },
  width: number,
): number {
  return mapGraphPoint(value, 0, { ...bounds, yMin: -1, yMax: 1 }, width, LINE_HEIGHT, GRAPH_CHART_PAD).px;
}

/** Draw an arrowhead pointing left or right at the given x,y. */
function arrowHead(
  x: number,
  y: number,
  dir: "left" | "right",
  color: string,
  key: string,
) {
  const size = 6;
  const points =
    dir === "right"
      ? `${x},${y - size} ${x},${y + size} ${x + size * 1.4},${y}`
      : `${x},${y - size} ${x},${y + size} ${x - size * 1.4},${y}`;
  return <Polygon key={key} points={points} fill={color} />;
}

/** Thick colored segment for a closed interval [start, end]. */
function intervalSegment(
  iv: NumberLineInterval,
  bounds: { xMin: number; xMax: number },
  width: number,
  y: number,
  color: string,
  key: string,
) {
  if (iv.start == null || iv.end == null) return null;
  if (iv.start === iv.end) return null;
  const x1 = valueToPx(iv.start, bounds, width);
  const x2 = valueToPx(iv.end, bounds, width);
  return (
    <Line
      key={key}
      x1={Math.min(x1, x2)}
      y1={y}
      x2={Math.max(x1, x2)}
      y2={y}
      stroke={color}
      strokeWidth={4}
      strokeLinecap="round"
    />
  );
}

/** Ray from an endpoint to the edge of the chart, with an arrowhead. */
function raySegment(
  iv: NumberLineInterval,
  bounds: { xMin: number; xMax: number },
  width: number,
  y: number,
  color: string,
  keyPrefix: string,
) {
  const elements: React.ReactNode[] = [];
  if (iv.start == null && iv.end != null) {
    // Ray to the left: (-∞, end]
    const xEnd = valueToPx(iv.end, bounds, width);
    const xLeft = GRAPH_CHART_PAD;
    elements.push(
      <Line
        key={`${keyPrefix}-line`}
        x1={xLeft}
        y1={y}
        x2={xEnd}
        y2={y}
        stroke={color}
        strokeWidth={4}
        strokeLinecap="round"
      />,
    );
    elements.push(arrowHead(xLeft, y, "left", color, `${keyPrefix}-arrow`));
  } else if (iv.end == null && iv.start != null) {
    // Ray to the right: [start, ∞)
    const xStart = valueToPx(iv.start, bounds, width);
    const xRight = width - GRAPH_CHART_PAD;
    elements.push(
      <Line
        key={`${keyPrefix}-line`}
        x1={xStart}
        y1={y}
        x2={xRight}
        y2={y}
        stroke={color}
        strokeWidth={4}
        strokeLinecap="round"
      />,
    );
    elements.push(arrowHead(xRight, y, "right", color, `${keyPrefix}-arrow`));
  }
  return elements;
}

/** Endpoint marker: filled circle for inclusive, hollow circle for exclusive. */
function endpointMarker(
  value: number,
  inclusive: boolean,
  bounds: { xMin: number; xMax: number },
  width: number,
  y: number,
  color: string,
  surfaceColor: string,
  key: string,
) {
  const cx = valueToPx(value, bounds, width);
  if (inclusive) {
    return <Circle key={key} cx={cx} cy={y} r={5} fill={color} />;
  }
  return (
    <Circle
      key={key}
      cx={cx}
      cy={y}
      r={5}
      fill={surfaceColor}
      stroke={color}
      strokeWidth={2.5}
    />
  );
}

export function NumberLineChart(props: Props) {
  if (!isSkiaAvailable()) return <SvgNumberLineChart {...props} />;
  return (
    <Suspense fallback={<SvgNumberLineChart {...props} />}>
      <SkiaNumberLineChartLazy {...props} />
    </Suspense>
  );
}

function SvgNumberLineChart({
  spec,
  width,
  height,
  color,
  axisColor,
  labelColor,
  surfaceColor,
}: Props) {
  const intervals = spec.intervals ?? [];
  const xBounds = numberLineBounds(intervals);
  const y = height / 2;
  const ticks = numberLineTicks(xBounds.xMin, xBounds.xMax);

  return (
    <Svg
      width={width}
      height={height}
      accessibilityLabel={formatInequalityExpr(spec.expr)}
    >
      {/* Main horizontal axis */}
      <Line
        x1={GRAPH_CHART_PAD}
        y1={y}
        x2={width - GRAPH_CHART_PAD}
        y2={y}
        stroke={axisColor}
        strokeWidth={1.5}
      />
      {/* Arrowheads at both ends of the axis to show it extends infinitely */}
      {arrowHead(width - GRAPH_CHART_PAD, y, "right", axisColor, "axis-arrow-right")}
      {arrowHead(GRAPH_CHART_PAD, y, "left", axisColor, "axis-arrow-left")}

      {/* Tick marks */}
      {ticks.map((n) => {
        const px = valueToPx(n, xBounds, width);
        return (
          <Line
            key={`tick-${n}`}
            x1={px}
            y1={y - 5}
            x2={px}
            y2={y + 5}
            stroke={axisColor}
            strokeWidth={1}
          />
        );
      })}

      {/* Tick labels */}
      {ticks.map((n) => {
        const px = valueToPx(n, xBounds, width);
        return (
          <SvgText
            key={`tick-label-${n}`}
            x={px}
            y={y + 20}
            fill={labelColor}
            fontSize={11}
            fontFamily={UI_FONT.regular}
            textAnchor="middle"
          >
            {formatTick(n)}
          </SvgText>
        );
      })}

      {/* Shaded intervals and rays */}
      {intervals.map((iv, i) => (
        <React.Fragment key={`iv-${i}`}>
          {intervalSegment(iv, xBounds, width, y, color, `seg-${i}`)}
          {raySegment(iv, xBounds, width, y, color, `ray-${i}`)}
        </React.Fragment>
      ))}

      {/* Endpoint markers (drawn after segments so they sit on top) */}
      {intervals.map((iv, i) => {
        const markers: React.ReactNode[] = [];
        if (iv.start != null) {
          markers.push(
            endpointMarker(
              iv.start,
              iv.start_inclusive,
              xBounds,
              width,
              y,
              color,
              surfaceColor,
              `m-s-${i}`,
            ),
          );
        }
        if (iv.end != null && iv.end !== iv.start) {
          markers.push(
            endpointMarker(
              iv.end,
              iv.end_inclusive,
              xBounds,
              width,
              y,
              color,
              surfaceColor,
              `m-e-${i}`,
            ),
          );
        }
        return markers;
      })}

      {/* Variable label at the right end */}
      <SvgText
        x={width - GRAPH_CHART_PAD + 10}
        y={y - 10}
        fill={labelColor}
        fontSize={11}
        fontFamily={UI_FONT.regular}
        textAnchor="end"
      >
        {spec.variable ?? "x"}
      </SvgText>
    </Svg>
  );
}
