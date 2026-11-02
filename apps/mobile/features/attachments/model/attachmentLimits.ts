/** The API's per-file cap (apps/api/app/core/attachment_limits.py MAX_ATTACHMENT_SIZE). */
export const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;

/** Whole megabytes, for the "too large" message. */
export const MAX_ATTACHMENT_MEGABYTES = MAX_ATTACHMENT_BYTES / (1024 * 1024);

/** Image types the API stores as sent (modules/attachments/content_types.py IMAGE_CONTENT_TYPES). */
export const UPLOADABLE_IMAGE_TYPES: ReadonlySet<string> = new Set([
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/gif",
]);

/** Document types the API accepts (modules/attachments/content_types.py DOCUMENT_CONTENT_TYPES). */
export const DOCUMENT_MIME_TYPES: readonly string[] = [
  "application/pdf",
  "text/plain",
  "text/markdown",
  "text/csv",
  "application/json",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
];

/** Long edge of a chat photo. Vision models read no finer, and a full camera frame is 3–5×. */
export const MAX_IMAGE_EDGE = 2048;

/**
 * Quality of a lossy re-encode (JPEG, WebP). Every picked photo but a GIF is
 * re-encoded so it leaves without its metadata (attachmentPrep.ts).
 */
export const IMAGE_JPEG_QUALITY = 0.8;
