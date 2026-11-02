/**
 * This install's native push token (APNs or FCM), read without the round
 * trip to Expo's push service that the Expo token takes. Only its
 * fingerprint leaves this module: enough to tell that the token changed.
 */
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

import { isExpoGo } from "@/lib/expoRuntime";

/** How long the native token may take before the caller goes on without it. */
const DEVICE_TOKEN_WAIT_MS = 3_000;

/** FNV-1a, 32 bits: a token's stand-in, never the token itself. */
export function fingerprint(text: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {
    hash = Math.imul(hash ^ text.charCodeAt(i), 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, "0");
}

/** The token's fingerprint; null where it cannot be read (Expo Go, web, a failed or slow read). */
export async function devicePushTokenFingerprint(): Promise<string | null> {
  if (Platform.OS === "web" || isExpoGo()) return null;
  const token = await new Promise<string | null>((resolve) => {
    const timer = setTimeout(() => resolve(null), DEVICE_TOKEN_WAIT_MS);
    Notifications.getDevicePushTokenAsync().then(
      ({ data }) => {
        clearTimeout(timer);
        resolve(typeof data === "string" && data ? data : null);
      },
      () => {
        clearTimeout(timer);
        resolve(null);
      },
    );
  });
  return token === null ? null : fingerprint(token);
}
