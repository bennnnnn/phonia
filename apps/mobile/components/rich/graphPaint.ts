/**
 * Paint the graph renderers share, so a Skia graph and its SVG fallback (and
 * the full-screen explorer) draw an inequality and its axes alike.
 */

/** Inset of the plot inside a number line or inequality chart. */
export const GRAPH_CHART_PAD = 28;
/** Tick label size on the Skia graphs. */
export const GRAPH_TICK_FONT_SIZE = 11;
/** A strict inequality's boundary (`<`, `>`) is dashed: dash, gap. */
export const STRICT_BOUNDARY_DASH = [6, 5];
/** The shaded side of an inequality. */
export const INEQUALITY_REGION_OPACITY = 0.16;
