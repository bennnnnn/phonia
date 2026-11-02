import { InlineCode } from "@/components/markdown/InlineCode";
import {
  inPlainBlockquote,
  inTableCell,
  parentHasType,
} from "@/components/markdown/markdownAstHelpers";
import type { MdTableStyles, StyleMap } from "@/components/markdown/markdownContentStyles";
import { Type } from "@/lib/type";

const HEADING_SIZES = {
  heading1: Type.h1.fontSize,
  heading2: Type.h2.fontSize,
  heading3: Type.h3.fontSize,
  heading4: Type.h4.fontSize,
  heading5: Type.h5.fontSize,
  heading6: Type.h6.fontSize,
} as const;

/** Inline code in a heading: the heading's size in the body's 14:16 ratio, not a fixed 14. */
function headingCodeSize(parent: unknown): { fontSize: number } | null {
  for (const [type, size] of Object.entries(HEADING_SIZES)) {
    if (parentHasType(parent, type)) {
      return { fontSize: Math.round((size * Type.secondary.fontSize) / Type.body.fontSize) };
    }
  }
  return null;
}

export function codeRules(mdTable: MdTableStyles, mdCodeInline: object) {
  return {
    code_inline: (
      node: { key: string; content: string },
      _children: unknown,
      parent: unknown,
      styles: StyleMap,
    ) => (
      <InlineCode
        key={node.key}
        style={[
          mdCodeInline,
          inTableCell(parent) && mdTable.cellCode,
          headingCodeSize(parent),
          inPlainBlockquote(parent) && styles.quoteText,
        ]}
      >
        {node.content}
      </InlineCode>
    ),
  };
}
