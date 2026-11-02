import {
  cacheDirectory,
  deleteAsync,
  EncodingType,
  writeAsStringAsync,
} from "expo-file-system/legacy";
import { Share } from "react-native";

import { newAccountFile } from "@/lib/accountFiles";
import { shareLocalFile } from "@/lib/shareFile";

const EXPORT_TITLE = "recall-export.json";

/** Pretty-print compact export JSON for sharing when the payload is small enough. */
export function formatExportJsonForShare(raw: string): string {
  const maxPrettyBytes = 500_000;
  if (raw.length > maxPrettyBytes) {
    return raw;
  }
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

/**
 * The export as a file in the share sheet. React Native's Share sends a file only on iOS
 * (Android ignores `url`, so nothing was shared there); shareLocalFile hands the file over
 * on both, and throws on a build that cannot share files so the screen can say so.
 */
export async function shareAccountExport(payload: string): Promise<void> {
  const dir = cacheDirectory;
  if (!dir) {
    await Share.share({ message: payload, title: EXPORT_TITLE });
    return;
  }

  const fileUri = newAccountFile("export", "json");
  try {
    await writeAsStringAsync(fileUri, payload, { encoding: EncodingType.UTF8 });
    await shareLocalFile(fileUri, { title: EXPORT_TITLE, mimeType: "application/json" });
  } finally {
    // The sheet has closed and the receiving app holds its own copy; sign-out
    // still sweeps one an interrupted export left behind.
    await deleteAsync(fileUri, { idempotent: true }).catch(() => undefined);
  }
}
