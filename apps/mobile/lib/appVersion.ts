import Constants from "expo-constants";

/**
 * Which app this is, for About and support reports: the version, the native build (the
 * binary's own CFBundleVersion or versionCode; none in Expo Go) and the over-the-air
 * update it runs (none when it runs the update built into the binary).
 */
type AppVersion = { version: string; build: string | null; update: string | null };

type UpdatesModule = { updateId: string | null; isEmbeddedLaunch: boolean };

/** expo-updates when this binary has its native module (a dev client may not). */
function loadUpdates(): UpdatesModule | null {
  try {
    const { requireOptionalNativeModule } =
      // eslint-disable-next-line @typescript-eslint/no-require-imports -- lazy: plain tests and old dev clients
      require("expo-modules-core") as typeof import("expo-modules-core");
    if (!requireOptionalNativeModule("ExpoUpdates")) return null;
    // eslint-disable-next-line @typescript-eslint/no-require-imports -- only once its native module is in this build
    return require("expo-updates") as UpdatesModule;
  } catch {
    return null;
  }
}

export function appVersion(): AppVersion {
  const ios = Constants.platform?.ios?.buildNumber ?? null;
  const androidCode = (Constants.platform?.android as { versionCode?: number | null } | undefined)?.versionCode;
  const updates = loadUpdates();
  const updateId = updates && !updates.isEmbeddedLaunch ? updates.updateId : null;
  return {
    version: Constants.expoConfig?.version ?? "1.0.0",
    build: ios || (androidCode != null ? String(androidCode) : null),
    // The first block of the id is enough to find the update on EAS.
    update: updateId ? updateId.split("-")[0] : null,
  };
}

/** "1.0.0 (42)": the version with its native build, when there is one. */
export function versionLabel({ version, build }: AppVersion): string {
  return build ? `${version} (${build})` : version;
}
