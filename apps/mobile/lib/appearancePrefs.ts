/**
 * Persist light/dark/system appearance. Not a secret — use the filesystem,
 * not SecureStore (Keychain). A linker-signed / entitlement-less simulator
 * build rejects Keychain writes with errSecMissingEntitlement (-34018), which
 * used to silently drop the user's preference on next launch.
 */

import {
  normalizeAppearancePreference,
  type AppearancePreference,
} from "@/lib/appearance";
import { prefFilePath, readPrefFile, readPrefFileSync, writePrefFile } from "@/lib/filePrefs";

const FILE_NAME = "recall.appearance-preference.txt";

let cachedPreference: AppearancePreference | null = null;

function filePath(): string | null {
  return prefFilePath(FILE_NAME);
}

/** The saved preference, read before the first render; null when there is no file yet. */
export function readAppearancePreferenceSync(): AppearancePreference | null {
  if (cachedPreference !== null) return cachedPreference;
  const fromFile = readPrefFileSync(FILE_NAME);
  if (fromFile === null) return null;
  cachedPreference = normalizeAppearancePreference(fromFile);
  return cachedPreference;
}

export async function getAppearancePreference(): Promise<AppearancePreference> {
  if (cachedPreference !== null) return cachedPreference;
  cachedPreference = normalizeAppearancePreference(await readPrefFile(filePath()));
  return cachedPreference;
}

export async function setAppearancePreference(
  preference: AppearancePreference,
): Promise<void> {
  cachedPreference = preference;
  await writePrefFile(filePath(), preference);
}

/** Test helper — reset in-memory cache between cases. */
export function resetAppearancePreferenceCache(): void {
  cachedPreference = null;
}
