import { useId, useMemo } from "react";
import { StyleSheet } from "react-native";
import Svg, { Circle, Defs, Pattern, Rect } from "react-native-svg";

import { dotGridLayout, type DotGrid } from "@/features/images/model/dotGrid";
import { withAlpha } from "@/lib/theme";

import { type DotFieldPalette, WAVE_DOT_RADIUS, WAVE_PITCH } from "./dotField";

type PatternProps = { grid: DotGrid; radius: number; fill: string };

/**
 * One dot per grid cell as a single SVG pattern, laid out by `dotGridLayout`
 * so it lines up with the wave shader and the dot game. Render inside an `Svg`.
 */
export function DotGridPattern({ grid, radius, fill }: PatternProps) {
  const id = `dots${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const half = grid.pitch / 2;
  const x = grid.originX - half;
  const y = grid.originY - half;
  return (
    <>
      <Defs>
        <Pattern
          id={id}
          x={x}
          y={y}
          width={grid.pitch}
          height={grid.pitch}
          patternUnits="userSpaceOnUse"
        >
          <Circle cx={half} cy={half} r={radius} fill={fill} />
        </Pattern>
      </Defs>
      <Rect
        x={x}
        y={y}
        width={grid.cols * grid.pitch}
        height={grid.rows * grid.pitch}
        fill={`url(#${id})`}
      />
    </>
  );
}

type FieldProps = { width: number; height: number; palette: DotFieldPalette };

/** The waiting card's fine grid, still: Reduce Motion, a canceled or failed card. */
export function StaticDotField({ width, height, palette }: FieldProps) {
  const grid = useMemo(() => dotGridLayout(width, height, WAVE_PITCH), [width, height]);
  return (
    <Svg
      width={width}
      height={height}
      style={StyleSheet.absoluteFill}
      testID="image-gen-dots-static"
    >
      <DotGridPattern
        grid={grid}
        radius={WAVE_DOT_RADIUS}
        fill={withAlpha(palette.dot.color, palette.dot.opacity)}
      />
    </Svg>
  );
}
