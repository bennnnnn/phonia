import { File, Paths } from "expo-file-system";

// Copies the pickers and the image manipulator wrote for a composer pick. A
// Library pick's local file is the download cache, and a library original is
// the user's: neither is ever listed here, so neither is ever deleted.
const ownedCopies = new Set<string>();

function inCacheDirectory(uri: string): boolean {
  try {
    const cache = Paths.cache.uri;
    return Boolean(cache) && uri.startsWith(cache);
  } catch {
    return false;
  }
}

/** Record a temporary copy made for this pick. Only cache-directory files qualify. */
export function adoptLocalCopy(uri: string): void {
  if (inCacheDirectory(uri)) ownedCopies.add(uri);
}

/** Whether `uri` is a temporary copy made for this pick, so one Recall may rewrite. */
export function ownsLocalCopy(uri: string): boolean {
  return ownedCopies.has(uri);
}

/** Delete a temporary copy once nothing needs it. Any other file is left alone. */
export function discardLocalCopy(uri: string | null | undefined): void {
  if (!uri || !ownedCopies.delete(uri)) return;
  try {
    const file = new File(uri);
    if (file.exists) file.delete();
  } catch {
    // Cache cleanup is best-effort; the OS reclaims the cache directory anyway.
  }
}
