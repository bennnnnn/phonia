import { isExpoGo } from "@/lib/expoRuntime";

let cached: boolean | null = null;

/**
 * True when the Skia native module is linked — dev/production builds that
 * include @shopify/react-native-skia. Expo Go never has it, and a stale dev
 * client built before the dep was added has the JS package but no native
 * module, so probe a cheap native call instead of trusting the import.
 */
export function isSkiaAvailable(): boolean {
  if (cached != null) return cached;
  if (isExpoGo()) {
    cached = false;
    return cached;
  }
  try {
    const { Skia } =
      require("@shopify/react-native-skia") as typeof import("@shopify/react-native-skia");
    cached = Skia.Path.Make() != null;
  } catch {
    cached = false;
  }
  return cached;
}
