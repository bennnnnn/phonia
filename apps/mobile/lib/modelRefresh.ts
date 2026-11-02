/** Gate for re-fetching the model catalog on app foreground. */
export function shouldRefreshModels(
  lastFetchedAt: number,
  now: number,
  ttlMs: number,
): boolean {
  if (lastFetchedAt <= 0) return true;
  // A clock set back makes the age negative: read again rather than wait for the clock.
  const age = now - lastFetchedAt;
  return age < 0 || age >= ttlMs;
}
