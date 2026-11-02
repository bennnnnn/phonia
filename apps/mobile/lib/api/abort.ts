/**
 * "This request was cancelled", however the runtime says it: fetch's AbortError (an Error,
 * or a DOMException that is not an Error in every runtime) or a client's CanceledError.
 * Six callers kept their own check and disagreed on which shapes count (code-health audit
 * DUP-13).
 */
export function isAbortError(error: unknown): boolean {
  if (typeof error !== "object" || error === null || !("name" in error)) return false;
  return error.name === "AbortError" || error.name === "CanceledError";
}
