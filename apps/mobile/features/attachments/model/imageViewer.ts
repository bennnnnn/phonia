/** One photo the full-screen viewer can show (chat thumbnail or Library item). */
export type AttachmentViewerImage = {
  attachmentId?: string | null;
  localUri?: string | null;
  path?: string | null;
  fileName?: string;
  previewUri?: string | null;
  chatId?: string | null;
  /** Spoken name; falls back to `fileName`. */
  label?: string;
};

/** Pages within this many of the last photo ask the Library for its next page. */
const VIEWER_PREFETCH_PAGES = 2;

/** Which photo this is, so the viewer follows it when the list around it changes. */
export function viewerImageKey(image: AttachmentViewerImage | undefined): string | null {
  if (!image) return null;
  return image.attachmentId ?? image.path ?? image.localUri ?? image.previewUri ?? null;
}

/**
 * The page for the photo the viewer was showing. When that photo is gone
 * (deleted), the one that took its place shows: the next photo, or the one
 * before when it was last.
 */
export function resolveViewerIndex(
  images: AttachmentViewerImage[],
  currentKey: string | null,
  lastIndex: number,
): number {
  if (images.length === 0) return 0;
  if (currentKey != null) {
    const found = images.findIndex((image) => viewerImageKey(image) === currentKey);
    if (found >= 0) return found;
  }
  return Math.min(Math.max(0, lastIndex), images.length - 1);
}

/** True when the viewer is close enough to the last photo to load more. */
export function isNearViewerEnd(
  index: number,
  count: number,
  pages: number = VIEWER_PREFETCH_PAGES,
): boolean {
  return count > 0 && index >= count - 1 - pages;
}
