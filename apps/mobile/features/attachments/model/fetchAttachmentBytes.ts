import { File } from "expo-file-system";
import { recallAttachmentPath } from "@/features/attachments/model/attachmentUri";
import { attachmentSessionGuard } from "@/features/attachments/model/attachmentSession";
import { authorizeNativeTransfer, requestRaw } from "@/lib/api/client";
import { serverUnreachableError } from "@/lib/api/deadline";

/** Read an attachment into memory; for small files the screen shows as text. */
export async function fetchAttachmentBytes(
  uri: string,
  token: string | null,
  signal?: AbortSignal,
): Promise<ArrayBuffer> {
  const requireCurrent = attachmentSessionGuard(token);
  if (uri.startsWith("file://") || uri.startsWith("content://")) {
    const bytes = await new File(uri).arrayBuffer();
    requireCurrent();
    return bytes;
  }
  const path = recallAttachmentPath(uri);
  // External and local file URLs never receive Recall credentials. API
  // downloads share the same session fences and refresh policy as JSON/SSE.
  const response = path ? await requestRaw(path, token, { signal }) : await fetch(uri, { signal });
  if (!response.ok) throw new Error("Could not load attachment.");
  const bytes = await response.arrayBuffer();
  requireCurrent();
  return bytes;
}

const HTTP_STATUS = /status:? (\d{3})|HTTP (\d{3})/;

/** The native module reports a refused download only in its message. */
function failedStatus(error: unknown): number | null {
  const match = error instanceof Error ? HTTP_STATUS.exec(error.message) : null;
  return match ? Number(match[1] ?? match[2]) : null;
}

/**
 * The download's own reasons, all after the server answered (or with nothing to fetch):
 * a status, no HTTP response, no file, no body (expo-file-system 57, FileSystemDownload.swift/.kt).
 */
const ANSWERED = /Unable to download a file: (response has status|no response|no file url|response body is null)/;
/** OkHttp's failures with no answer, by Java class name (never translated): DNS, refused, reset, timeouts. */
const JAVA_NO_ANSWER =
  /\bjava\.(?:net\.(?:UnknownHost|Connect|NoRouteToHost|SocketTimeout|PortUnreachable|Socket)|io\.InterruptedIO)Exception\b/;

/**
 * The native download got no answer from the server: offline, DNS, a refused or dropped
 * connection, a timeout. fetch's wording (`isServerUnreachable`) never matches it, so a
 * Library share offline showed the action's own line. Read from expo-file-system 57:
 * - iOS rejects every URLSession error as `ERR_UNABLE_TO_DOWNLOAD`, "Unable to download a
 *   file: " + the error's localizedDescription, in the phone's language ("The Internet
 *   connection appears to be offline."); so the code is read, not the words.
 * - Android passes OkHttp's IOException on, which expo-modules-core wraps as
 *   `ERR_UNEXPECTED`, "…→ Caused by: java.net.UnknownHostException: …".
 * A status the server answered (404, 403) is `ERR_UNABLE_TO_DOWNLOAD` "response has status"
 * on both, and is never this.
 */
function noAnswer(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  const code = (error as { code?: unknown }).code;
  if (code === "ERR_UNABLE_TO_DOWNLOAD") return !ANSWERED.test(error.message);
  if (code === "ERR_UNEXPECTED") return JAVA_NO_ANSWER.test(error.message);
  return false;
}

/**
 * Stream an attachment straight to `dest` natively: the bytes never cross
 * into JavaScript. Recall URLs get the Bearer header (refreshed like fetch);
 * any other URL is downloaded without credentials. No answer from the server
 * rejects with `serverUnreachableError()`, worded by `isServerUnreachable`.
 */
export async function downloadAttachmentFile(
  uri: string,
  dest: string,
  token: string | null,
  signal?: AbortSignal,
): Promise<void> {
  const send = async (headers: Record<string, string>): Promise<number> => {
    try {
      await File.downloadFileAsync(uri, new File(dest), { headers, idempotent: true, signal });
      return 200;
    } catch (error) {
      const status = failedStatus(error);
      if (status !== null) return status;
      throw noAnswer(error) ? Object.assign(serverUnreachableError(), { cause: error }) : error;
    }
  };
  const status = recallAttachmentPath(uri) ? await authorizeNativeTransfer(token, send) : await send({});
  if (status !== 200) throw new Error("Could not load attachment.");
}
