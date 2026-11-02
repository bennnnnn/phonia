import type { ApiRequestError } from "@/lib/api/client";

/**
 * A sign-in the server turned away, as the login screen words it. The screen showed the
 * server's English as it came, in every language ("Invalid Google ID token"); each refusal
 * now names a code (docs/fixtures/error_codes.json, modules/account/signin_refusals.py) and
 * `key` is the screen's own line for it.
 */
export class SignInRefusedError extends Error {
  constructor(readonly key: string) {
    super(key);
    this.name = "SignInRefusedError";
  }
}

export const SIGN_IN_GENERIC_KEY = "login.error_generic";

/** No answer from the API (offline, a dropped connection, past the sign-in deadline). */
export function signInUnreachable(): SignInRefusedError {
  return new SignInRefusedError("login.error_unreachable");
}
const UNAVAILABLE_KEY = "login.error_unavailable";
const RATE_LIMITED_KEY = "login.error_rate_limited";
const TOKEN_INVALID_KEY = "login.error_token_invalid";

/** The line for each code `/auth/google`, `/auth/apple` and `/auth/dev` refuse with. */
const CODE_KEYS: Readonly<Record<string, string>> = {
  sign_in_rate_limited: RATE_LIMITED_KEY,
  // The API's request limiter over its minute (core/rest_rate_limit.py): dev login passes it.
  rate_limited: RATE_LIMITED_KEY,
  sign_in_unavailable: UNAVAILABLE_KEY,
  // The API's own outage body (core/unavailable.py): the request limiter with Redis down
  // (dev login passes it), or any route's database or Redis.
  unavailable: UNAVAILABLE_KEY,
  google_unavailable: UNAVAILABLE_KEY,
  apple_unavailable: UNAVAILABLE_KEY,
  google_token_invalid: TOKEN_INVALID_KEY,
  apple_token_invalid: TOKEN_INVALID_KEY,
  apple_key_unknown: TOKEN_INVALID_KEY,
  google_email_unverified: "login.error_google_email_unverified",
  apple_email_unverified: "login.error_apple_email_unverified",
  google_email_missing: "login.error_google_email_missing",
  apple_email_missing: "login.error_apple_email_missing",
  apple_not_configured: "login.error_apple_not_configured",
  dev_auth_disabled: "login.error_dev_disabled",
};

/** A refusal that names no code: a gateway's 503 or 429 in front of the API. */
const STATUS_KEYS: Readonly<Record<number, string>> = {
  429: RATE_LIMITED_KEY,
  503: UNAVAILABLE_KEY,
};

/** The i18n key for a refused sign-in: its code's line, a code-less refusal's status line,
 * else the one generic line (a code this phone does not know yet included). */
export function signInRefusalKey(error: ApiRequestError): string {
  if (error.code !== null) return CODE_KEYS[error.code] ?? SIGN_IN_GENERIC_KEY;
  return STATUS_KEYS[error.status] ?? SIGN_IN_GENERIC_KEY;
}
