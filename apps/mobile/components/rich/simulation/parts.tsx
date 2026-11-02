/** The scene's parts: solids, the pulley, supports, angles, the spring, strings and bodies. */
import { useMemo } from "react";
import { Circle, Group, Path, Skia } from "@shopify/react-native-skia";
import { useDerivedValue, type SharedValue } from "react-native-reanimated";

import {
  tetherEnd,
  type AngleLayout,
  type SceneLayout,
  type ScreenPoint,
  type SimulationArrow,
  type SolidLayout,
  type SupportLayout,
} from "@/lib/physics/simulation";
import { trajectoryPointAt } from "@/lib/math/trajectory";
import type { Theme } from "@/lib/theme";
import { appendArrowHead, linePath, pointsPath, segmentsPath } from "@/components/rich/skia/paths";
import {
  boxPath,
  rectPath,
  springPath,
  type Rect,
} from "@/components/rich/simulation/paths";
import {
  ARROW_STROKE,
  DerivedArrow,
  RESULT_STROKE,
  type Slope,
} from "@/components/rich/simulation/vectors";

const HUB_RADIUS = 2.5;

export function SolidShape({
  layout,
  fill,
  edge,
}: {
  layout: SolidLayout;
  fill: string;
  edge: string;
}) {
  const { box, solid } = layout;
  if (solid.kind === "fluid") {
    // A tank of water: a wash of blue with its surface drawn along the top.
    return (
      <>
        <Path path={rectPath(box)} color={fill} />
        <Path
          path={linePath(box.x, box.y, box.x + box.width, box.y)}
          color={edge}
          style="stroke"
          strokeWidth={ARROW_STROKE}
        />
      </>
    );
  }
  return (
    <>
      <Path path={rectPath(box)} color={fill} />
      <Path path={rectPath(box)} color={edge} style="stroke" strokeWidth={1} />
    </>
  );
}

export function PulleyWheel({
  layout,
  theme,
}: {
  layout: NonNullable<SceneLayout["pulley"]>;
  theme: Theme;
}) {
  const { centre, radius, rope } = layout;
  return (
    <>
      {/* The bracket it hangs from, up to the top of the canvas. */}
      <Path
        path={linePath(centre.px, centre.py, centre.px, 0)}
        color={theme.textSecondary}
        style="stroke"
        strokeWidth={2}
      />
      <Circle cx={centre.px} cy={centre.py} r={radius} color={theme.bg} />
      <Circle
        cx={centre.px}
        cy={centre.py}
        r={radius}
        color={theme.textSecondary}
        style="stroke"
        strokeWidth={ARROW_STROKE}
      />
      <Circle cx={centre.px} cy={centre.py} r={HUB_RADIUS} color={theme.textSecondary} />
      {rope ? (
        <Path
          path={pointsPath(rope)}
          color={theme.textSecondary}
          style="stroke"
          strokeWidth={ARROW_STROKE * 1.5}
          strokeCap="round"
        />
      ) : null}
    </>
  );
}

export function Support({ layout, theme }: { layout: SupportLayout; theme: Theme }) {
  return (
    <>
      <Path
        path={segmentsPath(layout.hatches)}
        color={theme.textTertiary}
        style="stroke"
        strokeWidth={1}
      />
      <Path
        path={linePath(layout.bar.x1, layout.bar.y1, layout.bar.x2, layout.bar.y2)}
        color={theme.textSecondary}
        style="stroke"
        strokeWidth={2}
        strokeCap="round"
      />
    </>
  );
}

export function AngleArc({ layout, theme }: { layout: AngleLayout; theme: Theme }) {
  const result = layout.angle.role === "result";
  const color = result ? theme.primary : theme.textSecondary;
  const strokeWidth = result ? RESULT_STROKE : ARROW_STROKE;
  const paths = useMemo(() => {
    const arc = pointsPath(layout.arc);
    const head = layout.head
      ? appendArrowHead(
          Skia.Path.Make(),
          layout.head.tip.px,
          layout.head.tip.py,
          layout.head.ux,
          layout.head.uy,
          layout.head.size,
          "filled",
        )
      : null;
    return { arc, head };
  }, [layout]);
  return (
    <>
      <Path
        path={paths.arc}
        color={color}
        style="stroke"
        strokeWidth={strokeWidth}
        strokeCap="round"
        strokeJoin="round"
      />
      {paths.head ? (
        <>
          <Path
            path={paths.head}
            color={color}
            style="stroke"
            strokeWidth={ARROW_STROKE}
            strokeJoin="round"
          />
          <Path path={paths.head} color={color} style="fill" />
        </>
      ) : null}
    </>
  );
}

export function SpringCoil({
  anchor,
  track,
  progress,
  color,
}: {
  anchor: ScreenPoint;
  track: ScreenPoint[];
  progress: SharedValue<number>;
  color: string;
}) {
  const path = useDerivedValue(() =>
    springPath(anchor, trajectoryPointAt(track, progress.value)),
  );
  return <Path path={path} color={color} style="stroke" strokeWidth={ARROW_STROKE} />;
}

export function Tether({
  anchor,
  track,
  radius,
  boxAngle,
  progress,
  color,
}: {
  anchor: ScreenPoint;
  track: ScreenPoint[];
  radius: number;
  boxAngle: number | null;
  progress: SharedValue<number>;
  color: string;
}) {
  const path = useDerivedValue(() => {
    const end = tetherEnd(anchor, trajectoryPointAt(track, progress.value), radius, boxAngle);
    const line = Skia.Path.Make();
    if (!end) return line;
    line.moveTo(anchor.px, anchor.py);
    line.lineTo(end.px, end.py);
    return line;
  });
  return (
    <Path path={path} color={color} style="stroke" strokeWidth={ARROW_STROKE} strokeCap="round" />
  );
}

/** A body's disc or box, with a halo of the background so lines behind it break around it. */
export function BodyShape({
  at,
  radius,
  boxAngle,
  color,
  halo,
  opacity,
}: {
  at: ScreenPoint | SharedValue<{ x: number; y: number }>;
  radius: number;
  boxAngle: number | null;
  color: string;
  halo?: string;
  opacity?: number;
}) {
  const point = "px" in at ? at : null;
  const live = "px" in at ? null : at;
  const box = useDerivedValue(() => {
    if (boxAngle === null) return Skia.Path.Make();
    const x = live ? live.value.x : point!.px;
    const y = live ? live.value.y : point!.py;
    return boxPath(x, y, radius, boxAngle);
  });
  const c = live ?? { x: point!.px, y: point!.py };
  if (boxAngle !== null) {
    return (
      <Group opacity={opacity ?? 1}>
        {halo ? (
          <Path path={box} color={halo} style="stroke" strokeWidth={3} strokeJoin="round" />
        ) : null}
        <Path path={box} color={color} />
      </Group>
    );
  }
  return (
    <Group opacity={opacity ?? 1}>
      {halo ? <Circle c={c} r={radius + 1.5} color={halo} /> : null}
      <Circle c={c} r={radius} color={color} />
    </Group>
  );
}

export function BodyMarks({
  track,
  closed,
  maxSpeed,
  radius,
  boxAngle,
  color,
  arrows,
  centre,
  slope,
  floorY,
  obstacles,
  progress,
  theme,
  canvasWidth,
  canvasHeight,
}: {
  track: ScreenPoint[];
  closed: boolean;
  maxSpeed: number;
  radius: number;
  boxAngle: number | null;
  color: string;
  arrows: SimulationArrow[];
  centre: ScreenPoint | null;
  slope: Slope | null;
  floorY: number | null;
  obstacles: Rect[];
  progress: SharedValue<number>;
  theme: Theme;
  canvasWidth: number;
  canvasHeight: number;
}) {
  const at = useDerivedValue(() => {
    const point = trajectoryPointAt(track, progress.value);
    return { x: point.px, y: point.py };
  });

  return (
    <>
      {/* Only the arrows this scene uses get a per-frame path. */}
      {arrows.map((kind) => (
        <DerivedArrow
          key={kind}
          kind={kind}
          at={at}
          track={track}
          closed={closed}
          maxSpeed={maxSpeed}
          radius={radius}
          boxAngle={boxAngle}
          centre={centre}
          slope={slope}
          floorY={floorY}
          obstacles={obstacles}
          progress={progress}
          color={kind === "velocity" ? color : theme.textSecondary}
          canvasWidth={canvasWidth}
          canvasHeight={canvasHeight}
        />
      ))}
      <BodyShape at={at} radius={radius} boxAngle={boxAngle} color={color} halo={theme.bg} />
    </>
  );
}
