/**
 * A preview WebView (a Mermaid diagram, a chart, a SMILES drawing) hands the
 * app links: a navigation its page may not make, or a link its page posts
 * (lib/preview/previewPage.ts). One opens only right after the user's finger touched
 * that WebView.
 *
 * Nothing the page says about a tap can be trusted: script in the page can
 * post a link, click a link it made (iOS still reports "click"), or assign
 * `location`, and on Android react-native-webview 14 reports nothing about
 * what started a navigation. The touch comes from the native touch system
 * (the WebView's `onTouchStart`), which no page script can produce.
 */

/**
 * How long after the finger lands a link may still open: the tap itself, the
 * page's click event and the bridge back to the app, on a busy JS thread.
 */
export const PREVIEW_TAP_WINDOW_MS = 2000;

export type PreviewTapGate = {
  /** The WebView's `onTouchStart`: the user's finger landed on it. */
  touched: () => void;
  /** True for one link within the window after a touch; that touch is then spent. */
  claim: () => boolean;
};

export function createPreviewTapGate(now: () => number = () => Date.now()): PreviewTapGate {
  let touchedAt: number | null = null;
  return {
    touched: () => {
      touchedAt = now();
    },
    claim: () => {
      if (touchedAt === null) return false;
      const elapsed = now() - touchedAt;
      touchedAt = null;
      return elapsed >= 0 && elapsed <= PREVIEW_TAP_WINDOW_MS;
    },
  };
}
