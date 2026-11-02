/**
 * Overlay stacking for chrome (headers, composer, drawer, toasts).
 * Chart/illustration internals may keep local z-index.
 */
export const Layer = {
  /** Behind the main column (drawer open). */
  base: 0,
  /** Main column / in-flow raised bits. */
  content: 1,
  /** In-screen overlays (scanner mask, inline FABs). */
  overlay: 10,
  fab: 20,
  header: 100,
  composer: 110,
  /** Full-height composer. Still inside the chat column, under the attach sheet. */
  composerExpanded: 200,
  /**
   * In-screen sheet. Above the composer, including the expanded field.
   * The drawer is a sibling of the chat column, so its own layer still wins.
   */
  sheet: 210,
  drawer: 200,
  /** Banners and transient toasts above everything in-tree. */
  toast: 9999,
} as const;
