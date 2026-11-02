/** A rectangle in window coordinates (what `measureInWindow` reports). */
export type Rect = { x: number; y: number; width: number; height: number };

type Insets = { top: number; bottom: number; left: number; right: number };

type PopoverPlacement = {
  top: number;
  left: number;
  /** Height the card may use before its rows scroll. */
  maxHeight: number;
  /** Point inside the card nearest the anchor — the card grows from here. */
  origin: { x: number; y: number };
  side: "below" | "above" | "center";
};

/** Space kept between the card and the screen edges. */
export const POPOVER_MARGIN = 12;
/** Space between the anchor and the card. */
export const POPOVER_GAP = 6;

/**
 * Where a popover card sits next to the control (or touch point) that opened
 * it: below when it fits, otherwise above, otherwise on whichever side has
 * more room with its rows scrolling. The card keeps the anchor's nearer edge
 * (a ⋮ on the right opens leftward) and never leaves the safe area. With no
 * anchor it centers, like a dialog.
 */
export function placePopover({
  anchor,
  width,
  height,
  screen,
  insets,
  margin = POPOVER_MARGIN,
  gap = POPOVER_GAP,
}: {
  anchor: Rect | null;
  width: number;
  height: number;
  screen: { width: number; height: number };
  insets: Insets;
  margin?: number;
  gap?: number;
}): PopoverPlacement {
  const minLeft = insets.left + margin;
  const maxRight = screen.width - insets.right - margin;
  const minTop = insets.top + margin;
  const maxBottom = screen.height - insets.bottom - margin;
  const cardWidth = Math.min(width, maxRight - minLeft);

  if (!anchor) {
    const maxHeight = maxBottom - minTop;
    const cardHeight = Math.min(height, maxHeight);
    return {
      left: Math.round(minLeft + (maxRight - minLeft - cardWidth) / 2),
      top: Math.round(minTop + (maxHeight - cardHeight) / 2),
      maxHeight,
      origin: { x: cardWidth / 2, y: cardHeight / 2 },
      side: "center",
    };
  }

  const anchorCenterX = anchor.x + anchor.width / 2;
  const opensLeftward = anchorCenterX > screen.width / 2;
  const preferredLeft = opensLeftward ? anchor.x + anchor.width - cardWidth : anchor.x;
  const left = clamp(preferredLeft, minLeft, maxRight - cardWidth);

  const belowTop = anchor.y + anchor.height + gap;
  const spaceBelow = maxBottom - belowTop;
  const aboveBottom = anchor.y - gap;
  const spaceAbove = aboveBottom - minTop;

  let side: "below" | "above";
  if (height <= spaceBelow) side = "below";
  else if (height <= spaceAbove) side = "above";
  else side = spaceBelow >= spaceAbove ? "below" : "above";

  const maxHeight = Math.max(0, side === "below" ? spaceBelow : spaceAbove);
  const cardHeight = Math.min(height, maxHeight);
  const top = side === "below" ? belowTop : aboveBottom - cardHeight;

  return {
    left: Math.round(left),
    top: Math.round(top),
    maxHeight,
    origin: {
      x: clamp(anchorCenterX - left, 0, cardWidth),
      y: side === "below" ? 0 : cardHeight,
    },
    side,
  };
}

function clamp(value: number, min: number, max: number): number {
  if (max < min) return min;
  return Math.min(Math.max(value, min), max);
}
