/**
 * The server refuses a chat turn, voice and a photo read until the account agrees
 * to what goes to outside AI services: an error frame with `code: "consent_required"`,
 * or HTTP 403 `{"detail": {"code": "consent_required", …}}`. The auth context
 * registers the handler, and the root layout's gate shows the consent screen.
 *
 * `notifyConsentRequired()` is the one way any feature hands such a refusal to the
 * app's consent handling: the chat calls it for an error frame, `request()` for every
 * 403 with the code (so an HTTP caller only has to stop showing its own error for
 * `CONSENT_REQUIRED_CODE`). A sign-in records the agreement itself
 * (features/auth/api.ts), so this reaches only an account without one: from before
 * that, or one that withdrew in Data controls.
 */

export const CONSENT_REQUIRED_CODE = "consent_required";

let onConsentRequired: (() => void) | null = null;

export function setConsentRequiredHandler(fn: (() => void) | null): void {
  onConsentRequired = fn;
}

export function notifyConsentRequired(): void {
  onConsentRequired?.();
}
