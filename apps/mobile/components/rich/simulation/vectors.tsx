/** The scene's arrows: the vectors the solver states and the arrows a body carries. */
import { useMemo, type ComponentProps } from "react";
import { DashPathEffect, Path, Skia } from "@shopify/react-native-skia";
import { useDerivedValue, type SharedValue } from "react-native-reanimated";

import {
  arrowHeadSize,
  derivedArrowGeometry,
  riddenVectorGeometry,
  tangentAt,
  vectorStroke,
  type inclineDirections,
  type ScreenPoint,
  type SimulationArrow,
  type VectorLayout,
} from "@/lib/physics/simulation";
import { trajectoryPointAt } from "@/lib/math/trajectory";
import type { Theme } from "@/lib/theme";
import type { Rect } from "@/components/rich/simulation/paths";
import {
  appendArrowHead,
  arrowHeadPath,
  arrowPath,
  arrowShaftPath,
} from "@/components/rich/skia/paths";

export const ARROW_STROKE = 1.5;
export const RESULT_STROKE = 2.5;

export type Slope = ReturnType<typeof inclineDirections>;
export type Wheel = { cx: number; cy: number; radius: number } | null;

export function vectorColor(role: VectorLayout["vector"]["role"], theme: Theme): string {
  // Motion shares the velocity arrow's colour family; the answer is primary.
  return role === "result" || role === "motion" ? theme.primary : theme.textSecondary;
}

/** How a stated vector is painted for its role: its stroke kind, colour and width. */
function vectorPaint(role: VectorLayout["vector"]["role"], theme: Theme) {
  return {
    stroke: vectorStroke(role),
    color: vectorColor(role, theme),
    strokeWidth: role === "result" ? RESULT_STROKE : ARROW_STROKE,
  };
}

type PathProp = ComponentProps<typeof Path>["path"];

/**
 * A stated vector's marks. A force is one arrow, stroked and filled (`shaft`
 * holds the whole arrow); motion and a measure are a dashed shaft with a
 * solid `head`, since dashing the head would break it up.
 */
function VectorMarks({
  stroke,
  color,
  strokeWidth,
  shaft,
  head,
}: ReturnType<typeof vectorPaint> & { shaft: PathProp; head: PathProp }) {
  if (stroke === "force") {
    return (
      <>
        <Path
          path={shaft}
          color={color}
          style="stroke"
          strokeWidth={strokeWidth}
          strokeJoin="round"
          strokeCap="round"
        />
        <Path path={shaft} color={color} style="fill" />
      </>
    );
  }
  return (
    <>
      <Path path={shaft} color={color} style="stroke" strokeWidth={strokeWidth}>
        <DashPathEffect intervals={stroke === "motion" ? [5, 3] : [3, 3]} />
      </Path>
      <Path
        path={head}
        color={color}
        style="stroke"
        strokeWidth={strokeWidth}
        strokeJoin="round"
        strokeCap="round"
      />
    </>
  );
}

/** A riding vector this frame: started where its body has carried it, refitted. */
export function ridingNow(
  layout: VectorLayout,
  track: ScreenPoint[],
  progress: number,
  wheel: Wheel,
  canvasWidth: number,
  canvasHeight: number,
) {
  "worklet";
  const ride = layout.ride;
  if (!ride) return null;
  const now = trajectoryPointAt(track, progress);
  const fromX = layout.from.px + now.px - track[0].px;
  const fromY = layout.from.py + now.py - track[0].py;
  const fit = riddenVectorGeometry(
    fromX,
    fromY,
    ride.ux,
    ride.uy,
    ride.desired,
    canvasWidth,
    canvasHeight,
    wheel,
  );
  return fit ? { fromX, fromY, ux: ride.ux, uy: ride.uy, length: fit.length } : null;
}

/** A stated vector riding on a moving body: the tension on an Atwood mass goes where it goes. */
export function RidingVector({
  layout,
  track,
  progress,
  wheel,
  theme,
  canvasWidth,
  canvasHeight,
}: {
  layout: VectorLayout;
  track: ScreenPoint[];
  progress: SharedValue<number>;
  wheel: Wheel;
  theme: Theme;
  canvasWidth: number;
  canvasHeight: number;
}) {
  const paint = vectorPaint(layout.vector.role, theme);
  const { stroke } = paint;
  const shaft = useDerivedValue(() => {
    const path = Skia.Path.Make();
    const arrow = ridingNow(layout, track, progress.value, wheel, canvasWidth, canvasHeight);
    if (!arrow) return path;
    if (stroke === "force") {
      return arrowPath(
        arrow.fromX,
        arrow.fromY,
        arrow.ux,
        arrow.uy,
        arrow.length,
        arrowHeadSize(arrow.length),
        "filled",
      );
    }
    path.moveTo(arrow.fromX, arrow.fromY);
    path.lineTo(arrow.fromX + arrow.ux * arrow.length, arrow.fromY + arrow.uy * arrow.length);
    return path;
  });
  const head = useDerivedValue(() => {
    const path = Skia.Path.Make();
    const arrow = ridingNow(layout, track, progress.value, wheel, canvasWidth, canvasHeight);
    if (!arrow || stroke === "force") return path;
    return appendArrowHead(
      path,
      arrow.fromX + arrow.ux * arrow.length,
      arrow.fromY + arrow.uy * arrow.length,
      arrow.ux,
      arrow.uy,
      arrowHeadSize(arrow.length),
      stroke === "motion" ? "open" : "ticks",
      arrow.length,
    );
  });
  return <VectorMarks {...paint} shaft={shaft} head={head} />;
}

export type ArrowContext = {
  track: ScreenPoint[];
  closed: boolean;
  maxSpeed: number;
  radius: number;
  boxAngle: number | null;
  centre: ScreenPoint | null;
  slope: Slope | null;
  floorY: number | null;
  obstacles: Rect[];
  canvasWidth: number;
  canvasHeight: number;
};

export function arrowNow(
  kind: SimulationArrow,
  at: ScreenPoint,
  progress: number,
  context: ArrowContext,
) {
  "worklet";
  return derivedArrowGeometry(kind, at, context.radius, {
    tangent:
      kind === "velocity" ? tangentAt(context.track, progress, context.closed) : { dx: 0, dy: 0 },
    maxSpeed: context.maxSpeed,
    centre: context.centre,
    slope: context.slope,
    width: context.canvasWidth,
    height: context.canvasHeight,
    boxAngle: context.boxAngle,
    floorY: context.floorY,
    solids: context.obstacles,
  });
}

export function DerivedArrow({
  kind,
  at,
  progress,
  color,
  ...context
}: {
  kind: SimulationArrow;
  /** The body's centre this frame, shared with the body's disc. */
  at: SharedValue<{ x: number; y: number }>;
  progress: SharedValue<number>;
  color: string;
} & ArrowContext) {
  const head = kind === "velocity" ? "open" : "filled";
  const path = useDerivedValue(() => {
    const arrow = arrowNow(kind, { px: at.value.x, py: at.value.y }, progress.value, context);
    if (!arrow) return Skia.Path.Make();
    return arrowPath(
      arrow.fromX,
      arrow.fromY,
      arrow.ux,
      arrow.uy,
      arrow.length,
      arrowHeadSize(arrow.length),
      head,
    );
  });
  return (
    <>
      <Path
        path={path}
        color={color}
        style="stroke"
        strokeWidth={ARROW_STROKE}
        strokeJoin="round"
        strokeCap="round"
      />
      {head === "filled" ? <Path path={path} color={color} style="fill" /> : null}
    </>
  );
}

export function StatedVector({ layout, theme }: { layout: VectorLayout; theme: Theme }) {
  const paint = vectorPaint(layout.vector.role, theme);
  const { stroke } = paint;
  const paths = useMemo(() => {
    const { from, tip, head } = layout;
    const length = Math.hypot(tip.px - from.px, tip.py - from.py);
    if (!(length > 0)) return null;
    const ux = (tip.px - from.px) / length;
    const uy = (tip.py - from.py) / length;
    if (stroke === "force") {
      return { solid: true as const, whole: arrowPath(from.px, from.py, ux, uy, length, head, "filled") };
    }
    // A dashed shaft with a solid end: dashing the head would break it up.
    return {
      solid: false as const,
      shaft: arrowShaftPath(from.px, from.py, ux, uy, length),
      head: arrowHeadPath(from.px, from.py, ux, uy, length, head, stroke === "motion" ? "open" : "ticks"),
    };
  }, [layout, stroke]);
  if (!paths) return null;
  return paths.solid ? (
    <VectorMarks {...paint} shaft={paths.whole} head={paths.whole} />
  ) : (
    <VectorMarks {...paint} shaft={paths.shaft} head={paths.head} />
  );
}
