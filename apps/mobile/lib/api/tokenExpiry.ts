/**
 * Decode JWT expiry only as a latency hint. Authentication still belongs to
 * the server; unreadable/opaque tokens keep the existing request-then-401
 * behavior instead of being rejected by the client.
 */
export function accessTokenNeedsRefresh(
  token: string,
  nowMs: number = Date.now(),
  skewMs = 30_000,
): boolean {
  try {
    const parts = token.split(".");
    if (parts.length !== 3 || parts.some((part) => !part)) return false;
    const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = payload.padEnd(Math.ceil(payload.length / 4) * 4, "=");
    const claims: unknown = JSON.parse(atob(padded));
    if (typeof claims !== "object" || claims === null || !("exp" in claims)) return false;
    const exp = (claims as { exp?: unknown }).exp;
    if (typeof exp !== "number" || !Number.isFinite(exp)) return false;
    return exp * 1000 <= nowMs + Math.max(0, skewMs);
  } catch {
    return false;
  }
}
