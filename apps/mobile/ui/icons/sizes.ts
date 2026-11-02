/**
 * Icon size ladder. Chrome, rows, and buttons use these; domain graphics may
 * keep other pixel sizes. Kept out of the drawings so Node tests can import it.
 */
export const IconSize = {
  /** 14 — marks inside dense chips and badges */
  xxs: 14,
  /** 16 — inline with caption / meta text */
  xs: 16,
  /** 20 — list rows, message actions, compact buttons */
  sm: 20,
  /** 24 — menus, headers, primary chrome */
  md: 24,
  /** 28 — prominent single actions */
  lg: 28,
  /** 40 — empty states and feature heroes */
  xl: 40,
  /** 56 — onboarding and full-screen empty states */
  hero: 56,
} as const;

/**
 * On-screen stroke in points. Every row and chrome icon draws the same line
 * weight whatever its size, instead of thinning as it shrinks. 1.5 matches a
 * light line icon; tiny and hero sizes step down so they do not look heavy.
 */
export function iconStroke(size: number): number {
  return size <= IconSize.xs || size >= IconSize.xl ? 1.25 : 1.5;
}
