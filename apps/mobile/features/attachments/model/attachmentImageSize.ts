export type ImageSize = { width: number; height: number };

/** Fit a decoded photo inside its thumbnail bounds without changing its ratio. */
export function fitAttachmentImage(size: ImageSize, bounds: ImageSize): ImageSize | null {
  if (![size.width, size.height, bounds.width, bounds.height].every(
    (value) => Number.isFinite(value) && value > 0,
  )) return null;
  const ratio = size.width / size.height;
  if (!Number.isFinite(ratio) || ratio <= 0) return null;
  const width = Math.min(bounds.width, bounds.height * ratio);
  const height = width / ratio;
  return Number.isFinite(width) && width > 0 && Number.isFinite(height) && height > 0
    ? { width, height }
    : null;
}
