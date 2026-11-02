/**
 * Stable per-install id for push token re-bind checks.
 *
 * Expo removed `Constants.installationId`; we generate once and persist on the
 * filesystem (not SecureStore — this is not a secret; Keychain can fail on
 * entitlement-less simulator builds).
 */

import * as Crypto from "expo-crypto";
import {
  documentDirectory,
  getInfoAsync,
  readAsStringAsync,
  writeAsStringAsync,
} from "expo-file-system/legacy";

const FILE_NAME = "recall.installation-id.txt";

function filePath(): string | null {
  if (!documentDirectory) return null;
  return `${documentDirectory}${FILE_NAME}`;
}

export async function getInstallationId(): Promise<string | null> {
  const path = filePath();
  if (!path) return null;
  try {
    const info = await getInfoAsync(path);
    if (info.exists) {
      const raw = (await readAsStringAsync(path)).trim();
      if (raw) return raw;
    }
  } catch {
    /* fall through to create */
  }
  try {
    const next = Crypto.randomUUID();
    await writeAsStringAsync(path, next);
    return next;
  } catch {
    return null;
  }
}
