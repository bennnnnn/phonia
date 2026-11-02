import { Platform, type TextStyle } from "react-native";

import { Weight } from "@/lib/type";

/** Space Mono (assets/fonts/SpaceMono-Regular.ttf). Registered at launch with the other faces (`lib/appFonts.ts`). */
export const CODE_FONT = "SpaceMono";

/**
 * The code face for any text style. Ligatures off: Space Mono joins "fi"
 * and "fl" into one glyph, so `fib` read as "ﬁb" and `floor` as "ﬂoor".
 * Every code style spreads this instead of naming CODE_FONT alone.
 */
export const CODE_FACE: TextStyle = {
  fontFamily: CODE_FONT,
  fontVariant: ["no-common-ligatures"],
};

/**
 * Keep a loaded math face on Android. A parent weight of 700 makes the system
 * look up a bold file that was never registered and draw Roboto. The default
 * font padding also sits inside the line box and clips Computer Modern.
 */
export function mathFace(family: string): TextStyle {
  return {
    ...Weight.regular,
    fontFamily: family,
    ...(Platform.OS === "android" ? { includeFontPadding: false } : null),
  };
}

/**
 * KaTeX's Computer Modern faces are purpose-built for mathematical notation.
 * Main carries digits/operators; Math Italic gives variables an unmistakable
 * lowercase silhouette (notably x in large final answers).
 */
export const MATH_FONT = "KaTeX_Main";
export const MATH_VARIABLE_FONT = "KaTeX_MathItalic";
/**
 * AMS relations that KaTeX_Main does not carry (`∴`, `∵`) and the
 * double-struck capitals KaTeX draws from this face. Most relations (`≤`,
 * `∈`, `∞`) are in KaTeX_Main and must stay there.
 */
export const MATH_SYMBOL_FONT = "KaTeX_AMS";
/** Large operators (`∬ ∭ ∮`) that neither Main nor AMS carries. */
export const MATH_SIZE1_FONT = "KaTeX_Size1";
