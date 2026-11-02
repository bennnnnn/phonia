import React from "react";
import { Text } from "react-native";
import Markdown, { type RenderRules } from "react-native-markdown-display";

import type { makeRenderRules } from "@/components/markdown/markdownRenderRules";
import type { markdownItInstance } from "@/lib/markdown/parser";

/** What every `Markdown` of one reply is drawn with. */
export type MarkdownProps = {
  style: ReturnType<typeof makeRenderRules>["mdStyles"];
  rules: RenderRules;
  markdownit: typeof markdownItInstance;
};

/*
 * The library's own defaults for two props, made once. `Markdown` builds its
 * renderer (every style flattened, the rules merged) in a memo that lists both;
 * left to their defaults they are new on every call, so the live piece built a
 * renderer again on every flush.
 */
const IMAGE_HANDLERS = [
  "data:image/png;base64",
  "data:image/gif;base64",
  "data:image/jpeg;base64",
  "https://",
  "http://",
];
const MORE_CHILDREN = <Text key="dotdotdot">...</Text>;

/**
 * One piece of a reply: a settled chunk, or the live end after the chunks. A
 * settled chunk's string never changes while the reply streams, so it parses
 * and mounts once. The live piece parses on every flush, and its nodes keep
 * their keys (`withStableNodeKeys`), so a flush updates its views instead of
 * mounting them again.
 *
 * Pieces are keyed by where they start in the prepared text: when the live
 * region is cut into a chunk, the chunk keeps the live piece's views, and when
 * the reply settles its pieces keep theirs.
 */
export const MarkdownPiece = React.memo(function MarkdownPiece({
  content,
  md,
}: {
  content: string;
  md: MarkdownProps;
}) {
  return (
    <Markdown {...md} allowedImageHandlers={IMAGE_HANDLERS} topLevelMaxExceededItem={MORE_CHILDREN}>
      {content}
    </Markdown>
  );
});
