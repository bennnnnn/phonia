import {
  cacheDirectory,
  deleteAsync,
  getInfoAsync,
  readAsStringAsync,
  writeAsStringAsync,
} from "expo-file-system/legacy";

import { readTextFileSync } from "@/lib/syncFileRead";

/** One best-effort text file in the OS cache directory, which the OS may purge
 * at any time; a missing or unreadable file reads as null. */
type CacheFile = {
  read: () => Promise<string | null>;
  /** Read at once, before the first render (`lib/launchPrefs.ts`). It does not
   * wait for this run's queued writes: it is for launch, before there are any. */
  readSync: () => string | null;
  write: (contents: string) => Promise<void>;
  clear: () => Promise<void>;
};

/** Writes and clears run in the order they were asked for, so a previous
 * account's started write finishes before signout clears it or a new account
 * replaces it. Readers also wait, to avoid observing a partial file. */
export function cacheFile(fileName: string): CacheFile {
  const path = cacheDirectory ? `${cacheDirectory}${fileName}` : null;
  let pending: Promise<void> = Promise.resolve();
  const enqueue = (change: (filePath: string) => Promise<void>): Promise<void> => {
    if (!path) return Promise.resolve();
    const result = pending.then(() => change(path)).catch(() => {});
    pending = result;
    return result;
  };
  return {
    async read() {
      if (!path) return null;
      await pending;
      try {
        const info = await getInfoAsync(path);
        return info.exists ? await readAsStringAsync(path) : null;
      } catch {
        return null;
      }
    },
    readSync: () => (path ? readTextFileSync("cache", fileName) : null),
    write: (contents) => enqueue((filePath) => writeAsStringAsync(filePath, contents)),
    clear: () => enqueue((filePath) => deleteAsync(filePath, { idempotent: true })),
  };
}
