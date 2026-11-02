import type { ConfigContext, ExpoConfig } from "expo/config";

import appJson from "./app.json";
import {
  includeDevClientPlugin,
  releaseProfile,
  requireReleaseBuildSecrets,
  sentryPluginOptions,
  simulatorWithoutAppleSignIn,
  updatesUrl,
} from "./lib/easBuildConfig.js";

function iosUrlSchemeFromClientId(iosClientId: string): string | null {
  const trimmed = iosClientId.trim();
  if (!trimmed.endsWith(".apps.googleusercontent.com")) return null;
  return `com.googleusercontent.apps.${trimmed.replace(".apps.googleusercontent.com", "")}`;
}

export default ({ config }: ConfigContext): ExpoConfig => {
  const base = appJson.expo as ExpoConfig;
  const buildProfile = releaseProfile(process.env);
  requireReleaseBuildSecrets(
    buildProfile,
    process.env.EAS_BUILD_PLATFORM ?? "",
    process.env,
  );
  const includeDevClient = includeDevClientPlugin(buildProfile);
  const appleSignIn = !simulatorWithoutAppleSignIn(buildProfile, process.env);
  const sentryPlugin: [string, ReturnType<typeof sentryPluginOptions>] | null =
    process.env.EXPO_PUBLIC_SENTRY_DSN?.trim()
      ? ["@sentry/react-native/expo", sentryPluginOptions(process.env)]
      : null;
  const plugins: ExpoConfig["plugins"] = [
    // Registered first so its entitlements mod runs last, after the Apple plugin's.
    ...(appleSignIn ? [] : (["./plugins/withoutAppleSignIn.js"] as const)),
    ...(includeDevClient ? (["expo-dev-client"] as const) : []),
    ...(sentryPlugin ? [sentryPlugin] : []),
    ...(base.plugins ?? []),
  ];
  const iosUrlScheme = iosUrlSchemeFromClientId(
    process.env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID ?? "",
  );
  const webClientId = process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID ?? "";

  if (webClientId && !/your-google/i.test(webClientId)) {
    const googlePluginConfig: { iosUrlScheme?: string } = {};
    if (iosUrlScheme) googlePluginConfig.iosUrlScheme = iosUrlScheme;
    plugins.push(["@react-native-google-signin/google-signin", googlePluginConfig]);
    if (iosUrlScheme) plugins.push("./plugins/googleSignInPodfile.js");
  }

  const iosInfoPlist: Record<string, unknown> = {
    ...(base.ios?.infoPlist ?? {}),
  };
  if (includeDevClient) {
    iosInfoPlist.NSAppTransportSecurity = { NSAllowsLocalNetworking: true };
  }

  const projectId = process.env.EXPO_PUBLIC_EAS_PROJECT_ID;
  const updatesFrom = updatesUrl(projectId);

  return {
    ...config,
    ...base,
    plugins,
    // Over-the-air JS updates (EAS Update). Which builds may take an update is
    // decided by app.json's runtimeVersion: bump `version` with any native change.
    updates: updatesFrom ? { ...base.updates, url: updatesFrom } : base.updates,
    ios: {
      ...base.ios,
      usesAppleSignIn: appleSignIn,
      infoPlist: iosInfoPlist,
    },
    extra: {
      ...base.extra,
      appleSignIn,
      eas: {
        projectId,
      },
    },
  };
};
