/** Scripts that are runs of glyphs, not laid-out bodies: `x^2`, `a_n`, and `x^{1/2}`. */
import { type ReactNode } from "react";
import { View } from "react-native";

import { MATH_FONT, mathFace } from "@/lib/fonts";
import { SCRIPT_RATIO, type MathLayout } from "@/lib/math/layout";
import {
  scaled,
  scriptTextStyle,
  type RenderCtx,
} from "@/components/rich/mathText/context";
import { renderMathRun, type RunPad } from "@/components/rich/mathText/runs";

/** A raised or dropped run (`x^2`, `a_n`), its operators unspaced. */
export function renderScriptRun(
  value: string,
  node: MathLayout | undefined,
  key: string,
  ctx: RenderCtx,
  placed: boolean,
): ReactNode {
  return renderMathRun(
    value,
    key,
    scriptTextStyle(node, ctx, placed),
    ctx.styles.glyph,
    ctx.styles.variable,
    "math-script",
    {
      em: node?.fontSize ?? ctx.em * SCRIPT_RATIO,
      fontScale: ctx.fontScale,
      leadingAtom: false,
      space: false,
    },
  );
}

/** `x^{1/2}`: a small stacked fraction in the exponent. */
export function renderFractionalScript(
  value: string,
  node: MathLayout | undefined,
  key: string,
  ctx: RenderCtx,
): ReactNode {
  const { styles } = ctx;
  const slash = value.indexOf("/");
  const scriptSize = node?.fontSize ?? ctx.em * SCRIPT_RATIO;
  const raise = node?.raise ?? ctx.em * 0.42;
  const scriptStyle = {
    ...mathFace(MATH_FONT),
    fontSize: scriptSize,
    lineHeight: scriptSize * 1.1,
    color: ctx.color,
  };
  const tight: RunPad = { em: scriptSize, fontScale: ctx.fontScale, leadingAtom: false, space: false };
  return (
    <View
      key={key}
      testID="math-fractional-sup"
      style={{
        width: scaled(node?.width ?? scriptSize * 2, ctx.fontScale),
        height: scaled(node?.height ?? scriptSize * 2, ctx.fontScale),
        paddingBottom: scaled(raise, ctx.fontScale),
        alignItems: "center",
        justifyContent: "flex-start",
      }}
    >
      {renderMathRun(
        value.slice(0, slash),
        `${key}-sn`,
        scriptStyle,
        styles.glyph,
        styles.variable,
        undefined,
        tight,
      )}
      <View
        testID="math-script-bar"
        style={[styles.vinculum, { alignSelf: "stretch", marginVertical: 0 }]}
      />
      {renderMathRun(
        value.slice(slash + 1),
        `${key}-sd`,
        scriptStyle,
        styles.glyph,
        styles.variable,
        undefined,
        tight,
      )}
    </View>
  );
}
