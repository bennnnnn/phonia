/** Phone drawers stay ~82% wide; tablets cap so chat keeps a usable gutter. */
export const DRAWER_MAX_WIDTH = 360;
const DRAWER_WIDTH_RATIO = 0.82;

export function cappedDrawerWidth(windowWidth: number): number {
  return Math.min(windowWidth * DRAWER_WIDTH_RATIO, DRAWER_MAX_WIDTH);
}
