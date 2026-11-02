const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "::1"]);

/** Production web builds must talk to a public HTTPS API (no mixed content / loopback). */
export function assertProductionApiUrl(apiUrl: string | undefined): void {
  const trimmed = apiUrl?.trim();
  if (!trimmed) {
    throw new Error("VITE_API_URL must be set to a public https:// URL for production builds");
  }
  let parsed: URL;
  try {
    parsed = new URL(trimmed);
  } catch {
    throw new Error(`VITE_API_URL must be a valid https:// URL, got "${trimmed}"`);
  }
  const host = parsed.hostname.toLowerCase();
  if (parsed.protocol !== "https:" || LOOPBACK_HOSTS.has(host)) {
    throw new Error(
      `VITE_API_URL must be a public https:// URL for production builds, got "${trimmed}"`,
    );
  }
}
