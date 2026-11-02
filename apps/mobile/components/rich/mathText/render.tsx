/** Renders parsed math segments as native Text/View runs for MathText. */
import { type ReactNode } from "react";
import { Text, View } from "react-native";
import Svg, { Path } from "react-native-svg";

import {
  FRAC_LINE_AT_16,
  FRAC_SIZE_RATIO,
  radicalStroke,
  SCRIPT_RATIO,
  SQRT_LINE_AT_16,
  type MathLayout,
} from "@/lib/math/layout";
import { attachScripts, type MathSegment } from "@/lib/math/text";
import { renderAccentMark } from "@/components/rich/mathText/accentMark";
import {
  faceAt,
  runStyle,
  scaled,
  scriptShift,
  type RenderCtx,
} from "@/components/rich/mathText/context";
import {
  renderMathRun,
  renderNonVariableRun,
  type RunPad,
} from "@/components/rich/mathText/runs";
import {
  renderFractionalScript,
  renderScriptRun,
} from "@/components/rich/mathText/scripts";

type Segment<K extends MathSegment["type"]> = Extract<MathSegment, { type: K }>;

function isFractionalScript(seg: MathSegment): boolean {
  if (seg.type !== "sup") return false;
  const slash = seg.value.indexOf("/");
  return slash > 0 && slash < seg.value.length - 1 && !seg.value.includes(" ");
}

function hasRaisedScript(segments: MathSegment[]): boolean {
  return segments.some((seg) => seg.type === "sup" || seg.type === "sub");
}

export function hasStackedMath(segments: MathSegment[]): boolean {
  return segments.some((seg) => (
    seg.type === "frac" || seg.type === "sqrt" || seg.type === "cancel"
    || seg.type === "accent" || isFractionalScript(seg)
  ));
}

export function hasTallMath(segments: MathSegment[]): boolean {
  // A lone `x^2` used to stay inside Text, and iOS ignores translateY there,
  // so the exponent sat on the baseline and read as x2. The shift only
  // sticks when the script is a child of a View, which is how the fraction
  // in a divide step already draws it.
  return hasStackedMath(segments) || hasRaisedScript(segments);
}

/** A run inside a stack: a row of Views when it holds stacked or raised math, else one Text. */
function renderStackRow(
  segments: MathSegment[],
  layout: MathLayout | undefined,
  keyPrefix: string,
  rowCtx: RenderCtx,
  textStyle: object,
): ReactNode {
  const children = renderSegments(segments, layout?.children ?? [], keyPrefix, rowCtx);
  if (hasTallMath(segments)) {
    return <View style={rowCtx.styles.fracSideRow}>{children}</View>;
  }
  return <Text style={textStyle}>{children}</Text>;
}

function renderFracSide(
  segments: MathSegment[],
  layout: MathLayout | undefined,
  keyPrefix: string,
  ctx: RenderCtx,
): ReactNode {
  const sideEm = ctx.inFrac ? ctx.em : ctx.em * FRAC_SIZE_RATIO;
  const sized = ctx.textStyle
    ? { ...faceAt(ctx, sideEm, FRAC_LINE_AT_16 / 14), textAlign: "center" as const }
    : null;
  const sideCtx = {
    ...ctx,
    inFrac: true,
    em: sideEm,
    textStyle: sized ?? ctx.textStyle,
  };
  // Nested fraction OR a radical: keep real Views. Flattening a radicand
  // to combining overlines made the minus look like `=` and inflated the bar.
  return renderStackRow(segments, layout, keyPrefix, sideCtx, sized ?? ctx.styles.fracPart);
}

/**
 * Radicand keeps the surrounding text size. Reusing the fraction-sized side
 * renderer made `\sqrt{8}` read as a subscript, and its plain-text flattening
 * leaked scripts as literal `8^3`. Nested stacks still take the View path (a
 * View cannot live in that Text).
 */
function renderRadicand(
  segments: MathSegment[],
  layout: MathLayout | undefined,
  keyPrefix: string,
  ctx: RenderCtx,
): ReactNode {
  const { styles } = ctx;
  const bodyStyle = ctx.textStyle
    ? faceAt(ctx, ctx.em, (ctx.inFrac ? FRAC_LINE_AT_16 / 14 : SQRT_LINE_AT_16 / 16))
    : ctx.inFrac
      ? styles.fracPart
      : styles.sqrtBody;
  return renderStackRow(segments, layout, keyPrefix, { ...ctx, textStyle: bodyStyle }, bodyStyle);
}

function renderScriptColumn(
  sup: Segment<"sup">,
  sub: Segment<"sub">,
  node: MathLayout | undefined,
  key: string,
  ctx: RenderCtx,
): ReactNode {
  const pad = { em: ctx.em, fontScale: ctx.fontScale, leadingAtom: true };
  return (
    <View
      key={key}
      testID="math-script-column"
      style={{
        width: scaled(node?.width ?? 0, ctx.fontScale),
        height: scaled(node?.height ?? 0, ctx.fontScale),
        paddingTop: scaled(node?.padTop ?? 0, ctx.fontScale),
        paddingBottom: scaled(node?.padBottom ?? 0, ctx.fontScale),
        alignItems: "center",
        justifyContent: "space-between",
      }}
    >
      {renderOneSegment(sup, node?.children[0], `${key}-sup`, ctx, pad, true)}
      {renderOneSegment(sub, node?.children[1], `${key}-sub`, ctx, pad, true)}
    </View>
  );
}

export function renderSegments(
  segments: MathSegment[],
  layouts: MathLayout[],
  keyPrefix: string,
  ctx: RenderCtx,
): ReactNode[] {
  const nodes: ReactNode[] = [];
  let leadingAtom = false;
  let layoutIndex = 0;
  for (const atom of attachScripts(segments)) {
    const key = `${keyPrefix}-${atom.index}`;
    const node = layouts[layoutIndex];
    layoutIndex += 1;
    const pad = { em: ctx.em, fontScale: ctx.fontScale, leadingAtom };
    leadingAtom = true;
    const rendered = renderOneSegment(atom.segment, node, key, ctx, pad, false);
    if (atom.sup && atom.sub) {
      const column = layouts[layoutIndex];
      layoutIndex += 1;
      nodes.push(
        <View key={key} style={{ flexDirection: "row", alignItems: "center" }}>
          {rendered}
          {renderScriptColumn(atom.sup, atom.sub, column, `${key}-col`, ctx)}
        </View>,
      );
    } else if (rendered != null) {
      nodes.push(rendered);
    }
  }
  return nodes;
}

/** A script with a body of its own (`x^{2^n}`): a View that owns its laid-out bounds. */
function renderScriptBody(
  body: MathSegment[],
  node: MathLayout | undefined,
  key: string,
  ctx: RenderCtx,
  placed: boolean,
): ReactNode {
  const scriptEm = node?.fontSize ?? ctx.em * SCRIPT_RATIO;
  const shift = scriptShift(node, ctx, placed);
  const inner = node?.children[0];
  return (
    <View
      key={key}
      testID="math-script"
      style={{
        width: scaled(node?.width ?? 0, ctx.fontScale),
        height: scaled(node?.height ?? 0, ctx.fontScale),
        paddingTop: scaled(inner?.padTop ?? 0, ctx.fontScale),
        paddingBottom: scaled(inner?.padBottom ?? 0, ctx.fontScale),
        transform: [{ translateY: shift }],
      }}
    >
      {renderSegments(body, inner?.children ?? [], `${key}-b`, {
        ...ctx,
        em: scriptEm,
        textStyle: faceAt(ctx, scriptEm, 1.15),
      })}
    </View>
  );
}

function renderScript(
  seg: Segment<"sup"> | Segment<"sub">,
  node: MathLayout | undefined,
  key: string,
  ctx: RenderCtx,
  placed: boolean,
): ReactNode {
  if (seg.body) return renderScriptBody(seg.body, node, key, ctx, placed);
  if (seg.type === "sup" && isFractionalScript(seg)) {
    return renderFractionalScript(seg.value, node, key, ctx);
  }
  return renderScriptRun(seg.value, node, key, ctx, placed);
}

function renderFrac(
  seg: Segment<"frac">,
  node: MathLayout | undefined,
  key: string,
  ctx: RenderCtx,
): ReactNode {
  const { styles } = ctx;
  return (
    <View
      key={key}
      style={[styles.fracStack, {
        width: scaled(node?.width ?? 0, ctx.fontScale),
        height: scaled(node?.height ?? 0, ctx.fontScale),
        marginHorizontal: scaled((node?.outer ?? 0) / 2, ctx.fontScale),
        paddingTop: scaled(node?.padTop ?? 0, ctx.fontScale),
        paddingBottom: scaled(node?.padBottom ?? 0, ctx.fontScale),
      }]}
      testID="math-frac"
      collapsable={false}
    >
      {renderFracSide(seg.num, node?.children[0], `${key}-n`, ctx)}
      <View
        style={[styles.vinculum, { height: Math.max(1, ctx.fontScale), marginVertical: 0 }]}
        testID="math-vinculum"
      />
      {renderFracSide(seg.den, node?.children[1], `${key}-d`, ctx)}
    </View>
  );
}

/** A root's index: a laid-out expression (`\sqrt[n+1]{x}`) or a plain degree (`\sqrt[3]{8}`). */
function renderSqrtIndex(
  seg: Segment<"sqrt">,
  node: MathLayout,
  key: string,
  ctx: RenderCtx,
): ReactNode {
  const index = node.index;
  if (!index) return null;
  if (seg.index) {
    return (
      <View
        testID="math-sqrt-index"
        style={{
          position: "absolute",
          left: scaled(index.left, ctx.fontScale),
          top: scaled(index.top, ctx.fontScale),
          width: scaled(index.width, ctx.fontScale),
          height: scaled(index.lineHeight, ctx.fontScale),
        }}
      >
        {renderSegments(seg.index, node.children[1]?.children ?? [], `${key}-i`, {
          ...ctx,
          em: index.fontSize,
          textStyle: faceAt(ctx, index.fontSize, 1.15),
        })}
      </View>
    );
  }
  if (!seg.degree) return null;
  return (
    <Text
      style={[ctx.styles.sqrtIndex, {
        left: scaled(index.left, ctx.fontScale),
        top: scaled(index.top, ctx.fontScale),
        fontSize: index.fontSize,
        lineHeight: index.lineHeight,
        transform: [],
      }]}
    >
      {seg.degree}
    </Text>
  );
}

function renderSqrt(
  seg: Segment<"sqrt">,
  node: MathLayout | undefined,
  key: string,
  ctx: RenderCtx,
): ReactNode {
  if (!node) return <View key={key} testID="math-sqrt" />;
  const { styles } = ctx;
  const stroke = radicalStroke(node);
  const width = scaled(node.width, ctx.fontScale);
  const height = scaled(node.height, ctx.fontScale);
  const padLeft = node.padLeft ?? 0;
  const padRight = Math.max(0, node.outer - padLeft);
  return (
    <View
      key={key}
      style={[styles.sqrtRow, {
        width,
        height,
        marginLeft: scaled(padLeft, ctx.fontScale),
        marginRight: scaled(padRight, ctx.fontScale),
      }]}
      testID="math-sqrt"
      collapsable={false}
    >
      <Svg
        testID="math-radical-glyph"
        width={width}
        height={height}
        viewBox={`0 0 ${node.width} ${node.height}`}
        style={styles.radicalGlyph}
        pointerEvents="none"
        accessible={false}
      >
        <Path
          d={stroke.d}
          fill="none"
          stroke={ctx.color}
          strokeWidth={Math.max(0.9, (node.em ?? ctx.em) * 0.075)}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </Svg>
      {renderSqrtIndex(seg, node, key, ctx)}
      <View
        style={[styles.sqrtRadicand, {
          marginLeft: scaled(node.lead ?? 0, ctx.fontScale),
          marginTop: scaled(node.bodyTop ?? 0, ctx.fontScale),
          width: scaled(node.children[0]?.width ?? node.bodyWidth ?? 0, ctx.fontScale),
          height: scaled(node.bodyHeight ?? 0, ctx.fontScale),
        }]}
        testID="math-sqrt-radicand"
      >
        {renderRadicand(seg.body, node.children[0], `${key}-b`, ctx)}
      </View>
    </View>
  );
}

function renderAccent(
  seg: Segment<"accent">,
  node: MathLayout | undefined,
  key: string,
  ctx: RenderCtx,
): ReactNode {
  if (!node) return <View key={key} testID="math-accent" />;
  const mark = renderAccentMark(node, ctx);
  const under = seg.kind === "underline";
  const head = under ? 0 : scaled(node.padTop ?? 0, ctx.fontScale);
  const foot = under ? scaled(node.padBottom ?? 0, ctx.fontScale) : 0;
  return (
    <View
      key={key}
      testID="math-accent"
      collapsable={false}
      style={{
        width: scaled(node.width, ctx.fontScale),
        height: scaled(node.height, ctx.fontScale),
        alignItems: "center",
        justifyContent: "flex-start",
      }}
    >
      {under ? null : mark}
      <View style={[ctx.styles.fracSideRow, { marginTop: head, marginBottom: foot }]}>
        {renderSegments(seg.body, node.children[0]?.children ?? [], `${key}-a`, ctx)}
      </View>
      {under ? mark : null}
    </View>
  );
}

function renderCancel(
  seg: Segment<"cancel">,
  node: MathLayout | undefined,
  key: string,
  ctx: RenderCtx,
): ReactNode {
  const { styles } = ctx;
  return (
    <View key={key} testID="math-cancel" style={styles.cancelWrap} collapsable={false}>
      {renderSegments(seg.body, node?.children[0]?.children ?? [], `${key}-c`, ctx)}
      <View style={styles.cancelSlashHit} pointerEvents="none" accessible={false}>
        <View testID="math-cancel-slash" style={styles.cancelSlash} />
      </View>
    </View>
  );
}

function renderOneSegment(
  seg: MathSegment,
  node: MathLayout | undefined,
  key: string,
  ctx: RenderCtx,
  pad: RunPad,
  placed: boolean,
): ReactNode {
  switch (seg.type) {
    case "sup":
    case "sub":
      return renderScript(seg, node, key, ctx, placed);
    case "frac":
      return renderFrac(seg, node, key, ctx);
    case "sqrt":
      return renderSqrt(seg, node, key, ctx);
    case "accent":
      return renderAccent(seg, node, key, ctx);
    case "cancel":
      return renderCancel(seg, node, key, ctx);
    case "upright":
      return (
        <Text key={key} style={runStyle(ctx)} testID="math-upright-run">
          {renderNonVariableRun(seg.value, `${key}-u`, ctx.styles.glyph, { em: ctx.em, fontScale: ctx.fontScale })}
        </Text>
      );
    case "text":
      return renderMathRun(seg.value, key, runStyle(ctx), ctx.styles.glyph, ctx.styles.variable, undefined, pad);
  }
}
