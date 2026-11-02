/**
 * Height policy for the mermaid WebView preview (`lib/preview/webPreviewHeight.ts`).
 *
 * Extracted so grow/clamp is unit-testable without a linked WebView.
 */
import { previewHeightRules } from "@/lib/preview/webPreviewHeight";

/** Placeholder until the SVG reports its size. */
export const MERMAID_MIN_HEIGHT = 160;
/** Fit a typical ~8-step flowchart TD without clipping. */
export const MERMAID_MAX_HEIGHT = 640;
/** Expanded cap for tall graphs; the WebView scrolls if still taller. */
export const MERMAID_MAX_EXPANDED = 960;
/** Ignore sub-pixel / font-settle chatter so the chat list doesn't bounce. */
const MERMAID_HEIGHT_EPSILON_PX = 4;

export const MERMAID_PREVIEW_HEIGHT = previewHeightRules({
  min: MERMAID_MIN_HEIGHT,
  max: MERMAID_MAX_HEIGHT,
  maxExpanded: MERMAID_MAX_EXPANDED,
  epsilon: MERMAID_HEIGHT_EPSILON_PX,
});
