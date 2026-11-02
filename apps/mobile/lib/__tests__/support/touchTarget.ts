/**
 * The height of a press target as drawn at the default text size, plus its hitSlop.
 *
 * Jest lays nothing out, so this reads the styles: an explicit height or minHeight, or
 * the vertical padding around the tallest child (an icon's size, or one line of text).
 * A Source Sans 3 line is 1.424 em tall (hhea ascender 1024, descender -400, no gap,
 * 1000 units per em), the face every UI role uses.
 */
import { StyleSheet, type TextStyle, type ViewStyle } from "react-native";

const SOURCE_SANS_LINE = 1.424;

type HostNode = {
  props: Record<string, unknown>;
  children: (HostNode | string)[];
  type: unknown;
};

function flat(node: HostNode): ViewStyle & TextStyle {
  return (StyleSheet.flatten(node.props.style as ViewStyle) ?? {}) as ViewStyle & TextStyle;
}

function contentHeight(node: HostNode): number {
  let tallest = 0;
  for (const child of node.children) {
    if (typeof child === "string") continue;
    const style = flat(child);
    if (typeof style.fontSize === "number") {
      tallest = Math.max(tallest, style.lineHeight ?? style.fontSize * SOURCE_SANS_LINE);
    } else if (typeof style.height === "number") {
      tallest = Math.max(tallest, style.height);
    } else {
      tallest = Math.max(tallest, contentHeight(child));
    }
  }
  return tallest;
}

function slop(value: unknown): number {
  if (typeof value === "number") return value * 2;
  const edges = (value ?? {}) as { top?: number; bottom?: number };
  return (edges.top ?? 0) + (edges.bottom ?? 0);
}

export function touchTargetHeight(node: HostNode): number {
  const style = flat(node);
  const own = typeof style.height === "number" ? style.height : style.minHeight;
  const edge = (side: unknown) => (typeof side === "number" ? side : 0);
  const vertical =
    edge(style.paddingTop ?? style.paddingVertical ?? style.padding) +
    edge(style.paddingBottom ?? style.paddingVertical ?? style.padding);
  const drawn = typeof own === "number" ? own : vertical + contentHeight(node);
  return drawn + slop(node.props.hitSlop);
}
