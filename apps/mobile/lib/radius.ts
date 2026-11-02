/**
 * Shared corner radii. Prefer these over one-off 10/12/14/16/999 mixes
 * for the same control role. Full app migration is incremental.
 */
export const Radius = {
  /** 4 — rows inside a rounded list group, so the group keeps the big curve */
  row: 4,
  /** 8 — tight chips, compact controls */
  xs: 8,
  /** 10 — date chips, small panels */
  sm: 10,
  /** 12 — buttons, cards, code panels (default) */
  md: 12,
  /** 14 — soft pills, menu groups */
  lg: 14,
  /** 16 — large cards / settings groups */
  xl: 16,
  /** 18 — user message bubbles */
  bubble: 18,
  /** 20 — large content cards (rich blocks, vocab card) */
  card: 20,
  /** 24 — popover menus */
  menu: 24,
  /** 28 — composer input well (chat, memory, login and onboarding fields) */
  composer: 28,
  /** 28 — sheet top corners */
  sheet: 28,
  /** 28 — centered dialogs and pickers */
  dialog: 28,
  /** Pill / fully rounded */
  full: 999,
} as const;
