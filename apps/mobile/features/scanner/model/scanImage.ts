import { deleteAsync } from "expo-file-system/legacy";
import { ImageManipulator, type ImageRef, SaveFormat } from "expo-image-manipulator";

/**
 * Longest edge of a scan crop sent to the reader. Mathpix and the vision
 * models read handwriting well at this size; a full-resolution crop only adds
 * upload time and the API's 8 MB cap.
 */
export const SCAN_MAX_EDGE = 2048;
export const SCAN_JPEG_QUALITY = 0.8;

type ImageSize = { width: number; height: number };
type PixelCrop = { originX: number; originY: number; width: number; height: number };

/** The downscale that brings a crop's long edge to `maxEdge`; null when it already fits. */
export function scanResize(
  size: ImageSize,
  maxEdge = SCAN_MAX_EDGE,
): { width: number } | { height: number } | null {
  if (Math.max(size.width, size.height) <= maxEdge) return null;
  return size.width >= size.height ? { width: maxEdge } : { height: maxEdge };
}

function validSize(image: ImageRef): ImageSize {
  const { width, height } = image;
  if (!(width > 0 && height > 0)) throw new Error("invalid image size");
  return { width, height };
}

/**
 * The image's size as the manipulator sees it (EXIF orientation applied), the
 * same space `cropScanImage` cuts in. React Native's Image.getSize can report
 * the stored, unrotated size instead.
 */
export async function measureScanImage(uri: string): Promise<ImageSize> {
  const context = ImageManipulator.manipulate(uri);
  let image: ImageRef | undefined;
  try {
    image = await context.renderAsync();
    return validSize(image);
  } finally {
    image?.release();
    context.release();
  }
}

/**
 * Crop and downscale a scan in one pass. `cropFor` gets the decoded size, so
 * the crop is computed in the space it is applied in.
 */
export async function cropScanImage(
  uri: string,
  cropFor: (size: ImageSize) => PixelCrop,
): Promise<{ uri: string } & ImageSize> {
  const context = ImageManipulator.manipulate(uri);
  let source: ImageRef | undefined;
  let result: ImageRef | undefined;
  try {
    source = await context.renderAsync();
    const crop = cropFor(validSize(source));
    context.crop(crop);
    const resize = scanResize(crop);
    if (resize) context.resize(resize);
    result = await context.renderAsync();
    const saved = await result.saveAsync({ compress: SCAN_JPEG_QUALITY, format: SaveFormat.JPEG });
    return { uri: saved.uri, width: saved.width, height: saved.height };
  } finally {
    result?.release();
    source?.release();
    context.release();
  }
}

/** Delete a scan file from the cache. Idempotent; a failed delete never blocks the scanner. */
function discardScanFile(uri: string): void {
  void deleteAsync(uri, { idempotent: true }).catch(() => undefined);
}

/**
 * The cache files one scanner owns: every capture, picked copy and crop until
 * it is handed to the composer as the chat attachment or discarded.
 */
export class ScanFiles {
  private readonly owned = new Set<string>();

  track(uri: string): void {
    this.owned.add(uri);
  }

  /** The composer owns this file now; the scanner never deletes it. */
  handOff(uri: string): void {
    this.owned.delete(uri);
  }

  discard(uri: string): void {
    if (!this.owned.delete(uri)) return;
    discardScanFile(uri);
  }

  discardAll(): void {
    for (const uri of this.owned) discardScanFile(uri);
    this.owned.clear();
  }
}
