import { readAsStringAsync } from "expo-file-system/legacy";

import { request } from "@/lib/api/client";
import { getSessionGeneration, requireTokenSession, SessionChangedError } from "@/lib/auth";
import type { ReadBackSubject } from "@/features/scanner/model/readBack";

/** What the scanner read, for the student to confirm or edit before solving. */
export type ScanReading = {
  /** Plain editable text ("2x + 3 = 7"); empty when nothing was legible. */
  reading: string;
  /** Hard to read: the review asks the student to check it closely. */
  uncertain: boolean;
  source: "mathpix" | "vision" | "none";
};

const SCAN_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

/**
 * The API answers a read within `scan_read_deadline_seconds` (20 s) of
 * receiving it, every reader and fallback included. The client waits that
 * plus 5 s for the upload and the reply, so a slow read comes back as the
 * API's "could not read" answer instead of a client timeout.
 */
const SCAN_READ_TIMEOUT_MS = 25_000;

/**
 * Read a cropped scan back without solving it, through the subject's own
 * reader. The file is base64-encoded natively (a JS-thread encode of a full
 * photo froze the scanner once before).
 */
export async function readScan(
  token: string,
  subject: ReadBackSubject,
  scan: { localUri: string; contentType: string },
  signal?: AbortSignal,
): Promise<ScanReading> {
  requireTokenSession(token);
  const generation = getSessionGeneration();
  const imageBase64 = await readAsStringAsync(scan.localUri, { encoding: "base64" });
  if (generation !== getSessionGeneration()) throw new SessionChangedError();
  return request<ScanReading>(
    `/${subject}/scan/read`,
    token,
    {
      method: "POST",
      body: JSON.stringify({
        image_base64: imageBase64,
        content_type: SCAN_TYPES.has(scan.contentType) ? scan.contentType : "image/jpeg",
      }),
      signal,
    },
    true,
    SCAN_READ_TIMEOUT_MS,
  );
}

export const scanApi = {
  readScan,
};
