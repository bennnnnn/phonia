/**
 * Persist Settings → Haptics. Not a secret — a file, like the appearance
 * preference, so a simulator build without Keychain entitlements keeps it.
 */

import { prefFilePath, readPrefFile, writePrefFile } from "@/lib/filePrefs";

const FILE_NAME = "recall.haptics.txt";

export async function getHapticsPreference(): Promise<boolean> {
  return (await readPrefFile(prefFilePath(FILE_NAME)))?.trim() !== "off";
}

export async function setHapticsPreference(enabled: boolean): Promise<void> {
  await writePrefFile(prefFilePath(FILE_NAME), enabled ? "on" : "off");
}
