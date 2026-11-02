import { isValidElement, type ReactElement, type ReactNode } from "react";
import type { StyleProp, TextStyle } from "react-native";
import type { ASTNode, RenderRules } from "react-native-markdown-display";

type Drawn = ReactElement<{ children?: ReactNode; style?: StyleProp<TextStyle>; testID?: string }>;

/**
 * Runs one render rule the way the markdown library does, on a node holding only
 * the fields a test sets, and hands back the element the rule drew.
 */
export function runRule(
  rules: RenderRules,
  name: string,
  node: Partial<ASTNode>,
  children: ReactNode,
  parents: ASTNode[],
  styles: object,
): Drawn {
  const rule = rules[name];
  if (!rule) throw new Error(`no ${name} rule`);
  const full: ASTNode = {
    type: name, sourceType: name, key: "node", content: "", markup: "",
    tokenIndex: 0, index: 0, attributes: {}, children: [], ...node,
  };
  const drawn = rule(full, children as ReactNode[], parents, styles);
  if (!isValidElement<Drawn["props"]>(drawn)) throw new Error(`the ${name} rule drew no element`);
  return drawn;
}
