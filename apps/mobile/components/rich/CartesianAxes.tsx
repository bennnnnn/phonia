import { ClipPath, Defs, Line, Rect, Text as SvgText } from "react-native-svg";

import {
  formatAxisNumber,
  graphAxisTicks,
  mapGraphPoint,
} from "@/lib/math/graphBlock";
import { formatPiTickW, piTicksW, tickCountW } from "@/lib/math/graphWorklets";
import { UI_FONT } from "@/lib/uiFont";

type Bounds = {
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
};

type Props = {
  width: number;
  height: number;
  pad: number;
  bounds: Bounds;
  clipId: string;
  axisColor: string;
  labelColor: string;
  gridColor: string;
  xName: string;
  yName: string;
  /** Viewports that exclude zero still need visible axis labels at the edge. */
  keepAxesInView?: boolean;
  /** Explicit viewports may require noninteger tick labels. */
  fractionalTicks?: boolean;
  /** Label x in multiples of π (an x-range given as 0…2π). */
  piTicks?: boolean;
};

const TICK_FONT = 11;

/** Grid, axes, and even tick labels for a function/trajectory plot. */
export function CartesianAxes({
  width,
  height,
  pad,
  bounds,
  clipId,
  axisColor,
  labelColor,
  gridColor,
  xName,
  yName,
  keepAxesInView = false,
  fractionalTicks = false,
  piTicks = false,
}: Props) {
  const innerW = width - pad * 2;
  const innerH = height - pad * 2;
  const origin = mapGraphPoint(0, 0, bounds, width, height, pad);
  const yAxisX = keepAxesInView ? Math.max(pad, Math.min(width - pad, origin.px)) : origin.px;
  const xAxisY = keepAxesInView ? Math.max(pad, Math.min(height - pad, origin.py)) : origin.py;
  const xTicks = piTicks
    ? piTicksW(bounds.xMin, bounds.xMax)
    : graphAxisTicks(bounds.xMin, bounds.xMax, tickCountW(bounds.xMin, bounds.xMax), fractionalTicks);
  const xLabel = (n: number) => (piTicks ? formatPiTickW(n) : formatAxisNumber(n, fractionalTicks));
  const yTicks = graphAxisTicks(
    bounds.yMin,
    bounds.yMax,
    tickCountW(bounds.yMin, bounds.yMax),
    fractionalTicks,
  );

  return (
    <>
      <Defs>
        <ClipPath id={clipId}>
          <Rect x={pad} y={pad} width={innerW} height={innerH} />
        </ClipPath>
      </Defs>
      {xTicks.map((n) => {
        if (Math.abs(n) < 1e-9) return null;
        const { px } = mapGraphPoint(n, 0, bounds, width, height, pad);
        return (
          <Line
            key={`gx-${n}`}
            x1={px}
            y1={pad}
            x2={px}
            y2={height - pad}
            stroke={gridColor}
            strokeWidth={1}
          />
        );
      })}
      {yTicks.map((n) => {
        if (Math.abs(n) < 1e-9) return null;
        const { py } = mapGraphPoint(0, n, bounds, width, height, pad);
        return (
          <Line
            key={`gy-${n}`}
            x1={pad}
            y1={py}
            x2={width - pad}
            y2={py}
            stroke={gridColor}
            strokeWidth={1}
          />
        );
      })}
      <Line
        x1={yAxisX}
        y1={pad}
        x2={yAxisX}
        y2={height - pad}
        stroke={axisColor}
        strokeWidth={1.25}
      />
      <Line
        x1={pad}
        y1={xAxisY}
        x2={width - pad}
        y2={xAxisY}
        stroke={axisColor}
        strokeWidth={1.25}
      />
      {xTicks.map((n) => {
        if (Math.abs(n) < 1e-9) return null;
        const { px } = mapGraphPoint(n, 0, bounds, width, height, pad);
        return (
          <SvgText
            key={`lx-${n}`}
            x={px}
            y={xAxisY + 16}
            fill={labelColor}
            fontSize={TICK_FONT}
            fontFamily={UI_FONT.regular}
            textAnchor="middle"
          >
            {xLabel(n)}
          </SvgText>
        );
      })}
      {yTicks.map((n) => {
        if (Math.abs(n) < 1e-9) return null;
        const { py } = mapGraphPoint(0, n, bounds, width, height, pad);
        if (py < pad + 12) return null;
        return (
          <SvgText
            key={`ly-${n}`}
            x={Math.max(4, yAxisX - 6)}
            y={py + 4}
            fill={labelColor}
            fontSize={TICK_FONT}
            fontFamily={UI_FONT.regular}
            textAnchor="end"
          >
            {formatAxisNumber(n, fractionalTicks)}
          </SvgText>
        );
      })}
      {bounds.xMin <= 0 && bounds.xMax >= 0 && bounds.yMin <= 0 && bounds.yMax >= 0 ? (
        <SvgText
          x={origin.px + 10}
          y={origin.py + 16}
          fill={labelColor}
          fontSize={TICK_FONT}
          fontFamily={UI_FONT.regular}
          textAnchor="start"
        >
          0
        </SvgText>
      ) : null}
      <SvgText
        x={width - pad}
        y={xAxisY - 6}
        fill={labelColor}
        fontSize={TICK_FONT}
        fontFamily={UI_FONT.regular}
        textAnchor="end"
      >
        {xName}
      </SvgText>
      {/* Anchored at its start, not its middle. A centred label puts half its
          width to the left of the axis, and the axis sits at `pad` — so
          anything longer than ~2·pad ran off the canvas and was clipped:
          "Velocity (m/s)" rendered as "elocity (m/s)". Growing rightward from
          the axis cannot clip, and the top-left of a plot is empty anyway. */}
      <SvgText
        x={Math.max(yAxisX - TICK_FONT, 2)}
        y={pad - 2}
        fill={labelColor}
        fontSize={TICK_FONT}
        fontFamily={UI_FONT.regular}
        textAnchor="start"
      >
        {yName}
      </SvgText>
    </>
  );
}
