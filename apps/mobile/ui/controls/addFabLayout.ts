import { Space } from "@/lib/space";

export const FAB_SIZE = 56;

/** The FAB's distance from the bottom edge, before any keyboard lift. */
export function fabBottom(insetsBottom: number): number {
  return Math.max(insetsBottom, Space.sm) + Space.xs;
}

/** Bottom padding that keeps a list's last row clear of the add FAB. */
export function addFabClearance(insetsBottom: number): number {
  return fabBottom(insetsBottom) + FAB_SIZE + Space.md;
}
