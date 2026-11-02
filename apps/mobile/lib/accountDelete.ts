import { isServiceUnavailable } from "@/lib/api/errorBody";

/**
 * The server ends the sessions only once the account's rows are deleted, so a 401/404 here (a
 * retry after a reply that never arrived) means the account is already gone.
 */
export function isAccountDeleteComplete(error: unknown): boolean {
  if (typeof error !== "object" || error === null || !("status" in error)) {
    return false;
  }
  const status = error.status;
  return status === 401 || status === 404;
}

/** Why a delete did not happen. */
export type AccountDeleteFailure = "unavailable" | "failed";

/**
 * A refused delete: Recall could not serve it for now (its 503 `unavailable`, refused with
 * nothing deleted and still signed in when Redis or the database fails before the account's
 * rows are deleted, or a gateway's 502/503/504), or anything else.
 */
export function accountDeleteFailure(error: unknown): AccountDeleteFailure {
  return isServiceUnavailable(error) ? "unavailable" : "failed";
}

/** The line a refused delete says: try again in a moment, or that it failed. */
export function accountDeleteFailureKey(failure: AccountDeleteFailure): string {
  return failure === "unavailable" ? "common.service_unavailable" : "settings.delete_failed";
}
