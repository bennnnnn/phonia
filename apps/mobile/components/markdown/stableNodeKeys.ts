import type { RenderRules } from "react-native-markdown-display";

/** The fields of a react-native-markdown-display AST node a key is read from. */
type KeyedNode = { key: string; index?: number; type?: string; path?: string };
type RenderRule = (node: KeyedNode, children: unknown, parents: KeyedNode[], ...rest: unknown[]) => unknown;

/**
 * react-native-markdown-display gives every node a fresh `getUniqueID()` key
 * on each parse, so a text that re-parses (a streaming reply's live part)
 * remounts its whole subtree each time: every View, Text, maths and card is
 * created again. A node's place in the tree (its index under each ancestor)
 * is stable while the text before it is unchanged, so that path becomes its
 * key and a re-parse updates the views in place. The AST belongs to the one
 * parse, so the path is kept on its nodes.
 */
function pathOf(node: KeyedNode, parents: KeyedNode[], depth: number): string {
  if (node.path !== undefined) return node.path;
  const parent = parents[depth];
  node.path = parent ? `${pathOf(parent, parents, depth + 1)}.${node.index ?? 0}` : "0";
  return node.path;
}

/** `rules` with each node keyed by its path. */
export function withStableNodeKeys(rules: RenderRules): RenderRules {
  const keyed: Record<string, RenderRule> = {};
  for (const [type, rule] of Object.entries(rules as Record<string, RenderRule>)) {
    keyed[type] = (node, children, parents, ...rest) => {
      node.key = `${pathOf(node, parents ?? [], 0)}_${node.type ?? type}`;
      return rule(node, children, parents, ...rest);
    };
  }
  return keyed as unknown as RenderRules;
}
