import { Linking } from "react-native";

/**
 * Guard for markdown `[text](url)` link targets rendered in chat.
 *
 * Model-emitted markdown can include arbitrary link URLs, so without a scheme
 * check a `javascript:` or `data:` URL could be handed to `Linking.openURL`,
 * which on some platforms executes the payload. We allow only schemes that
 * are safe to hand to the OS link handler:
 *  - `http:` / `https:` — ordinary web links.
 *  - `mailto:` / `tel:` — compose / dial intents (no script execution).
 *  - `sms:` / `maps:` / `geo:` — common app intents the model emits.
 *
 * `javascript:`, `data:`, `file:`, `content:`, `ws:`, etc. are blocked. The
 * allowlist is intentionally permissive on the *kind* of scheme (web + common
 * intents) but strict on *which* schemes — anything that can execute script
 * or read local files is rejected.
 *
 * HTML Run preview (`openHtmlInBrowser`) intentionally opens `data:` / `file:`
 * and must not go through `openAllowedUrl`.
 */
const ALLOWED_LINK_SCHEMES = new Set([
  "http:",
  "https:",
  "mailto:",
  "tel:",
  "sms:",
  "maps:",
  "geo:",
]);

export function isAllowedLinkUrl(href: string | undefined | null): href is string {
  if (!href || typeof href !== "string") return false;
  const trimmed = href.trim();
  if (!trimmed) return false;
  try {
    const { protocol } = new URL(trimmed);
    return ALLOWED_LINK_SCHEMES.has(protocol.toLowerCase());
  } catch {
    // Relative paths and bare strings aren't valid link targets for the OS
    // handler; require an absolute URL with an allowed scheme.
    return false;
  }
}

/** Open an allowlisted URL in the OS handler. Returns false if blocked or open fails. */
export async function openAllowedUrl(
  href: string | undefined | null,
): Promise<boolean> {
  if (!isAllowedLinkUrl(href)) return false;
  try {
    await Linking.openURL(href);
    return true;
  } catch {
    return false;
  }
}
