/** The mark an accent draws over (or under) its body: dots, a hat, a tilde, an arrow, or a rule. */
import { type ReactNode } from "react";
import { View } from "react-native";
import Svg, { Path } from "react-native-svg";

import type { MathLayout } from "@/lib/math/layout";
import { scaled, type RenderCtx } from "@/components/rich/mathText/context";

/** The SVG path of a hat, tilde or arrow accent `w` wide and `h` tall. */
function strokedAccentPath(kind: "hat" | "vec" | "vecLeft" | "tilde", w: number, h: number): string {
  return kind === "hat"
    ? `M 0 ${h} L ${w / 2} 0 L ${w} ${h}`
    : kind === "tilde"
      ? `M 0 ${h * 0.7} Q ${w * 0.25} 0 ${w * 0.5} ${h * 0.55} T ${w} ${h * 0.2}`
      : kind === "vecLeft"
        ? `M ${w} ${h * 0.5} L 0 ${h * 0.5} M 0 ${h * 0.5} L ${w * 0.28} 0 M 0 ${h * 0.5} L ${w * 0.28} ${h}`
        : `M 0 ${h * 0.5} L ${w} ${h * 0.5} M ${w} ${h * 0.5} L ${w * 0.72} 0 M ${w} ${h * 0.5} L ${w * 0.72} ${h}`;
}

export function renderAccentMark(node: MathLayout, ctx: RenderCtx): ReactNode {
  const rule = scaled(node.ruleWidth ?? node.inkWidth, ctx.fontScale);
  const thick = Math.max(1, scaled(ctx.em * 0.06, ctx.fontScale));
  const kind = node.accentKind;
  if (kind === "dot" || kind === "ddot") {
    const dot = (
      <View
        testID="math-accent-rule"
        style={{ width: thick, height: thick, borderRadius: thick, backgroundColor: ctx.color }}
      />
    );
    return (
      <View style={{ flexDirection: "row", gap: thick, alignSelf: "center" }}>
        {dot}
        {kind === "ddot" ? dot : null}
      </View>
    );
  }
  if (kind === "hat" || kind === "vec" || kind === "vecLeft" || kind === "tilde") {
    const w = rule;
    const h = scaled(ctx.em * 0.18, ctx.fontScale);
    const d = strokedAccentPath(kind, w, h);
    return (
      <Svg testID="math-accent-rule" width={w} height={h} viewBox={`0 0 ${Math.max(w, 1)} ${Math.max(h, 1)}`}>
        <Path d={d} fill="none" stroke={ctx.color} strokeWidth={Math.max(1, thick * 0.8)} strokeLinecap="round" />
      </Svg>
    );
  }
  return (
    <View
      testID="math-accent-rule"
      style={{ width: rule, height: thick, backgroundColor: ctx.color, alignSelf: "center" }}
    />
  );
}
