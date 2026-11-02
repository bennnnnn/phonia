/**
 * A run that holds a math View is a wrapping row, and a Text in a row is one
 * box: prose after a raised exponent or a fraction could not share the
 * formula's line and jumped to the next one, leaving a gap. Here every word
 * is its own item, so the row fills like a line of text and only a display
 * formula or a line break takes a row alone.
 */
import {
  cloneElement,
  Fragment,
  isValidElement,
  type ReactElement,
  type ReactNode,
} from "react";
import {
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type TextProps as RNTextProps,
  type TextStyle,
  type ViewStyle,
} from "react-native";

import { MathText } from "@/components/rich/MathText";
import { MathBlock } from "@/components/rich/MathView";
import { latexHasNestedMathView, readableLatexFallback } from "@/lib/math/text";

/** A space between word items, as a share of the font size (a text space is about a quarter em). */
const SPACE_EM = 0.26;
const BODY_FONT_SIZE = 16;

/** The props a split word keeps from the Text it came from. */
const CARRIED_TEXT_PROPS = ["selectable", "onPress", "onLongPress", "suppressHighlighting", "accessibilityRole"] as const;

type TextProps = Pick<RNTextProps, (typeof CARRIED_TEXT_PROPS)[number]>;
type Ctx = { style: StyleProp<TextStyle>[]; props: TextProps; space: number };
type Piece =
  /** `inText`: the item may sit inside a Text (prose, or maths drawn as glyphs). */
  | { kind: "word" | "atom"; node: ReactElement; space: number; inText: boolean }
  | { kind: "block"; node: ReactElement }
  | { kind: "break" };
type Flow = { pieces: Piece[]; label: string[]; pressable: boolean };

/** A display formula: always a row of its own in a flow. */
export function DisplayRow({ latex }: { latex: string }) {
  return (
    <View testID="md-heavy-math-run" style={styles.displayRow}>
      <MathBlock latex={latex} />
    </View>
  );
}

function spaceFor(style: StyleProp<TextStyle>[]): number {
  const fontSize = StyleSheet.flatten(style).fontSize ?? BODY_FONT_SIZE;
  return Math.round(fontSize * SPACE_EM * 10) / 10;
}

/** The space after the last item; whitespace after a formula belongs to it. */
function markSpace(flow: Flow, space: number): void {
  const last = flow.pieces[flow.pieces.length - 1];
  if (last && (last.kind === "word" || last.kind === "atom")) last.space = space;
}

function addWords(text: string, ctx: Ctx, flow: Flow): void {
  flow.label.push(text);
  for (const [token] of text.matchAll(/\s+|\S+/g)) {
    if (/\s/.test(token)) {
      if (token.includes("\n")) flow.pieces.push({ kind: "break" });
      else markSpace(flow, ctx.space);
      continue;
    }
    const node = <Text style={ctx.style} {...ctx.props}>{token}</Text>;
    flow.pieces.push({ kind: "word", node, space: 0, inText: true });
  }
}

function textContext(ctx: Ctx, props: Record<string, unknown>): Ctx {
  const style = [...ctx.style, props.style as StyleProp<TextStyle>];
  const carried: Record<string, unknown> = { ...ctx.props };
  for (const name of CARRIED_TEXT_PROPS) {
    if (props[name] !== undefined) carried[name] = props[name];
  }
  return { style, props: carried as TextProps, space: spaceFor(style) };
}

/** The words of a Text kept whole (an inline code chip), for the spoken label. */
function plainText(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(plainText).join("");
  if (isValidElement(node)) return plainText((node.props as { children?: ReactNode }).children);
  return "";
}

function collect(node: ReactNode, ctx: Ctx, flow: Flow): void {
  if (node == null || typeof node === "boolean") return;
  if (typeof node === "string" || typeof node === "number") {
    addWords(String(node), ctx, flow);
    return;
  }
  if (Array.isArray(node)) {
    for (const child of node) collect(child, ctx, flow);
    return;
  }
  if (!isValidElement(node)) return;
  const props = node.props as Record<string, unknown> & { children?: ReactNode; latex?: unknown };
  const latex = typeof props.latex === "string" ? props.latex : null;
  if (node.type === Fragment || node.type === InlineFlow) {
    collect(props.children, ctx, flow);
    return;
  }
  if (node.type === DisplayRow) {
    flow.pieces.push({ kind: "block", node });
    if (latex) flow.label.push(` ${readableLatexFallback(latex)} `);
    return;
  }
  if (node.type === Text) {
    const inner = textContext(ctx, props);
    if (props.onPress || props.onLongPress) flow.pressable = true;
    // A painted chip (inline code) stays one box; its words share the fill.
    if (StyleSheet.flatten(inner.style).backgroundColor == null) {
      collect(props.children, inner, flow);
      return;
    }
  }
  const inText = node.type === Text || (node.type === MathText && latex != null && !latexHasNestedMathView(latex));
  flow.pieces.push({ kind: "atom", node, space: 0, inText });
  flow.label.push(latex ? readableLatexFallback(latex) : node.type === Text ? plainText(props.children) : "");
}

/** Items with no space between them (`(`, a formula, `).`) stay one unbreakable box. */
function units(pieces: Piece[]): Piece[][] {
  const out: Piece[][] = [];
  let current: Piece[] = [];
  const flush = () => {
    if (current.length) out.push(current);
    current = [];
  };
  for (const piece of pieces) {
    if (piece.kind === "block" || piece.kind === "break") {
      flush();
      out.push([piece]);
      continue;
    }
    current.push(piece);
    if (piece.space > 0) flush();
  }
  flush();
  return out;
}

function renderUnit(unit: Piece[], key: string): ReactNode {
  const [first] = unit;
  const last = unit[unit.length - 1];
  if (!first || !last) return null;
  if (first.kind === "block") return cloneElement(first.node, { key });
  if (first.kind === "break") return <View key={key} style={styles.lineBreak} />;
  const space = last.kind === "word" || last.kind === "atom" ? last.space : 0;
  const gap = space > 0 ? { marginRight: space } : null;
  if (unit.length === 1 && first.kind === "word") {
    const style = (first.node.props as { style?: StyleProp<TextStyle> }).style;
    return cloneElement(first.node as ReactElement<{ style?: StyleProp<TextStyle> }>, { key, style: [style, gap] });
  }
  if (unit.length === 1 && !gap && first.kind === "atom") return <Fragment key={key}>{first.node}</Fragment>;
  const items = unit.map((piece, i) => (piece.kind === "word" || piece.kind === "atom"
    ? <Fragment key={i}>{piece.node}</Fragment>
    : null));
  // `(`, a formula drawn as glyphs and `).` read as one word of Text.
  if (unit.every((piece) => (piece.kind === "word" || piece.kind === "atom") && piece.inText)) {
    return <Text key={key} style={gap}>{items}</Text>;
  }
  return <View key={key} style={[styles.unit, gap]}>{items}</View>;
}

/** A wrapping row whose words, formulas and bold runs flow like one line of text. */
export function InlineFlow({
  children,
  style,
  testID,
}: {
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
  testID?: string;
}) {
  const flow: Flow = { pieces: [], label: [], pressable: false };
  collect(children, { style: [], props: {}, space: spaceFor([]) }, flow);
  const label = flow.label.join("").replace(/\s+/g, " ").trim();
  // One element for VoiceOver, not one per word. A link keeps its own focus.
  const grouped = !flow.pressable && label.length > 0;
  return (
    <View
      testID={testID}
      style={style}
      accessible={grouped || undefined}
      accessibilityLabel={grouped ? label : undefined}
    >
      {units(flow.pieces).map((unit, i) => renderUnit(unit, `w${i}`))}
    </View>
  );
}

const styles = StyleSheet.create({
  displayRow: { width: "100%" },
  lineBreak: { width: "100%", height: 0 },
  unit: { flexDirection: "row", alignItems: "center", flexShrink: 1, maxWidth: "100%" },
});
