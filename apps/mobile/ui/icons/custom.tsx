import type { ReactNode } from "react";
import { Circle, Defs, Mask, Path, Rect } from "react-native-svg";

type CustomGlyphProps = {
  color: string;
  /** Stroke width in the 24-unit drawing space. */
  strokeWidth: number;
  /** Unique per rendered icon, for knockout masks. */
  maskId: string;
};

export type CustomGlyph = (props: CustomGlyphProps) => ReactNode;

/** A solid shape with a see-through mark cut out of it (not a painted-on mark). */
function knockout(shape: ReactNode, mark: ReactNode, { color, maskId }: CustomGlyphProps) {
  return (
    <>
      <Defs>
        <Mask id={maskId} maskUnits="userSpaceOnUse" x="0" y="0" width="24" height="24">
          <Rect x="0" y="0" width="24" height="24" fill="black" />
          {shape}
          {mark}
        </Mask>
      </Defs>
      <Rect
        x="0"
        y="0"
        width="24"
        height="24"
        fill={color}
        stroke="none"
        mask={`url(#${maskId})`}
      />
    </>
  );
}

/**
 * Drawings Lucide does not have, in the same 24-unit grid and line weight.
 * `menu` is the two-line mark with the shorter bottom bar; the filled circles
 * and box are selected/done states, with the tick cut out of the fill.
 */
export const CUSTOM_GLYPHS = {
  menu: ({ color, strokeWidth }) => (
    <>
      <Path d="M3.5 8.5h17" stroke={color} strokeWidth={strokeWidth} />
      <Path d="M3.5 15.5h10.5" stroke={color} strokeWidth={strokeWidth} />
    </>
  ),
  "check-circle-filled": (props) =>
    knockout(
      <Circle cx="12" cy="12" r="10" fill="white" stroke="none" />,
      <Path
        d="m8 12.25 2.75 2.75L16.25 9.25"
        fill="none"
        stroke="black"
        strokeWidth={props.strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />,
      props,
    ),
  "close-circle-filled": (props) =>
    knockout(
      <Circle cx="12" cy="12" r="10" fill="white" stroke="none" />,
      <Path
        d="M15 9l-6 6M9 9l6 6"
        fill="none"
        stroke="black"
        strokeWidth={props.strokeWidth}
        strokeLinecap="round"
      />,
      props,
    ),
  "checkbox-checked": (props) =>
    knockout(
      <Rect x="3" y="3" width="18" height="18" rx="5" fill="white" stroke="none" />,
      <Path
        d="m8 12.25 2.75 2.75L16.25 9.25"
        fill="none"
        stroke="black"
        strokeWidth={props.strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />,
      props,
    ),
  stop: ({ color }) => <Rect x="6" y="6" width="12" height="12" rx="2.5" fill={color} stroke="none" />,
} satisfies Record<string, CustomGlyph>;

export type CustomIconName = keyof typeof CUSTOM_GLYPHS;
