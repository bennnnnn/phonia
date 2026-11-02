/** CDN hosts HTML Run may load. Not open `https:` — keep this list tight. */
const HTML_RUN_CDN_HOSTS = [
  "https://cdn.jsdelivr.net",
  "https://unpkg.com",
  "https://cdnjs.cloudflare.com",
  "https://fonts.googleapis.com",
  "https://fonts.gstatic.com",
] as const;

export const HTML_RUN_CDN_CSP = HTML_RUN_CDN_HOSTS.join(" ");
