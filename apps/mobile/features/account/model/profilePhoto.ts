import { File } from "expo-file-system";
import { ImageManipulator, type ImageRef, SaveFormat } from "expo-image-manipulator";

import { pickFromPhotoLibrary, type PendingAttachment } from "@/features/attachments/model/attachments";

const MAX_SOURCE_BYTES = 30 * 1024 * 1024;
const MAX_SOURCE_PIXELS = 40_000_000;
const MAX_SOURCE_EDGE = 16_384;
const PROFILE_PHOTO_EDGE = 512;
const PROFILE_PHOTO_QUALITY = 0.8;
const generatedPhotos = new Set<string>();

/** Release only previews created here; never remove a selected library original. */
export function discardProfilePhoto(photo: PendingAttachment): void {
  if (!generatedPhotos.delete(photo.localUri)) return;
  try {
    const file = new File(photo.localUri);
    if (file.exists) file.delete();
  } catch {
    // Best-effort cache cleanup must not prevent closing or saving the editor.
  }
}

/** Pick and prepare a local preview. Upload happens only when the editor saves. */
export async function pickProfilePhoto(): Promise<PendingAttachment | null> {
  const selected = await pickFromPhotoLibrary({ squareCrop: true });
  if (!selected) return null;

  const { width, height } = selected.imageSize ?? { width: 0, height: 0 };
  const source = new File(selected.localUri);
  if (
    selected.kind !== "image" ||
    !source.exists ||
    !Number.isSafeInteger(source.size) ||
    source.size <= 0 ||
    !Number.isSafeInteger(width) ||
    !Number.isSafeInteger(height) ||
    width <= 0 ||
    height <= 0
  ) {
    throw new Error("PROFILE_PHOTO_INVALID");
  }
  if (
    source.size > MAX_SOURCE_BYTES ||
    width * height > MAX_SOURCE_PIXELS ||
    width > MAX_SOURCE_EDGE ||
    height > MAX_SOURCE_EDGE
  ) {
    throw new Error("PROFILE_PHOTO_TOO_LARGE");
  }

  const side = Math.min(width, height);
  const context = ImageManipulator.manipulate(selected.localUri);
  let image: ImageRef | undefined;
  let preview: PendingAttachment | undefined;
  try {
    // Native crop UI is square; enforce that shape if a platform ignores it.
    if (width !== height) {
      context.crop({
        originX: Math.floor((width - side) / 2),
        originY: Math.floor((height - side) / 2),
        width: side,
        height: side,
      });
    }
    if (side > PROFILE_PHOTO_EDGE) {
      context.resize({ width: PROFILE_PHOTO_EDGE, height: PROFILE_PHOTO_EDGE });
    }
    image = await context.renderAsync();
    const result = await image.saveAsync({
      format: SaveFormat.JPEG,
      compress: PROFILE_PHOTO_QUALITY,
    });
    preview = {
      localUri: result.uri,
      contentType: "image/jpeg",
      fileName: `profile-${Date.now()}.jpg`,
      kind: "image",
    };
    if (result.uri !== selected.localUri) generatedPhotos.add(result.uri);

    const prepared = new File(result.uri);
    if (
      result.uri === selected.localUri ||
      !prepared.exists ||
      !Number.isSafeInteger(prepared.size) ||
      prepared.size <= 0 ||
      !Number.isSafeInteger(result.width) ||
      result.width <= 0 ||
      result.width > PROFILE_PHOTO_EDGE ||
      result.width !== result.height
    ) {
      throw new Error("PROFILE_PHOTO_INVALID");
    }
    return preview;
  } catch (error) {
    if (preview) discardProfilePhoto(preview);
    throw error;
  } finally {
    image?.release();
    context.release();
  }
}
