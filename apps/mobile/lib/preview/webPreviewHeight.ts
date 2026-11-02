/**
 * Height policy for a WebView preview card (a Vega chart, a Mermaid diagram).
 * The page reports its drawn height; the card grows toward it but never
 * shrinks after first paint, so the reply does not jump, and stays between the
 * placeholder height and the active cap (taller once the user expands it).
 */
type PreviewHeightPolicy = {
  /** Also the placeholder until the page reports its size. */
  min: number;
  max: number;
  /** The cap once expanded; the WebView scrolls if the page is still taller. */
  maxExpanded: number;
  /** Ignore sub-pixel / font-settle chatter so the chat list doesn't bounce. */
  epsilon: number;
};

export type PreviewHeightRules = {
  policy: PreviewHeightPolicy;
  clamp: (reported: number, maxHeight: number) => number;
  /** The next height for a fresh report, or `null` when it should not change (grow-only). */
  next: (reported: number, current: number, maxHeight: number) => number | null;
  /** True when the page is taller than the visible WebView (expand can grow it). */
  isClipped: (reportedHeight: number, visibleHeight: number) => boolean;
  /** Height to apply when toggling expand — the raw page size, not the clamped one. */
  toggled: (reportedHeight: number, expanded: boolean) => number;
};

export function previewHeightRules(policy: PreviewHeightPolicy): PreviewHeightRules {
  const clamp = (reported: number, maxHeight: number): number => {
    if (!Number.isFinite(reported) || reported <= 0) return policy.min;
    return Math.min(maxHeight, Math.max(policy.min, Math.ceil(reported)));
  };
  return {
    policy,
    clamp,
    next: (reported, current, maxHeight) => {
      const next = clamp(reported, maxHeight);
      if (next <= current + policy.epsilon) return null;
      return next;
    },
    isClipped: (reportedHeight, visibleHeight) => reportedHeight > visibleHeight + policy.epsilon,
    toggled: (reportedHeight, expanded) =>
      clamp(reportedHeight, expanded ? policy.maxExpanded : policy.max),
  };
}
