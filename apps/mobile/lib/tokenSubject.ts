/**
 * The account id (`sub` claim) inside an access token, or null when it cannot
 * be read. Decoded only to pick which account's cached display data to show,
 * never to authenticate or grant access: a cache from a previous account can
 * survive a failed file deletion.
 */
export function tokenSubject(token: string): string | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3 || parts.some((part) => !part)) return null;
    const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = payload.padEnd(Math.ceil(payload.length / 4) * 4, "=");
    const claims: unknown = JSON.parse(atob(padded));
    return typeof claims === "object" && claims !== null &&
      "sub" in claims && typeof claims.sub === "string" ? claims.sub : null;
  } catch {
    return null;
  }
}
