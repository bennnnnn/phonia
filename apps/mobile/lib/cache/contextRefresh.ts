/** Skip redundant list refetches when in-memory data is still fresh. */
export const CONTEXT_REFRESH_STALE_MS = 20_000;

export function isContextFresh(
  lastFetchedAt: number | undefined,
  now = Date.now(),
): boolean {
  if (lastFetchedAt == null) return false;
  // A clock set back makes the age negative: not fresh, or it stays so until the clock catches up.
  const age = now - lastFetchedAt;
  return age >= 0 && age < CONTEXT_REFRESH_STALE_MS;
}
