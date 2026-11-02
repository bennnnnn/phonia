import { StyleSheet } from "react-native";

import { MATH_FONT, MATH_SYMBOL_FONT, MATH_VARIABLE_FONT, mathFace } from "@/lib/fonts";
import { BODY_LINE_AT_16, FRAC_LINE_AT_16, SQRT_LINE_AT_16 } from "@/lib/math/layout";
import type { Theme } from "@/lib/theme";

export const makeStyles = (theme: Theme, textColor?: string, compact = false, fontSize = 16, fontScale = 1) => {
  const color = textColor ?? theme.text;
  const scale = fontSize / 16;
  const layoutScale = scale * fontScale;
  return StyleSheet.create({
    base: {
      ...mathFace(MATH_FONT),
      fontSize,
      // Match body rhythm. 28 made nested `$m$` / `$y=mx+b$` Text
      // wrap onto its own line inside list items ("Slope (" / "m" / "): 3").
      lineHeight: (compact ? SQRT_LINE_AT_16 : BODY_LINE_AT_16) * scale,
      color,
    },
    glyph: mathFace(MATH_SYMBOL_FONT),
    variable: {
      ...mathFace(MATH_VARIABLE_FONT),
      color,
    },
    inlineViewport: {
      maxWidth: "100%",
      flexGrow: 0,
      flexShrink: 1,
    },
    tallRoot: {
      flexDirection: "row",
      alignItems: "center",
      flexShrink: 0,
      overflow: "visible",
    },
    fracStack: {
      alignItems: "center",
      alignSelf: "flex-start",
      justifyContent: "space-between",
      overflow: "visible",
      flexShrink: 0,
    },
    fracSideRow: {
      flexDirection: "row",
      alignItems: "center",
    },
    fracPart: {
      ...mathFace(MATH_FONT),
      fontSize: 14 * scale,
      lineHeight: FRAC_LINE_AT_16 * scale,
      color,
      textAlign: "center",
    },
    // One SVG path draws hook, rising stroke, and bar continuously. Its height
    // is derived from the radicand, so a stacked denominator stays inside it.
    sqrtRow: {
      flexDirection: "row",
      alignItems: "flex-start",
      overflow: "visible",
    },
    sqrtIndex: {
      position: "absolute",
      left: 0,
      top: 0,
      ...mathFace(MATH_FONT),
      fontSize: 12 * scale,
      lineHeight: 14 * scale,
      color,
    },
    sqrtBody: {
      ...mathFace(MATH_FONT),
      fontSize,
      lineHeight: SQRT_LINE_AT_16 * scale,
      color,
    },
    sqrtRadicand: {
      flexDirection: "row",
      alignItems: "flex-start",
      overflow: "visible",
    },
    radicalGlyph: {
      position: "absolute",
      left: 0,
      top: 0,
    },
    vinculum: {
      alignSelf: "stretch",
      height: 1,
      marginVertical: 0,
      backgroundColor: color,
    },
    cancelWrap: {
      alignItems: "center",
      justifyContent: "center",
    },
    cancelSlashHit: {
      ...StyleSheet.absoluteFill,
      alignItems: "center",
      justifyContent: "center",
    },
    cancelSlash: {
      width: "140%",
      height: 1.5 * layoutScale,
      backgroundColor: theme.danger,
      transform: [{ rotate: "-32deg" }],
    },
  });
};

export type MathTextStyles = ReturnType<typeof makeStyles>;
