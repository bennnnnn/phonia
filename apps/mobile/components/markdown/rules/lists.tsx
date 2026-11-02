import { memo, ReactNode } from "react";
import { PixelRatio, Text, View, type ViewStyle } from "react-native";

import { Icon } from "@/ui/icons/Icon";
import {
  astSource,
  type AstNode,
  type AstParent,
  bulletDiscMetrics,
  immediateAncestorType,
  isLastListItem,
  isLastRootBlock,
  listItemDisplayNumber,
  listItemHasNestedList,
  listHasOpenTask,
  listItemOpensWithTitle,
  listLargestNumber,
  numberColumnWidth,
  parentHasType,
  shouldNumberListItem,
  taskChecked,
} from "@/components/markdown/markdownAstHelpers";
import {
  verifyCheckStyles,
  type MdMathStyles,
  type StyleMap,
} from "@/components/markdown/markdownContentStyles";
import { VerifyCheckmark } from "@/components/markdown/VerifyCheckmark";
import { Space } from "@/lib/space";
import type { Theme } from "@/lib/theme";
import { IconSize } from "@/ui/icons/sizes";

/** The list disc's size and drop at the reader's text size. */
function bulletDiscStyle(): ViewStyle {
  const { size, top } = bulletDiscMetrics(PixelRatio.getFontScale());
  return { width: size, height: size, marginTop: top };
}

/** A list's end: no gap under it, its last item flush. */
const OPEN_LIST_END = { marginBottom: 0 };

type ListItemNode = AstNode & { index: number; markup?: string };

/**
 * What a list item is drawn from: its own AST, what its list says about it
 * (its number, the number column, being last or going on in the next piece,
 * an open task beside it), the kinds of block above it and the text size.
 * Null inside a blockquote, whose text style reads the whole quote.
 */
function listItemSource(node: ListItemNode, parent: AstParent[], goesOn: boolean): string | null {
  if (parent.some((ancestor) => ancestor.type === "blockquote")) return null;
  const fontScale = PixelRatio.getFontScale();
  return [
    parent.map((ancestor) => ancestor.type).join(">"),
    node.index,
    isLastListItem(parent, node.index),
    goesOn,
    listItemDisplayNumber(parent, node.index),
    numberColumnWidth(listLargestNumber(parent), fontScale),
    listHasOpenTask(parent),
    fontScale,
    astSource(node),
  ].join("|");
}

type DrawnListItemProps = { source: string | null; drawnWith: object; children: ReactNode };

/**
 * A list item drawn again only when what it is drawn from changes. A list a
 * streaming reply cannot cut yet (a numbered list before item 11) is parsed
 * again on every flush; its finished items stay as they were drawn.
 */
const DrawnListItem = memo(
  function DrawnListItem({ children }: DrawnListItemProps) {
    return children;
  },
  (prev, next) => next.source != null && prev.source === next.source && prev.drawnWith === next.drawnWith,
);

/**
 * `continuesBelow`: this markdown is one piece of a streaming reply cut
 * between two items of a list (lib/markdown/streamBlocks.ts). The list that
 * ends the piece goes on in the next piece, so it is drawn without its end
 * (its last item keeps the item gap, the list adds none), and the two pieces
 * read as the one list they are.
 */
export function listRules(t: Theme, mdMath: MdMathStyles, continuesBelow = false) {
  const listGoesOn = (list: unknown, ancestors: unknown[]) =>
    continuesBelow && isLastRootBlock(list, ancestors);
  const rules = {
    list_item: (
      node: ListItemNode,
      children: ReactNode,
      parent: AstParent[],
      styles: StyleMap,
    ) => {
      const task = taskChecked(node);
      const itemStyle = [
        styles._VIEW_SAFE_list_item as object,
        isLastListItem(parent, node.index) &&
          !listGoesOn(parent[0], parent.slice(1)) &&
          (styles.lastListItem as object),
      ];
      if (parentHasType(parent, "bullet_list") && task !== null) {
        if (task && !listHasOpenTask(parent)) {
          return (
            <View key={node.key} style={itemStyle}>
              <View
                style={[mdMath.listBullet, bulletDiscStyle()]}
                accessible={false}
              />
              <View style={verifyCheckStyles.verifyRow}>
                <View style={verifyCheckStyles.verifyContent}>{children}</View>
                <VerifyCheckmark />
              </View>
            </View>
          );
        }
        // A checklist item: an empty box, or a ticked one once done.
        return (
          <View
            key={node.key}
            style={itemStyle}
            accessible
            accessibilityRole="checkbox"
            accessibilityState={{ checked: task }}
          >
            <Icon
              name={task ? "select" : "square"}
              size={IconSize.sm}
              color={task ? t.success : t.textTertiary}
              style={{ marginTop: 2, marginRight: Space.xs }}
              testID={task ? "md-task-done" : "md-task-open"}
            />
            <View style={styles._VIEW_SAFE_bullet_list_content as object}>
              {children}
            </View>
          </View>
        );
      }
      if (shouldNumberListItem(parent)) {
        const markup =
          immediateAncestorType(parent) === "ordered_list"
            ? (node.markup ?? ".")
            : ".";
        return (
          <View key={node.key} style={itemStyle}>
            <Text
              style={[
                styles.ordered_list_icon as object,
                {
                  minWidth: numberColumnWidth(
                    listLargestNumber(parent),
                    PixelRatio.getFontScale(),
                  ),
                },
                // "1. Read widely" is one heading: the number takes the title's weight.
                listItemOpensWithTitle(node) && (styles.strong as object),
              ]}
            >
              {listItemDisplayNumber(parent, node.index)}
              {markup}
            </Text>
            <View
              style={[
                mdMath.listContent,
                // Last, so a sent bubble's sizing (compactMdStyles) wins over the flex column.
                styles._VIEW_SAFE_ordered_list_content as object,
              ]}
            >
              {children}
            </View>
          </View>
        );
      }
      if (immediateAncestorType(parent) === "bullet_list") {
        return (
          <View key={node.key} style={itemStyle}>
            {listItemHasNestedList(node) ? (
              // No disc on a parent topic, but keep its column: the label lines
              // up with its siblings' text and the sub-bullets indent under it.
              <View
                style={[
                  mdMath.listBullet,
                  bulletDiscStyle(),
                  mdMath.listBulletSpacer,
                ]}
                accessible={false}
                testID="md-list-bullet-spacer"
              />
            ) : (
              <View
                style={[mdMath.listBullet, bulletDiscStyle()]}
                accessible={false}
                testID="md-list-bullet"
              />
            )}
            <View
              style={[
                mdMath.listContent,
                // Last, so a sent bubble's sizing (compactMdStyles) wins over the flex column.
                styles._VIEW_SAFE_bullet_list_content as object,
              ]}
            >
              {children}
            </View>
          </View>
        );
      }
      return (
        <View key={node.key} style={itemStyle}>
          {children}
        </View>
      );
    },
    bullet_list: (
      node: AstNode,
      children: ReactNode,
      parent: unknown[],
      styles: StyleMap,
    ) => (
      <View
        key={node.key}
        testID="md-bullet-list"
        style={[
          styles._VIEW_SAFE_bullet_list as object,
          parentHasType(parent, "list_item") && (styles.nestedList as object),
          listGoesOn(node, parent) && OPEN_LIST_END,
        ]}
      >
        {children}
      </View>
    ),
    ordered_list: (
      node: AstNode,
      children: ReactNode,
      parent: unknown[],
      styles: StyleMap,
    ) => (
      <View
        key={node.key}
        testID="md-ordered-list"
        style={[
          styles._VIEW_SAFE_ordered_list as object,
          parentHasType(parent, "list_item") && (styles.nestedList as object),
          listGoesOn(node, parent) && OPEN_LIST_END,
        ]}
      >
        {children}
      </View>
    ),
  };
  return {
    ...rules,
    list_item: (node: ListItemNode, children: ReactNode, parent: AstParent[], styles: StyleMap) => (
      <DrawnListItem
        key={node.key}
        source={listItemSource(node, parent, listGoesOn(parent[0], parent.slice(1)))}
        drawnWith={styles}
      >
        {rules.list_item(node, children, parent, styles)}
      </DrawnListItem>
    ),
  };
}
