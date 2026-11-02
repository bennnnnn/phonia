/**
 * Two props `Markdown` takes (its propTypes and its src/index.js) that the
 * package's typings leave out. `MarkdownPiece` passes both so the renderer
 * `Markdown` memoizes is built once per piece.
 */
import type { ReactNode } from "react";

declare module "react-native-markdown-display" {
  interface MarkdownProps {
    allowedImageHandlers?: string[];
    topLevelMaxExceededItem?: ReactNode;
  }
}
