import { memo, useId } from "react";
import { View, type StyleProp, type ViewStyle } from "react-native";
import Svg, { Circle, Ellipse, Line, Path, Polygon, Polyline, Rect } from "react-native-svg";

import { useTheme } from "@/lib/theme";

import { CUSTOM_GLYPHS, type CustomGlyph } from "./custom";
import { GLYPHS, type GlyphNode, type LucideIconName } from "./glyphs.generated";
import type { IconName } from "./names";
import { IconSize, iconStroke } from "./sizes";

const ELEMENTS = {
  path: Path,
  circle: Circle,
  line: Line,
  rect: Rect,
  polyline: Polyline,
  polygon: Polygon,
  ellipse: Ellipse,
} as const;

type Props = {
  name: IconName;
  /** Pixel size. Defaults to `IconSize.sm` (20). */
  size?: number;
  /** Explicit ink. Omit for the theme text color. */
  color?: string;
  /** Use the danger ink (red) instead of the default. */
  danger?: boolean;
  /**
   * Fill the closed shapes (active state: a pressed thumbs-up, a saved
   * bookmark, a playing speaker). Open strokes stay lines.
   */
  filled?: boolean;
  /** Line weight in on-screen points. Defaults to the shared weight for this size. */
  strokeWidth?: number;
  style?: StyleProp<ViewStyle>;
  testID?: string;
};

function isClosed(tag: GlyphNode[0], attrs: Readonly<Record<string, string>>): boolean {
  if (tag === "path") return /z\s*$/i.test(attrs.d ?? "");
  return tag === "rect" || tag === "circle" || tag === "ellipse" || tag === "polygon";
}

/**
 * The app's one icon: rounded line drawings at a single stroke weight, in
 * the style of the ChatGPT menus. Decorative — the pressable around it owns
 * the accessibility label (an SVG view is never focusable on its own).
 */
export const Icon = memo(function Icon({
  name,
  size = IconSize.sm,
  color,
  danger = false,
  filled = false,
  strokeWidth,
  style,
  testID,
}: Props) {
  const theme = useTheme();
  const ink = color ?? (danger ? theme.danger : theme.text);
  const unitStroke = ((strokeWidth ?? iconStroke(size)) * 24) / size;
  const maskId = `icon-mask-${useId().replace(/[^A-Za-z0-9]/g, "")}`;
  const custom: CustomGlyph | undefined = (CUSTOM_GLYPHS as Partial<Record<string, CustomGlyph>>)[name];
  const nodes = custom ? null : (GLYPHS[name as LucideIconName] as readonly GlyphNode[]);

  return (
    <View
      style={[{ width: size, height: size }, style]}
      testID={testID}
      pointerEvents="none"
      // Exposed for tests: which glyph, at what size, in what ink.
      {...({ name, size, color: ink } as object)}
    >
      <Svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        stroke={ink}
        strokeWidth={unitStroke}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {custom
          ? custom({ color: ink, strokeWidth: unitStroke, maskId })
          : nodes?.map(([tag, attrs], index) => {
              const Element = ELEMENTS[tag];
              return (
                <Element
                  key={index}
                  {...attrs}
                  fill={filled && isClosed(tag, attrs) ? ink : "none"}
                />
              );
            })}
      </Svg>
    </View>
  );
});
