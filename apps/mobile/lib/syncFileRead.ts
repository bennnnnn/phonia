/**
 * A small text file read synchronously, for the little the first frame needs
 * before React renders (the appearance, the accent, the cached account's
 * language; `lib/launchPrefs.ts`). Every other read stays asynchronous.
 *
 * Null when the file is missing or cannot be read, or when the native file
 * system is absent, so a launch never fails on it. The module is required
 * here rather than at the top because the prefs and caches that offer this
 * read are imported almost everywhere, tests included, without it.
 */
type Directory = "document" | "cache";

export function readTextFileSync(directory: Directory, fileName: string): string | null {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports -- loaded on first read, see above
    const { File, Paths } = require("expo-file-system") as typeof import("expo-file-system");
    const file = new File(directory === "document" ? Paths.document : Paths.cache, fileName);
    return file.exists ? file.textSync() : null;
  } catch {
    return null;
  }
}
