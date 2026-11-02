import { ApiRequestError } from "@/lib/api/client";
import { isServiceUnavailable } from "@/lib/api/errorBody";

/** A scan the API refused, with the message the student should see. */
export type ScanReadFailure = { error: string };

// Every subject's read endpoint shares one protocol (services/scan_read.py), and each
// refusal names a code (docs/fixtures/error_codes.json): the words are the phone's own.
// 404 when the reader is off, 413 for an oversized photo, 429 for a limit.
const NAMED_STATUSES = new Set([404, 413, 429]);

const CODE_KEYS: Record<string, string> = {
  not_available: "chat.scan_unavailable",
  image_too_large: "chat.scan_too_large",
  scan_rate_limited: "chat.scan_rate_limit",
  scan_spend_cap: "chat.scan_spend_cap",
  // Any request over a limit (the API's request limiter, a refused refresh): it showed the
  // server's English. Not the scan's own hourly limit, so not "Too many scans".
  rate_limited: "chat.rate_limited",
};

/**
 * The words for a refused scan, for any subject: the phone's own for a known code or an
 * outage, the server's for another refusal of a named status. A network failure, a vision
 * failure and every other status stay the generic could-not-read message, so this returns
 * nothing for them.
 */
export function scanFailureMessage(error: unknown, t: (key: string) => string): string | null {
  // Recall down (a Redis outage said "Too many scans in a row"): not the photo's fault.
  if (error instanceof ApiRequestError && isServiceUnavailable(error)) return t("common.service_unavailable");
  if (!(error instanceof ApiRequestError) || !NAMED_STATUSES.has(error.status)) return null;
  const key = error.code == null ? undefined : CODE_KEYS[error.code];
  return key ? t(key) : error.detail.trim() || null;
}
