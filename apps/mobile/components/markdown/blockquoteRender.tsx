import { Children, type ReactNode } from "react";
import { View } from "react-native";

import {
  blockquoteCitation,
  type AstNode,
} from "@/components/markdown/markdownAstHelpers";
import { QuoteBlock } from "@/components/rich/QuoteBlock";
import { PARAGRAPH_GAP, TRIM_TRAILING_GAP } from "@/components/markdown/markdownContentStyles";
import { Space } from "@/lib/space";
import { useTheme } from "@/lib/theme";

// Ordinary indented prose (a citation is the quote card): the block rhythm and
// a neutral rule, so the indent reads as a quote at a glance. The rule is
// textDisabled (~3.2:1 on the light page, ~4.6:1 on the dark one); `border`
// at 2pt was 1.4:1 and vanished. The text takes the quieter ink in the render
// rules (`quoteText`).
const indentedProse = {
  marginTop: 0,
  marginBottom: PARAGRAPH_GAP,
  paddingLeft: Space.sm,
  borderLeftWidth: 3,
};

/** Quote card for a citation; every other blockquote is indented prose. */
export function renderBlockquote(node: AstNode, children: ReactNode): ReactNode {
  const citation = blockquoteCitation(node);
  if (citation) {
    return (
      <QuoteBlock
        key={node.key}
        author={citation.author ?? undefined}
        testID="quote-card"
      >
        {Children.toArray(children).slice(0, citation.bodyCount)}
      </QuoteBlock>
    );
  }
  return (
    <IndentedProse key={node.key}>{children}</IndentedProse>
  );
}

function IndentedProse({ children }: { children: ReactNode }) {
  const t = useTheme();
  return (
    <View testID="indented-prose" style={[indentedProse, { borderLeftColor: t.textDisabled }]}>
      <View style={TRIM_TRAILING_GAP}>{children}</View>
    </View>
  );
}
