/**
 * Shared spacing scale (4pt base). Prefer these over one-off 6/10/14 mixes
 * for the same layout role. Full app migration is incremental.
 */
export const Space = {
  /** 4 — hair gaps, icon hit padding */
  xxs: 4,
  /** 8 — tight stacks, compact padding */
  xs: 8,
  /** 12 — control padding, list gaps */
  sm: 12,
  /** 16 — screen gutters, card padding */
  md: 16,
  /** 20 — home inset, denser section gap */
  gutter: 20,
  /** 24 — section / sheet horizontal inset */
  lg: 24,
  /** 32 — large hero / empty-state breathing room */
  xl: 32,
  /** 44 — minimum interactive target (WCAG 2.5.5 / Apple HIG) */
  minTouch: 44,
} as const;
