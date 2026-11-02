/**
 * The id each call to our API carries (`X-Request-ID`; a chat socket's is a `request_id`
 * query parameter, since a socket cannot set headers). The API puts it on every log line
 * the call writes and echoes it back, so an error this phone reports to Sentry can be
 * matched to the server's lines for the same call. An id, never content.
 */

export const REQUEST_ID_HEADER = "X-Request-ID";

/** The API's rule for an id it accepts (apps/api/app/core/request_id.py). */
const REQUEST_ID = /^[A-Za-z0-9_-]{1,64}$/;

/** Correlation, not a secret: time and randomness keep two calls' ids apart. */
export function newRequestId(): string {
  const random = () => Math.random().toString(36).slice(2, 10).padEnd(8, "0");
  return `m${Date.now().toString(36)}-${random()}${random()}`;
}

export function isRequestId(value: unknown): value is string {
  return typeof value === "string" && REQUEST_ID.test(value);
}

/** The id the API answered with (its echo of ours), or null. */
export function responseRequestId(response: Response): string | null {
  // Test doubles and some transports have no headers object.
  const echoed =
    typeof response.headers?.get === "function" ? response.headers.get(REQUEST_ID_HEADER) : null;
  return isRequestId(echoed) ? echoed : null;
}

/** `url` with this socket's id as its `request_id` query parameter. */
export function withRequestId(url: string, requestId: string): string {
  const [base, hash] = url.split("#", 2);
  const joined = `${base}${base.includes("?") ? "&" : "?"}request_id=${encodeURIComponent(requestId)}`;
  return hash === undefined ? joined : `${joined}#${hash}`;
}
