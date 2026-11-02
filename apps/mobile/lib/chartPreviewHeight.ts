/**
 * Height policy for the chart WebView preview (`lib/preview/webPreviewHeight.ts`).
 * Grow-only after first paint so the assistant bubble does not jump.
 */
import { previewHeightRules } from "@/lib/preview/webPreviewHeight";

/** Also the placeholder until the SVG reports its size. */
export const CHART_MIN_HEIGHT = 140;
/** Fit a 6-row horizontal bar chart plus title/axes. */
export const CHART_MAX_HEIGHT = 480;
export const CHART_MAX_EXPANDED = 800;
export const CHART_HEIGHT_EPSILON_PX = 4;

export const CHART_PREVIEW_HEIGHT = previewHeightRules({
  min: CHART_MIN_HEIGHT,
  max: CHART_MAX_HEIGHT,
  maxExpanded: CHART_MAX_EXPANDED,
  epsilon: CHART_HEIGHT_EPSILON_PX,
});
