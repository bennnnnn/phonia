import { Fragment, ReactNode } from "react";
import { Text, type StyleProp, type TextStyle, type ViewStyle } from "react-native";

import {
  type AstNode,
  astText,
  inHeading,
  inTableCell,
  inTableHeader,
  parentHasType,
} from "@/components/markdown/markdownAstHelpers";
import type {
  MdMathStyles,
  MdTableStyles,
  StyleMap,
} from "@/components/markdown/markdownContentStyles";
import { InlineFlow } from "@/components/markdown/rules/inlineFlow";
import { markdownHasNestedMathView } from "@/lib/markdown/preprocess";
import { isHeavyInlineMath } from "@/lib/math/fenceRetag";
import { mathRunLineHeight } from "@/lib/math/text";
import { Italic } from "@/lib/type";

/**
 * Stacked frac/sqrt and raised scripts are sized Views. A Text ancestor on
 * iOS gives that View a 0×0 text attachment, and it also drops translateY
 * on a nested Text, so an exponent sits on the baseline. Use a wrapping
 * row whose words flow around the formula; keep Text when the run is only prose.
 */
export function wrapInlineChildren(
  node: AstNode,
  children: ReactNode,
  textStyle: StyleProp<TextStyle>,
  wrapStyle: StyleProp<ViewStyle>,
): React.ReactElement {
  if (markdownHasNestedMathView(astText(node)) || isHeavyInlineMath(astText(node))) {
    return (
      <InlineFlow key={node.key} testID="md-math-inline-wrap" style={wrapStyle}>
        {children}
      </InlineFlow>
    );
  }
  return (
    <Text key={node.key} style={[textStyle, { flexShrink: 1 }]} selectable>
      {children}
    </Text>
  );
}

export function inlineRules(mdTable: MdTableStyles, mdMath: MdMathStyles) {
  return {
    textgroup: (
      node: AstNode,
      children: ReactNode,
      parent: unknown,
      styles: StyleMap,
      inheritedStyles: object = {},
    ) => {
      // Tight lists (and GFM table cells / mixed headings) omit a wrapping
      // paragraph. Without one enclosing Text, Fragment-flattened children
      // (plain + **bold** / `code`) land as siblings of a column View and
      // each takes its own line — or, in a row heading, overflow off-screen.
      if (
        parentHasType(parent, "list_item") ||
        inTableCell(parent) ||
        inHeading(parent)
      ) {
        const runHeight = mathRunLineHeight(astText(node));
        return wrapInlineChildren(
          node,
          children,
          [
            styles.body,
            inheritedStyles,
            styles.text,
            inTableCell(parent) && mdTable.cellInline,
            inTableHeader(parent) && mdTable.headerText,
            runHeight != null && { lineHeight: runHeight },
            { flexShrink: 1 },
          ],
          mdMath.inlineWrap,
        );
      }
      return <Fragment key={node.key}>{children}</Fragment>;
    },
    hardbreak: (node: { key: string }, _c: unknown, _p: unknown, styles: StyleMap) => (
      <Text key={node.key} style={styles.hardbreak} selectable>
        {"\n"}
      </Text>
    ),
    softbreak: (node: { key: string }) => (
      // CommonMark softbreak is a newline in source. HTML treats it as a
      // space; RN Text treats "\n" as a hard line break — that's why list
      // items like "It's a\n**linear equation**\nin slope-intercept form"
      // stacked every phrase. Render a space so the paragraph wraps naturally.
      <Text key={node.key}> </Text>
    ),
    inline: (node: { key: string }, children: ReactNode) => (
      // Extra Text here is Text > Text > View for stacked frac (0×0 on iOS).
      // List items get their run wrapper from `textgroup`; body paragraphs
      // from `paragraph`.
      <Fragment key={node.key}>{children}</Fragment>
    ),
    span: (node: { key: string }, children: ReactNode, _p: unknown, styles: StyleMap) => (
      <Text key={node.key} style={styles.span} selectable>
        {children}
      </Text>
    ),
    html_inline: (node: { key: string; content?: string }) => {
      const html = (node.content ?? "").trim();
      if (/^<br\s*\/?>$/i.test(html)) {
        return (
          <Text key={node.key} selectable>
            {"\n"}
          </Text>
        );
      }
      return null;
    },
    strong: (
      node: AstNode,
      children: ReactNode,
      parent: unknown,
      styles: StyleMap,
    ) => wrapInlineChildren(
      node,
      children,
      [
          styles.body,
          styles.strong,
          inTableHeader(parent) && mdTable.headerText,
          // ***both***: the bold italic file, not bold drawn upright.
          parentHasType(parent, "em") && Italic.bold,
      ],
      mdMath.inlineWrap,
    ),
    em: (node: { key: string }, children: ReactNode, parent: unknown, styles: StyleMap) => (
      <Text
        key={node.key}
        style={[styles.body, styles.em, parentHasType(parent, "strong") && Italic.bold]}
        selectable
      >
        {children}
      </Text>
    ),
  };
}
