import { useMemo } from "react";
import { View } from "react-native";
import {
  Canvas,
  Circle,
  Group,
  Path,
  Skia,
  Text as SkiaText,
  useFont,
} from "@shopify/react-native-skia";

import {
  GRAPH_CHART_PAD,
  GRAPH_TICK_FONT_SIZE,
} from "@/components/rich/graphPaint";
import {
  formatInequalityExpr,
  mapGraphPoint,
  numberLineBounds,
  numberLineTicks,
} from "@/lib/math/graphBlock";
import { type GraphSpec } from "@/lib/math/graphSpec";


type Props = {
  spec: GraphSpec;
  width: number;
  height: number;
  color: string;
  axisColor: string;
  labelColor: string;
  surfaceColor: string;
};

function valueToPx(
  value: number,
  bounds: { xMin: number; xMax: number },
  width: number,
  height: number,
) {
  return mapGraphPoint(value, 0, { ...bounds, yMin: -1, yMax: 1 }, width, height, GRAPH_CHART_PAD).px;
}

function addArrowHead(
  path: ReturnType<typeof Skia.Path.Make>,
  x: number,
  y: number,
  direction: "left" | "right",
) {
  const size = 6;
  const point = direction === "right" ? x + size * 1.4 : x - size * 1.4;
  path.moveTo(x, y - size);
  path.lineTo(x, y + size);
  path.lineTo(point, y);
  path.close();
}

function formatTick(value: number) {
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(6)));
}

export function SkiaNumberLineChart({
  spec,
  width,
  height,
  color,
  axisColor,
  labelColor,
  surfaceColor,
}: Props) {
  const font = useFont(
    require("../../../assets/fonts/KaTeX_Main-Regular.ttf"),
    GRAPH_TICK_FONT_SIZE,
  );
  const intervals = useMemo(() => spec.intervals ?? [], [spec.intervals]);
  const bounds = useMemo(() => numberLineBounds(intervals), [intervals]);
  const ticks = useMemo(
    () => numberLineTicks(bounds.xMin, bounds.xMax),
    [bounds.xMax, bounds.xMin],
  );
  const y = height / 2;

  const axisPath = useMemo(() => {
    const path = Skia.Path.Make();
    path.moveTo(GRAPH_CHART_PAD, y);
    path.lineTo(width - GRAPH_CHART_PAD, y);
    ticks.forEach((value) => {
      const px = valueToPx(value, bounds, width, height);
      path.moveTo(px, y - 5);
      path.lineTo(px, y + 5);
    });
    return path;
  }, [bounds, height, ticks, width, y]);

  const intervalPath = useMemo(() => {
    const path = Skia.Path.Make();
    intervals.forEach((interval) => {
      if (interval.start != null && interval.end != null && interval.start !== interval.end) {
        path.moveTo(valueToPx(interval.start, bounds, width, height), y);
        path.lineTo(valueToPx(interval.end, bounds, width, height), y);
      } else if (interval.start == null && interval.end != null) {
        path.moveTo(GRAPH_CHART_PAD, y);
        path.lineTo(valueToPx(interval.end, bounds, width, height), y);
      } else if (interval.end == null && interval.start != null) {
        path.moveTo(valueToPx(interval.start, bounds, width, height), y);
        path.lineTo(width - GRAPH_CHART_PAD, y);
      }
    });
    return path;
  }, [bounds, height, intervals, width, y]);

  const axisArrowPath = useMemo(() => {
    const path = Skia.Path.Make();
    addArrowHead(path, GRAPH_CHART_PAD, y, "left");
    addArrowHead(path, width - GRAPH_CHART_PAD, y, "right");
    return path;
  }, [width, y]);

  const intervalArrowPath = useMemo(() => {
    const path = Skia.Path.Make();
    intervals.forEach((interval) => {
      if (interval.start == null && interval.end != null) addArrowHead(path, GRAPH_CHART_PAD, y, "left");
      if (interval.end == null && interval.start != null) {
        addArrowHead(path, width - GRAPH_CHART_PAD, y, "right");
      }
    });
    return path;
  }, [intervals, width, y]);

  const markers = useMemo(
    () =>
      intervals.flatMap((interval, index) => {
        const result: { value: number; inclusive: boolean; key: string }[] = [];
        if (interval.start != null) {
          result.push({
            value: interval.start,
            inclusive: interval.start_inclusive,
            key: `start-${index}`,
          });
        }
        if (interval.end != null && interval.end !== interval.start) {
          result.push({
            value: interval.end,
            inclusive: interval.end_inclusive,
            key: `end-${index}`,
          });
        }
        return result;
      }),
    [intervals],
  );

  return (
    <View
      accessible
      accessibilityRole="image"
      accessibilityLabel={formatInequalityExpr(spec.expr)}
      style={{ width, height }}
    >
      <Canvas testID="skia-number-line-canvas" style={{ width, height }}>
        <Path path={axisPath} color={axisColor} style="stroke" strokeWidth={1.5} />
        <Path path={axisArrowPath} color={axisColor} style="fill" />
        <Path path={intervalArrowPath} color={color} style="fill" />
        <Path
          path={intervalPath}
          color={color}
          style="stroke"
          strokeWidth={4}
          strokeCap="round"
        />
        {markers.map((marker) => {
          const cx = valueToPx(marker.value, bounds, width, height);
          return marker.inclusive ? (
            <Circle key={marker.key} cx={cx} cy={y} r={5} color={color} />
          ) : (
            <Group key={marker.key}>
              <Circle cx={cx} cy={y} r={5} color={color} />
              <Circle cx={cx} cy={y} r={2.5} color={surfaceColor} />
            </Group>
          );
        })}
        {font
          ? ticks.map((value) => {
              const label = formatTick(value);
              const px = valueToPx(value, bounds, width, height);
              return (
                <SkiaText
                  key={`tick-${label}`}
                  x={px - font.measureText(label).width / 2}
                  y={y + 20}
                  text={label}
                  font={font}
                  color={labelColor}
                />
              );
            })
          : null}
        {font ? (
          <SkiaText
            x={width - GRAPH_CHART_PAD + 10 - font.measureText(spec.variable ?? "x").width}
            y={y - 10}
            text={spec.variable ?? "x"}
            font={font}
            color={labelColor}
          />
        ) : null}
      </Canvas>
    </View>
  );
}
