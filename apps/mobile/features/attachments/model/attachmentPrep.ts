import { File } from "expo-file-system";
import { ImageManipulator, type ImageManipulatorContext, type ImageRef, SaveFormat } from "expo-image-manipulator";

import { AttachmentError } from "@/features/attachments/model/attachmentErrors";
import {
  DOCUMENT_MIME_TYPES,
  IMAGE_JPEG_QUALITY,
  MAX_ATTACHMENT_BYTES,
  MAX_IMAGE_EDGE,
  UPLOADABLE_IMAGE_TYPES,
} from "@/features/attachments/model/attachmentLimits";
import { stripGifMetadata } from "@/features/attachments/model/gifMetadata";
import { adoptLocalCopy, discardLocalCopy, ownsLocalCopy } from "@/features/attachments/model/localAttachmentFile";

/** What a picker returned, with its content type already normalized. */
export type PickedAsset = {
  uri: string;
  contentType: string;
  fileName: string;
};

type PreparedAttachment = {
  localUri: string;
  contentType: string;
  fileName: string;
  kind: "image" | "file";
};

/** What a re-encode writes. */
type Encoding = { format: SaveFormat; contentType: string; extension: string };

const JPEG: Encoding = { format: SaveFormat.JPEG, contentType: "image/jpeg", extension: "jpg" };

/** PNG and WebP keep their format, and so any transparency (JPEG paints it black). */
const KEPT_ENCODINGS: Readonly<Record<string, Encoding>> = {
  "image/png": { format: SaveFormat.PNG, contentType: "image/png", extension: "png" },
  "image/webp": { format: SaveFormat.WEBP, contentType: "image/webp", extension: "webp" },
};

/** Size of a local file; a missing or empty file cannot be sent. */
export function localFileSize(uri: string): number {
  const file = new File(uri);
  if (!file.exists) throw new AttachmentError("unreadable");
  const size = file.size;
  if (!Number.isSafeInteger(size) || size <= 0) throw new AttachmentError("unreadable");
  return size;
}

function withExtension(fileName: string, extension: string): string {
  const stem = fileName.replace(/\.[^./]+$/, "") || "photo";
  return `${stem}.${extension}`;
}

/**
 * A GIF keeps its frames, so it stays animated: only its metadata blocks go,
 * rewritten in this pick's own copy. Null for one too big to send as it is, one
 * that does not parse, and a file only named a GIF (Android's picker writes a
 * JPEG, its EXIF copied in, under that name): those are re-encoded instead.
 */
async function strippedGif(asset: PickedAsset): Promise<PreparedAttachment | null> {
  if (asset.contentType !== "image/gif" || !ownsLocalCopy(asset.uri)) return null;
  if (localFileSize(asset.uri) > MAX_ATTACHMENT_BYTES) return null;
  const file = new File(asset.uri);
  const original = await file.bytes();
  const gif = stripGifMetadata(original);
  if (!gif || gif.width <= 0 || gif.height <= 0 || Math.max(gif.width, gif.height) > MAX_IMAGE_EDGE) return null;
  if (gif.bytes.length !== original.length) file.write(gif.bytes);
  return { localUri: asset.uri, contentType: "image/gif", fileName: asset.fileName, kind: "image" };
}

/**
 * A new file of the image's pixels and nothing else: expo-image-manipulator
 * writes no EXIF, GPS or XMP (iOS `UIImage.jpegData`/`pngData`, Android
 * `Bitmap.compress`). A PNG or WebP still over the byte cap goes as a JPEG.
 */
async function savedWithoutMetadata(image: ImageRef, fileName: string, encoding: Encoding): Promise<PreparedAttachment> {
  const saved = await image.saveAsync({ format: encoding.format, compress: IMAGE_JPEG_QUALITY });
  adoptLocalCopy(saved.uri);
  if (encoding !== JPEG && localFileSize(saved.uri) > MAX_ATTACHMENT_BYTES) {
    discardLocalCopy(saved.uri);
    return savedWithoutMetadata(image, fileName, JPEG);
  }
  return {
    localUri: saved.uri,
    contentType: encoding.contentType,
    fileName: withExtension(fileName, encoding.extension),
    kind: "image",
  };
}

/**
 * Every other photo is decoded and written again, whatever its size: upright
 * (its EXIF orientation applied), no larger than MAX_IMAGE_EDGE on its long
 * edge, and with none of the original's metadata (GPS position, time, camera).
 * HEIC, TIFF and the rest become JPEG.
 */
async function reencoded(asset: PickedAsset): Promise<PreparedAttachment> {
  const contexts: ImageManipulatorContext[] = [ImageManipulator.manipulate(asset.uri)];
  const images: ImageRef[] = [];
  try {
    let image = await contexts[0].renderAsync();
    images.push(image);
    if (Math.max(image.width, image.height) > MAX_IMAGE_EDGE) {
      const resize = ImageManipulator.manipulate(image).resize(
        image.width >= image.height ? { width: MAX_IMAGE_EDGE } : { height: MAX_IMAGE_EDGE },
      );
      contexts.push(resize);
      image = await resize.renderAsync();
      images.push(image);
    }
    return await savedWithoutMetadata(image, asset.fileName, KEPT_ENCODINGS[asset.contentType] ?? JPEG);
  } finally {
    for (const image of images) image.release();
    for (const context of contexts) context.release();
  }
}

/** Every picked photo leaves here without its metadata, as something the API accepts. */
async function prepareImage(asset: PickedAsset): Promise<PreparedAttachment> {
  try {
    return (await strippedGif(asset)) ?? (await reencoded(asset));
  } catch (error) {
    if (error instanceof AttachmentError) throw error;
    // An allowed type that will not decode is damaged; anything else (SVG, RAW) is a type we cannot take.
    throw new AttachmentError(UPLOADABLE_IMAGE_TYPES.has(asset.contentType) ? "unreadable" : "unsupported_type");
  }
}

function prepareDocument(asset: PickedAsset): PreparedAttachment {
  if (!DOCUMENT_MIME_TYPES.includes(asset.contentType)) throw new AttachmentError("unsupported_type");
  return { localUri: asset.uri, contentType: asset.contentType, fileName: asset.fileName, kind: "file" };
}

/**
 * Turns a pick into a composer attachment the API will take, or refuses it
 * now with the reason, before Send. The picker's copy is removed when a
 * re-encode replaces it, and every copy made here is removed on a refusal.
 */
export async function preparePickedAsset(asset: PickedAsset): Promise<PreparedAttachment> {
  adoptLocalCopy(asset.uri);
  let prepared: PreparedAttachment | null = null;
  try {
    prepared = asset.contentType.startsWith("image/") ? await prepareImage(asset) : prepareDocument(asset);
    if (localFileSize(prepared.localUri) > MAX_ATTACHMENT_BYTES) throw new AttachmentError("too_large");
    if (prepared.localUri !== asset.uri) discardLocalCopy(asset.uri);
    return prepared;
  } catch (error) {
    discardLocalCopy(asset.uri);
    discardLocalCopy(prepared?.localUri);
    throw error;
  }
}
