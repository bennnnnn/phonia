import { StyleSheet, type TextStyle } from "react-native";

import { CODE_FACE } from "@/lib/fonts";
import type { Theme } from "@/lib/theme";
import { Italic, Type, Weight } from "@/lib/type";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";

/**
 * Inline code: monospace on a tinted pill, so `total` stands out from the
 * explanation around it (drawn by `InlineCode`, which pads the ends).
 *
 * The markdown-display default is a block recipe (`borderWidth: 1`,
 * `padding: 10`); those props make iOS wrap each chip onto its own line, so
 * they stay zero. 14pt SpaceMono sits inside the 16pt body line box (its
 * ascent and descent are both under Source Sans 3's at 16), so a line with
 * code is no taller than one without. The radius only shows where the code
 * is its own Text in a row; a nested span has no corners on either platform.
 */
export function inlineCodeTextStyle(t: Theme): TextStyle {
  return {
    ...Type.secondary,
    ...CODE_FACE,
    color: t.text,
    backgroundColor: t.codeInlineBg,
    borderRadius: Radius.row,
    borderWidth: 0,
    borderColor: "transparent",
    padding: 0,
    paddingHorizontal: 0,
    paddingVertical: 0,
  };
}

export const verifyCheckStyles = StyleSheet.create({
  verifyRow: {
    flex: 1,
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
  },
  verifyContent: {
    flex: 1,
    flexShrink: 1,
  },
});

/** Green verification tick badge for checked `- [x]` list items. */
export function makeVerifyCheckStyles(t: Theme) {
  return StyleSheet.create({
    badge: {
      width: 20,
      height: 20,
      borderRadius: Radius.row,
      backgroundColor: t.success,
      alignItems: "center",
      justifyContent: "center",
      marginLeft: Space.xs,
      marginTop: 2,
      flexShrink: 0,
    },
  });
}

export function makeMdMath(t: Theme) {
  return StyleSheet.create({
    listContent: {
      flex: 1,
      flexShrink: 1,
    },
    // Hosts stacked frac/sqrt Views as siblings of Text — iOS lays out a
    // View nested inside Text as 0×0 and paints the numerator over the
    // previous line. Row+wrap keeps bold/prose inline without that clip.
    inlineWrap: {
      flexDirection: "row",
      flexWrap: "wrap",
      alignItems: "center",
      alignSelf: "stretch",
    },
    // Filled disc in the body ink. A colored or gray dot reads as decoration
    // instead of a list marker. iOS used to render U+00B7, a hairline glyph.
    listBullet: {
      width: 6,
      height: 6,
      borderRadius: Radius.full,
      backgroundColor: t.text,
      // Size and drop follow the text size: see bulletDiscMetrics.
      marginTop: Space.xs,
      marginRight: Space.sm,
      marginLeft: 2,
      flexShrink: 0,
    },
    listBulletSpacer: { backgroundColor: "transparent" },
  });
}

export function makeMdTable(t: Theme) {
  return StyleSheet.create({
    cellText: { ...Type.callout, ...Weight.regular, color: t.text, flexShrink: 1 },
    // Runs inside a cell take its size and ink but keep their own face, so
    // **bold** in a cell stays bold (cellText's Regular used to win).
    cellInline: { fontSize: Type.callout.fontSize, color: t.text },
    headerText: { ...Weight.semibold, color: t.text },
    // The cell's smaller size, still in the code face (spreading the
    // compact role here used to put Source Sans back on table code).
    cellCode: {
      ...inlineCodeTextStyle(t),
      fontSize: Type.compact.fontSize,
    },
  });
}

export function makeMdImg(t: Theme) {
  return StyleSheet.create({
    image: {
      width: "100%",
      height: 200,
      borderRadius: Radius.md,
      marginVertical: Space.xs,
      backgroundColor: t.contentSurface,
    },
  });
}

/**
 * The space under every block of a reply: paragraph, list, card, code, table,
 * quote. One gap and no top margins, so the space between any two blocks is
 * the same whatever their kind. Headings add their own space above.
 */
export const PARAGRAPH_GAP = Space.sm;

/**
 * Wraps markdown blocks inside a framed container (quote bar, quote card):
 * cancels the last block's gap so the frame ends at the text and the gap
 * below belongs to the container.
 */
export const TRIM_TRAILING_GAP = { marginBottom: -PARAGRAPH_GAP } as const;

export function makeMdStyles(t: Theme) {
  return StyleSheet.create({
    body: { ...Type.body, color: t.assistantText },
    code_inline: inlineCodeTextStyle(t),
    // Custom fence renderer handles code blocks / HTML preview inline.
    fence: { marginVertical: 0, padding: 0 },
    paragraph: { marginVertical: 0 },
    // Text-only paragraph run. Do not reuse `paragraph` — markdown-display
    // mergeStyle copies flexDirection/flexWrap/width onto that key.
    paragraphRun: { marginTop: 0, marginBottom: PARAGRAPH_GAP },
    bullet_list: { marginTop: 0, marginBottom: PARAGRAPH_GAP },
    ordered_list: { marginTop: 0, marginBottom: PARAGRAPH_GAP },
    // The gap between items. The last item drops it (`lastListItem`), so the
    // list's own gap alone ends the block.
    list_item: { marginBottom: Space.xs },
    lastListItem: { marginBottom: 0 },
    // A list inside a list item: its item's gap already separates it.
    nestedList: { marginBottom: 0 },
    // A loose list's paragraphs: the item gap separates them, not a block gap.
    listParagraph: { marginBottom: 0 },
    ordered_list_icon: {
      ...Type.body,
      color: t.text,
      minWidth: 22,
      textAlign: "right",
      marginLeft: 0,
      marginRight: Space.xs,
    },
    heading1: {
      ...Type.h1,
      marginTop: Space.md,
      marginBottom: Space.xs,
      color: t.text,
      flexDirection: "row",
      flexWrap: "wrap",
      alignItems: "flex-start",
    },
    heading2: {
      ...Type.h2,
      marginTop: Space.sm,
      marginBottom: Space.xxs,
      color: t.text,
      flexDirection: "row",
      flexWrap: "wrap",
      alignItems: "flex-start",
    },
    heading3: {
      ...Type.h3,
      marginTop: Space.xs,
      marginBottom: Space.xxs,
      color: t.text,
      flexDirection: "row",
      flexWrap: "wrap",
      alignItems: "flex-start",
    },
    heading4: {
      ...Type.h4,
      marginTop: Space.xxs,
      marginBottom: Space.xxs,
      color: t.text,
      flexDirection: "row",
      flexWrap: "wrap",
      alignItems: "flex-start",
    },
    heading5: {
      ...Type.h5,
      marginTop: Space.xxs,
      marginBottom: Space.xxs,
      color: t.text,
      flexDirection: "row",
      flexWrap: "wrap",
      alignItems: "flex-start",
    },
    heading6: {
      ...Type.h6,
      marginTop: Space.xxs,
      marginBottom: Space.xxs,
      color: t.text,
      flexDirection: "row",
      flexWrap: "wrap",
      alignItems: "flex-start",
    },
    strong: { ...Weight.bold, color: t.text },
    em: { ...Italic.regular },
    blockquote: { marginVertical: 0, padding: 0, borderWidth: 0 },
    // Text of an ordinary blockquote (not a quote card): quieter than the
    // reply, same size, so the aside reads as an aside.
    quoteText: { color: t.textSecondary },
    // A hairline (between the parts of a question, or the requests of a message), with
    // the same space above (the previous block's gap) and below.
    hr: {
      backgroundColor: t.border,
      height: StyleSheet.hairlineWidth,
      marginTop: 0,
      marginBottom: PARAGRAPH_GAP,
    },
    // Underlined, so a link never depends on color alone (WCAG 1.4.1): in dark
    // mode the accent is only ~1.8:1 against body text, and Graphite is grey.
    link: { color: t.primary, textDecorationLine: "underline" },
  });
}

/**
 * A sent bubble's blocks: spaced by the container's gap instead of each
 * block's bottom margin, so the last paragraph or list adds nothing under the
 * text and the bubble's top and bottom padding match.
 */
export function compactMdStyles<T extends ReturnType<typeof makeMdStyles>>(styles: T): T {
  const blockGap = styles.paragraphRun.marginBottom;
  return {
    ...styles,
    body: { ...styles.body, gap: blockGap },
    paragraphRun: { ...styles.paragraphRun, marginBottom: 0 },
    bullet_list: { ...styles.bullet_list, marginBottom: 0 },
    ordered_list: { ...styles.ordered_list, marginBottom: 0 },
    // A sent bubble is as wide as its text. Yoga gives any positive `flex` a zero basis (an
    // explicit `flexBasis: "auto"` does not override it), so an item's text added no width:
    // the bubble fit only the numbers and "1. buy milk" showed as "1.". `flex: 0` with grow
    // and shrink sizes the text from its content and still wraps it. The library derives
    // each `_VIEW_SAFE_` key from these.
    ordered_list_content: { flex: 0, flexGrow: 1, flexShrink: 1 },
    bullet_list_content: { flex: 0, flexGrow: 1, flexShrink: 1 },
  };
}

/** The style map react-native-markdown-display hands each render rule. */
export type StyleMap = Record<string, object>;
export type MdTableStyles = ReturnType<typeof makeMdTable>;
export type MdMathStyles = ReturnType<typeof makeMdMath>;
export type MdImgStyles = ReturnType<typeof makeMdImg>;
