/**
 * Canvas text with a halo: the same string stroked in the background colour
 * first, then filled. A track, slope or arrow running behind a label is then
 * interrupted around it instead of striking it through.
 *
 * With `fallbacks`, a character the main font cannot draw (Greek in the
 * figures' monospace face) is set in the first fallback that can.
 */
import { useMemo, type ComponentProps } from "react";
import { Group, Text as SkiaText, type SkFont } from "@shopify/react-native-skia";
import { useDerivedValue } from "react-native-reanimated";

import { fontRuns, needsFallback } from "@/components/rich/skia/fontRuns";

const HALO_WIDTH = 3;

type Coordinate = ComponentProps<typeof SkiaText>["x"];

type Props = {
  x: Coordinate;
  y: Coordinate;
  text: string;
  font: SkFont;
  color: string;
  /** The surface behind the canvas (`theme.bg`). */
  halo: string;
  /** Fonts tried, in order, for characters `font` has no glyph for. */
  fallbacks?: readonly (SkFont | null)[];
};

export function HaloText({ fallbacks, ...props }: Props) {
  const fonts = useMemo(
    () => [props.font, ...(fallbacks ?? []).filter((font): font is SkFont => font !== null)],
    [fallbacks, props.font],
  );
  const split = useMemo(
    () => fonts.length > 1 && needsFallback(props.text, fonts),
    [fonts, props.text],
  );
  return split ? <HaloRuns {...props} fonts={fonts} /> : <HaloLine {...props} />;
}

function HaloLine({ x, y, text, font, color, halo }: Omit<Props, "fallbacks">) {
  return (
    <>
      <SkiaText
        x={x}
        y={y}
        text={text}
        font={font}
        color={halo}
        style="stroke"
        strokeWidth={HALO_WIDTH}
        strokeJoin="round"
      />
      <SkiaText x={x} y={y} text={text} font={font} color={color} />
    </>
  );
}

function HaloRuns({
  x,
  y,
  text,
  color,
  halo,
  fonts,
}: Omit<Props, "fallbacks"> & { fonts: readonly SkFont[] }) {
  const runs = useMemo(() => fontRuns(text, fonts), [fonts, text]);
  // The runs are set from the label's origin, wherever that is this frame.
  const transform = useDerivedValue(() => {
    const left = typeof x === "number" ? x : (x as { value: number }).value;
    const baseline = typeof y === "number" ? y : (y as { value: number }).value;
    return [{ translateX: left }, { translateY: baseline }];
  });
  return (
    <Group transform={transform}>
      {runs.map((run, index) => (
        <SkiaText
          key={`halo-${index}`}
          x={run.dx}
          y={0}
          text={run.text}
          font={run.font}
          color={halo}
          style="stroke"
          strokeWidth={HALO_WIDTH}
          strokeJoin="round"
        />
      ))}
      {runs.map((run, index) => (
        <SkiaText
          key={`text-${index}`}
          x={run.dx}
          y={0}
          text={run.text}
          font={run.font}
          color={color}
        />
      ))}
    </Group>
  );
}
