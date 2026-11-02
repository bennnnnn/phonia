/**
 * Zoom math for the photo viewer. Offsets are measured from the stage centre,
 * the photo is centred in the stage, and the view transform is
 * `translate(offset) scale(scale)` about its centre, so a photo point `p`
 * (unscaled, from the centre) lands at `p * scale + offset` on screen.
 *
 * Every function is a worklet: gesture callbacks call them on the UI thread.
 */

export const ZOOM_MAX = 4;
/** Where a double tap zooms to. */
export const ZOOM_DOUBLE_TAP = 2.5;
/** Pinching may dip this far under 1x before it springs back. */
const ZOOM_UNDERSHOOT = 0.85;
/** Above this the photo counts as zoomed: paging and swipe-down-to-close stop. */
const ZOOM_ACTIVE = 1.01;

export function isZoomed(scale: number): boolean {
  "worklet";
  return scale > ZOOM_ACTIVE;
}

/** Scale while the fingers are down: up to ZOOM_MAX, a little give under 1x. */
export function pinchScale(startScale: number, gestureScale: number): number {
  "worklet";
  return Math.min(ZOOM_MAX, Math.max(ZOOM_UNDERSHOOT, startScale * gestureScale));
}

/** Farthest the photo may move on one axis while its edge still covers the stage. */
export function maxPan(content: number, stage: number, scale: number): number {
  "worklet";
  return Math.max(0, (content * scale - stage) / 2);
}

export function clampPan(offset: number, content: number, stage: number, scale: number): number {
  "worklet";
  const limit = maxPan(content, stage, scale);
  return Math.min(limit, Math.max(-limit, offset));
}

/**
 * The offset that keeps the photo point that was under `focalStart` (at
 * `startScale`, `startOffset`) under the fingers at `focalNow` and `scale`.
 * Moving both fingers therefore pans while pinching.
 */
export function focalOffset(
  startOffset: number,
  focalStart: number,
  focalNow: number,
  startScale: number,
  scale: number,
): number {
  "worklet";
  return focalNow - ((focalStart - startOffset) / startScale) * scale;
}

/**
 * Where a double tap at `tap` (from the stage centre) leads: back to 1x when
 * zoomed, else ZOOM_DOUBLE_TAP with the tapped point kept under the finger.
 */
export function doubleTapZoom(
  scale: number,
  tapX: number,
  tapY: number,
  content: { width: number; height: number },
  stage: { width: number; height: number },
): { scale: number; x: number; y: number } {
  "worklet";
  if (isZoomed(scale)) return { scale: 1, x: 0, y: 0 };
  const next = ZOOM_DOUBLE_TAP;
  return {
    scale: next,
    x: clampPan(focalOffset(0, tapX, tapX, 1, next), content.width, stage.width, next),
    y: clampPan(focalOffset(0, tapY, tapY, 1, next), content.height, stage.height, next),
  };
}
