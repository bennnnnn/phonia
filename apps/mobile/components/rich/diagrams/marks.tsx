/** Marks the ray and wave diagrams share: measure lines, labels and plain shapes. */
import { useMemo } from "react";
import { DashPathEffect, Path, Skia, type SkFont, type SkPath } from "@shopify/react-native-skia";

import { HaloText } from "@/components/rich/skia/HaloText";
import { arrowHeadPath, arrowShaftPath } from "@/components/rich/skia/paths";
import type { LabelPlacement, MeasureLayout } from "@/lib/physics/optics";
import type { Theme } from "@/lib/theme";

const MEASURE_STROKE = 1.5;
const MEASURE_TICK = 8;

/**
 * An extent drawn at its world length: a dashed line with a cross-tick at each
 * end, the same dimension line the scenes use for an h or a d, so it never
 * reads as a force.
 */
export function MeasureLine({ layout, color }: { layout: MeasureLayout; color: string }) {
  const paths = useMemo(() => {
    const { from, to } = layout;
    const length = Math.hypot(to.px - from.px, to.py - from.py);
    if (!(length > 0)) return null;
    const ux = (to.px - from.px) / length;
    const uy = (to.py - from.py) / length;
    return {
      shaft: arrowShaftPath(from.px, from.py, ux, uy, length),
      ticks: arrowHeadPath(from.px, from.py, ux, uy, length, MEASURE_TICK, "ticks"),
    };
  }, [layout]);
  if (!paths) return null;
  return (
    <>
      <Path path={paths.shaft} color={color} style="stroke" strokeWidth={MEASURE_STROKE}>
        <DashPathEffect intervals={[3, 3]} />
      </Path>
      <Path path={paths.ticks} color={color} style="stroke" strokeWidth={MEASURE_STROKE} strokeCap="round" />
    </>
  );
}

export function DiagramLabel({
  label,
  font,
  color,
  theme,
}: {
  label: LabelPlacement;
  font: SkFont;
  color: string;
  theme: Theme;
}) {
  return <HaloText x={label.x} y={label.y} text={label.text} font={font} color={color} halo={theme.bg} />;
}

/** A filled rectangle, built from lines so the test stub can draw it too. */
export function rectPath(x: number, y: number, width: number, height: number): SkPath {
  const path = Skia.Path.Make();
  path.moveTo(x, y);
  path.lineTo(x + width, y);
  path.lineTo(x + width, y + height);
  path.lineTo(x, y + height);
  path.close();
  return path;
}
