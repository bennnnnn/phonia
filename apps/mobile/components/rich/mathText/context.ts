/** What every math segment renderer reads, and the text faces derived from it. */
import { MATH_FONT, mathFace } from "@/lib/fonts";
import { SCRIPT_RATIO, type MathLayout } from "@/lib/math/layout";
import type { MathTextStyles } from "@/components/rich/mathText/styles";

export type RenderCtx = {
  styles: MathTextStyles;
  color: string;
  inFrac?: boolean;
  textStyle?: object;
  /** Device font scale only. Layout pixels are already at `em`. */
  fontScale: number;
  em: number;
};

export function scaled(px: number, fontScale: number): number {
  return px * fontScale;
}

export function runStyle(ctx: RenderCtx): object {
  if (ctx.textStyle) return ctx.textStyle;
  return ctx.inFrac ? ctx.styles.fracPart : ctx.styles.base;
}

/** Face at `em`, used when a script is smaller than the stylesheet's 16px sizes. */
export function faceAt(ctx: RenderCtx, em: number, lineOverFont: number): object {
  return {
    ...mathFace(MATH_FONT),
    fontSize: em,
    lineHeight: em * lineOverFont,
    color: ctx.color,
  };
}

/** How far a laid-out script moves off the baseline: up when raised, down when dropped. */
export function scriptShift(node: MathLayout | undefined, ctx: RenderCtx, placed: boolean): number {
  return placed
    ? 0
    : ((node?.raise ?? 0) > 0 ? -(node?.raise ?? 0) : (node?.drop ?? 0)) * ctx.fontScale;
}

export function scriptTextStyle(node: MathLayout | undefined, ctx: RenderCtx, placed = false): object {
  const fontSize = node?.fontSize ?? ctx.em * SCRIPT_RATIO;
  const shift = scriptShift(node, ctx, placed);
  return {
    ...mathFace(MATH_FONT),
    fontSize,
    lineHeight: node?.lineHeight ?? fontSize * 1.15,
    color: ctx.color,
    transform: [{ translateY: shift }],
  };
}
