/**
 * Estimated progress for the image-gen waiting card. The server reports no
 * real progress, so the percentage eases toward a ceiling with elapsed time:
 * quick at first, slower later, and never 100 while the image is still on
 * its way. The stage line follows the same curve, so the words and the
 * number move together.
 */

/** The estimate stops here until the real image arrives. */
export const IMAGE_GEN_PROGRESS_CAP = 95;
/** Time constant: about 60% of the cap after this long. */
const IMAGE_GEN_PROGRESS_TAU_MS = 12_000;

/** Whole percent, 1 to 95, for `elapsedMs` since the card appeared. */
export function estimateImageGenPercent(elapsedMs: number): number {
  const elapsed = Number.isFinite(elapsedMs) ? Math.max(0, elapsedMs) : 0;
  const raw = IMAGE_GEN_PROGRESS_CAP * (1 - Math.exp(-elapsed / IMAGE_GEN_PROGRESS_TAU_MS));
  return Math.min(IMAGE_GEN_PROGRESS_CAP, Math.max(1, Math.round(raw)));
}

/**
 * Which of `stageCount` stage lines to show at `percent`: equal shares of the
 * estimate, holding on the last one ("Almost there") once it is reached.
 */
export function imageGenStageIndex(percent: number, stageCount: number): number {
  if (stageCount <= 1 || !Number.isFinite(percent)) return 0;
  const share = Math.min(1, Math.max(0, percent / IMAGE_GEN_PROGRESS_CAP));
  return Math.min(stageCount - 1, Math.floor(share * stageCount));
}
