import type { ReactNode } from "react";
import { View } from "react-native";

import type { AstNode } from "@/components/markdown/markdownAstHelpers";
import type { StyleMap } from "@/components/markdown/markdownContentStyles";

const LEVELS = [1, 2, 3, 4, 5, 6] as const;

function holdsLink(node: AstNode): boolean {
  return node.type === "link" || (node.children ?? []).some(holdsLink);
}

/**
 * A reply's `#` headings, drawn as the library draws them, are headings to a
 * screen reader too, so VoiceOver's rotor and TalkBack's heading navigation
 * jump between the sections of a long answer. The heading is read as one
 * element; one that holds a link stays open, so its link can still be focused.
 */
export function headingRules() {
  const rules: Record<string, (node: AstNode, children: ReactNode, parent: unknown, styles: StyleMap) => ReactNode> = {};
  for (const level of LEVELS) {
    const type = `heading${level}`;
    rules[type] = (node, children, _parent, styles) => (
      <View
        key={node.key}
        style={styles[`_VIEW_SAFE_${type}`]}
        accessible={!holdsLink(node)}
        accessibilityRole="header"
      >
        {children}
      </View>
    );
  }
  return rules;
}
