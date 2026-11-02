/** Hand a local file to the system share sheet on iOS and Android. */

import { Platform, Share } from "react-native";

import { isShareCancelled } from "@/lib/shareCancelled";
import { SharingUnavailableError } from "@/lib/shareUnavailable";

type SharingModule = {
  shareAsync: (url: string, options?: { mimeType?: string; UTI?: string; dialogTitle?: string }) => Promise<void>;
};

/**
 * expo-sharing, when this build has its native module. Loaded lazily: its JS
 * calls requireNativeModule on import, so a dev client built before it was
 * added would otherwise crash every screen that can share.
 */
function loadSharing(): SharingModule | null {
  try {
    const { requireOptionalNativeModule } =
      // eslint-disable-next-line @typescript-eslint/no-require-imports -- lazy, like expo-sharing below
      require("expo-modules-core") as typeof import("expo-modules-core");
    if (!requireOptionalNativeModule("ExpoSharing")) return null;
    // eslint-disable-next-line @typescript-eslint/no-require-imports -- only once its native module is in this build
    return require("expo-sharing") as SharingModule;
  } catch {
    return null;
  }
}

type ShareRoute = "expo-sharing" | "rn-share" | "unavailable";

/**
 * How a file reaches the share sheet. expo-sharing hands over the file on
 * both platforms. React Native's Share sends a file only on iOS (`url`);
 * Android ignores `url` and would send the cache path as text, so Android
 * without expo-sharing cannot share a file at all.
 */
export function shareRoute(platform: string, hasSharing: boolean): ShareRoute {
  if (hasSharing) return "expo-sharing";
  return platform === "ios" ? "rn-share" : "unavailable";
}

/**
 * Open the share sheet for a `file://` URI. A dismissed sheet is not an
 * error; a build that cannot share a file on this platform throws `SharingUnavailableError`.
 */
export async function shareLocalFile(
  localUri: string,
  options: { title: string; mimeType?: string | null; uti?: string },
): Promise<void> {
  const sharing = loadSharing();
  const route = shareRoute(Platform.OS, sharing != null);
  if (route === "unavailable") {
    throw new SharingUnavailableError();
  }
  try {
    if (route === "expo-sharing" && sharing) {
      await sharing.shareAsync(localUri, {
        dialogTitle: options.title,
        ...(options.mimeType ? { mimeType: options.mimeType } : {}),
        // iOS reads the file's type from its UTI; without it a PDF can open as plain data.
        ...(options.uti ? { UTI: options.uti } : {}),
      });
    } else {
      await Share.share({ url: localUri, title: options.title });
    }
  } catch (error) {
    if (isShareCancelled(error)) return;
    throw error;
  }
}
