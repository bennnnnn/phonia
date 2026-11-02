type DeviceSessionFields = {
  device_label?: string;
  platform?: string;
};

/**
 * Never static-import expo-device: its JS calls requireNativeModule and Metro
 * can treat a missing native module as fatal even inside try/catch.
 * Also lazy-require react-native / expo-modules-core so lib Jest tests that
 * import api/client can load this module in Node.
 */
export function deviceSessionFields(): DeviceSessionFields {
  let platform: string | undefined;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports -- lazy, so lib tests load this module in Node
    const { Platform } = require("react-native") as typeof import("react-native");
    platform = Platform.OS;
  } catch {
    platform = undefined;
  }
  try {
    const { requireOptionalNativeModule } =
      // eslint-disable-next-line @typescript-eslint/no-require-imports -- lazy, so lib tests load this module in Node
      require("expo-modules-core") as typeof import("expo-modules-core");
    const device = requireOptionalNativeModule<{
      deviceName?: string;
      modelName?: string;
    }>("ExpoDevice");
    const raw = device?.deviceName || device?.modelName;
    const label = typeof raw === "string" ? raw.trim().slice(0, 80) : "";
    if (label) {
      return platform ? { device_label: label, platform } : { device_label: label };
    }
  } catch {
    // Missing ExpoDevice or ESM require must not break sign-in or Jest.
  }
  return platform ? { platform } : {};
}
