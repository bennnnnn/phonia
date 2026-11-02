import { ReactNode } from "react";
import { View } from "react-native";

import {
  MarkdownTable,
  MarkdownTableCell,
  MarkdownTableHeaderCell,
  MarkdownTableRow,
} from "@/components/MarkdownTable";
import { type AstNode } from "@/components/markdown/markdownAstHelpers";
import { tableColumnText, tableRowSource } from "@/components/markdown/tableLayout";

export function tableRules() {
  return {
    table: (node: AstNode, children: ReactNode) => (
      <MarkdownTable key={node.key} nodeKey={node.key} columns={tableColumnText(node)}>
        {children}
      </MarkdownTable>
    ),
    thead: (node: { key: string }, children: ReactNode) => (
      <View key={node.key}>{children}</View>
    ),
    tbody: (node: { key: string }, children: ReactNode) => (
      <View key={node.key}>{children}</View>
    ),
    tr: (node: AstNode, children: ReactNode, parents: AstNode[], styles: object) => (
      <MarkdownTableRow
        key={node.key}
        nodeKey={node.key}
        source={tableRowSource(node, parents)}
        drawnWith={styles}
      >
        {children}
      </MarkdownTableRow>
    ),
    th: (node: { key: string }, children: ReactNode) => (
      <MarkdownTableHeaderCell key={node.key} nodeKey={node.key}>
        {children}
      </MarkdownTableHeaderCell>
    ),
    td: (node: { key: string }, children: ReactNode) => (
      <MarkdownTableCell key={node.key} nodeKey={node.key}>
        {children}
      </MarkdownTableCell>
    ),
  };
}
