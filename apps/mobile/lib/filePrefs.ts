/**
 * Non-secret preference persistence, on the filesystem: Keychain writes fail on
 * unsigned simulator builds (errSecMissingEntitlement / -34018).
 */
import {
  deleteAsync,
  documentDirectory,
  getInfoAsync,
  readAsStringAsync,
  writeAsStringAsync,
} from "expo-file-system/legacy";

import { readTextFileSync } from "@/lib/syncFileRead";

export function prefFilePath(fileName: string): string | null {
  if (!documentDirectory) return null;
  return `${documentDirectory}${fileName}`;
}

export function safePrefUserId(userId: string): string {
  return userId.replace(/[^a-zA-Z0-9._-]/g, "_") || "default";
}

export async function readPrefFile(path: string | null): Promise<string | null> {
  if (!path) return null;
  try {
    const info = await getInfoAsync(path);
    if (!info.exists) return null;
    return await readAsStringAsync(path);
  } catch {
    return null;
  }
}

/** The pref read synchronously: only for what the first frame needs (`lib/launchPrefs.ts`). */
export function readPrefFileSync(fileName: string): string | null {
  return readTextFileSync("document", fileName);
}

export async function writePrefFile(path: string | null, value: string): Promise<void> {
  if (!path) return;
  try {
    await writeAsStringAsync(path, value);
  } catch {
    /* best-effort — in-memory state from the caller still applies this session */
  }
}

export async function deletePrefFile(path: string | null): Promise<void> {
  if (!path) return;
  try {
    await deleteAsync(path, { idempotent: true });
  } catch {
    /* best-effort */
  }
}
