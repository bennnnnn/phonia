import type { ApiRequestError } from "@/lib/api/client";

type SignInProvider = "google" | "apple";

/**
 * The email already has an account this sign-in may not join (the provider is
 * not the address's authority, or the account holds another id of it): sign in
 * the earlier way. The server answers 409 `account_exists`.
 */
export class AccountExistsError extends Error {
  constructor(readonly signInWith: SignInProvider) {
    super(`account_exists:${signInWith}`);
    this.name = "AccountExistsError";
  }
}

/** The provider an `account_exists` refusal names in `sign_in_with`. */
export function accountExistsProvider(error: ApiRequestError): SignInProvider | null {
  if (error.status !== 409 || error.code !== "account_exists") return null;
  const provider = error.fields.sign_in_with;
  return provider === "apple" || provider === "google" ? provider : null;
}
