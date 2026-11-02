import Constants, { ExecutionEnvironment } from "expo-constants";

function isDevClientBuild(): boolean {
  try {
    // Optional — present after `expo install expo-dev-client` + native rebuild.
    const devClient = require("expo-dev-client") as {
      isDevelopmentBuild?: () => boolean;
    };
    return devClient.isDevelopmentBuild?.() === true;
  } catch {
    return false;
  }
}

/** True when running inside the Expo Go app (not a dev/production build). */
export function isExpoGo(): boolean {
  if (isDevClientBuild()) return false;

  const env = Constants.executionEnvironment;
  if (
    env === ExecutionEnvironment.Bare ||
    env === ExecutionEnvironment.Standalone
  ) {
    return false;
  }

  // StoreClient covers Expo Go and some dev clients; only Expo Go sets appOwnership.
  return Constants.appOwnership === "expo";
}

/**
 * False on a simulator or emulator, null when this binary has no ExpoDevice
 * module. Never import expo-device: Metro reports its requireNativeModule as a
 * fatal even inside try/catch, so probe the native registry instead.
 */
export function isPhysicalDevice(): boolean | null {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports -- lazy, like expo-dev-client above: plain-Node tests import this file
    const { requireOptionalNativeModule } = require("expo-modules-core") as typeof import("expo-modules-core");
    const device = requireOptionalNativeModule<{ isDevice?: boolean }>("ExpoDevice");
    return typeof device?.isDevice === "boolean" ? device.isDevice : null;
  } catch {
    return null;
  }
}

/** Device GPS is only available in dev/production builds with native Info.plist keys. */
export function canUseDeviceLocation(): boolean {
  return !isExpoGo();
}
