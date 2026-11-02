import { ApiRequestError, isServiceUnavailable } from "@/lib/api/errorBody";
import { isServerUnreachable } from "@/lib/api/deadline";
import { MAX_ATTACHMENT_MEGABYTES } from "@/features/attachments/model/attachmentLimits";
import { shareFailureKey } from "@/lib/shareUnavailable";

/** Why an attachment could not be picked or uploaded. Each reason has one message. */
export type AttachmentFailure =
  | "too_large"
  | "unsupported_type"
  | "unreadable"
  | "changed"
  | "upload_failed"
  | "daily_limit"
  | "camera_permission";

export class AttachmentError extends Error {
  readonly reason: AttachmentFailure;
  constructor(reason: AttachmentFailure) {
    super(`ATTACHMENT_${reason.toUpperCase()}`);
    this.name = "AttachmentError";
    this.reason = reason;
  }
}

const MESSAGE_KEYS: Record<AttachmentFailure, string> = {
  too_large: "chat.attach_too_large",
  unsupported_type: "chat.attach_unsupported_type",
  unreadable: "chat.attach_unreadable",
  changed: "chat.attach_changed",
  upload_failed: "chat.attach_upload_failed",
  daily_limit: "chat.attach_daily_limit",
  camera_permission: "chat.camera_permission",
};

type Translate = (key: string, options?: Record<string, unknown>) => string;

/**
 * The toast for a failed pick or upload. No answer from Recall (offline at the presign)
 * is the unreachable line, as everywhere else; it said "Could not attach". Anything else
 * untyped is the generic message, never raw text.
 */
export function attachmentErrorMessage(error: unknown, t: Translate): string {
  if (isServerUnreachable(error)) return t("chat.error_unreachable");
  if (!(error instanceof AttachmentError)) return t("chat.attach_failed");
  return t(MESSAGE_KEYS[error.reason], { limit: MAX_ATTACHMENT_MEGABYTES });
}

/**
 * The words for a failed action on a stored file (the Library's share, attach and delete; a
 * PDF card's share), always the phone's own. A refusal from the API: over a request limit,
 * Recall down, or the action's own line. Its English showed ("Too many requests. Please
 * slow down.", a delete's "Not found"). No answer from Recall is the unreachable line; a
 * build that cannot share files says to update the app; any other failure on this phone
 * (a file it could not fetch, open or share) is the action's own. Their English showed too:
 * "Could not reach the Recall server…", "Could not attach", "Could not open this
 * attachment.", "Network request failed".
 */
export function libraryActionMessage(error: unknown, fallbackKey: string, t: Translate): string {
  if (error instanceof ApiRequestError) {
    if (error.code === "rate_limited") return t("chat.rate_limited");
    return t(isServiceUnavailable(error) ? "common.service_unavailable" : fallbackKey);
  }
  return t(shareFailureKey(error, isServerUnreachable(error) ? "chat.error_unreachable" : fallbackKey));
}

/** The fields FastAPI's validation refused: each error's `loc`, last part. */
function refusedFields(error: ApiRequestError): string[] {
  const errors = error.fields.errors;
  if (!Array.isArray(errors)) return [];
  return errors.map((item) => {
    const loc = (item as { loc?: unknown } | null)?.loc;
    return Array.isArray(loc) ? String(loc[loc.length - 1]) : "";
  });
}

/**
 * Presign refusals named by the API's codes (modules/attachments/upload.py,
 * docs/fixtures/error_codes.json); the schema's cap on `size_bytes` is FastAPI's 422.
 * Any other API refusal is a failed upload; a non-API error (session change,
 * network) passes through unchanged.
 */
export function presignFailure(error: unknown): unknown {
  if (!(error instanceof ApiRequestError)) return error;
  if (error.code === "daily_limit") return new AttachmentError("daily_limit");
  if (error.code === "unsupported_type") return new AttachmentError("unsupported_type");
  if (error.code === "invalid_size" || refusedFields(error).includes("size_bytes")) {
    return new AttachmentError("too_large");
  }
  return new AttachmentError("upload_failed");
}
