/** An axis-aligned box in canvas pixels: left, top, width and height. */
export type Box = { x: number; y: number; width: number; height: number };

/** Whether two boxes overlap, or come within `gap` px of each other. */
export function boxesOverlap(a: Box, b: Box, gap = 0): boolean {
  return (
    a.x < b.x + b.width + gap &&
    b.x < a.x + a.width + gap &&
    a.y < b.y + b.height + gap &&
    b.y < a.y + a.height + gap
  );
}
