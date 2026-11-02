/** EAS build profile helpers. CJS so Expo's isolated app.config compile can require it. */

const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "::1"]);

function includeDevClientPlugin(buildProfile) {
  return !buildProfile || buildProfile === "development";
}

/** EAS Build sets EAS_BUILD_PROFILE; an over-the-air update sets RECALL_UPDATE_PROFILE
 * so its bundle is checked like a release build of the same profile. */
function releaseProfile(env) {
  return env.EAS_BUILD_PROFILE?.trim() || env.RECALL_UPDATE_PROFILE?.trim() || "";
}

/** EAS Update's address for the project. Without a project ID, updates stay off. */
function updatesUrl(projectId) {
  const id = projectId?.trim();
  return id ? `https://u.expo.dev/${id}` : null;
}

function assertReleaseApiUrl(apiUrl, envName) {
  const trimmed = apiUrl?.trim();
  if (!trimmed) {
    throw new Error(`${envName} must be set to a public https:// URL`);
  }
  let parsed;
  try {
    parsed = new URL(trimmed);
  } catch {
    throw new Error(`${envName} must be a valid https:// URL, got "${trimmed}"`);
  }
  const host = parsed.hostname.toLowerCase();
  if (parsed.protocol !== "https:" || LOOPBACK_HOSTS.has(host)) {
    throw new Error(
      `${envName} must be a public https:// URL for release builds, got "${trimmed}"`,
    );
  }
}

function requirePublicApiUrlForReleaseBuild(buildProfile, apiUrl) {
  if (buildProfile !== "production" && buildProfile !== "preview") return;
  try {
    assertReleaseApiUrl(apiUrl, "EXPO_PUBLIC_API_URL");
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(
      `${message}. Set EXPO_PUBLIC_API_URL in EAS secrets for production and preview builds`,
    );
  }
}

/** `pnpm ios:sim` sets RECALL_IOS_SIMULATOR=1: a local simulator build without Sign in
 * with Apple, whose entitlement makes Expo demand a signing certificate even for a
 * simulator. A release build never drops it. */
function simulatorWithoutAppleSignIn(buildProfile, env) {
  if (env.RECALL_IOS_SIMULATOR?.trim() !== "1") return false;
  if (buildProfile === "production" || buildProfile === "preview") {
    throw new Error(
      `RECALL_IOS_SIMULATOR is for local simulator builds, not a ${buildProfile} build`,
    );
  }
  return true;
}

/** With a DSN, a release build uploads source maps and debug symbols to Sentry, and
 * Sentry's Xcode and Gradle steps fail the build at its very end when that upload fails.
 * Checked on the EAS worker only (EAS_BUILD): the CLI resolves this config on a laptop or
 * in CI without Secret-visibility variables, where SENTRY_AUTH_TOKEN belongs.
 * SENTRY_DISABLE_AUTO_UPLOAD=true, Sentry's own switch, ships without the upload. */
function missingSentryUploadSecrets(env) {
  if (!env.EXPO_PUBLIC_SENTRY_DSN?.trim() || !env.EAS_BUILD?.trim()) return [];
  if (env.SENTRY_DISABLE_AUTO_UPLOAD?.trim() === "true") return [];
  return ["SENTRY_ORG", "SENTRY_PROJECT", "SENTRY_AUTH_TOKEN"].filter(
    (key) => !env[key]?.trim(),
  );
}

/** Options for `@sentry/react-native/expo`: the org and project its upload step names. */
function sentryPluginOptions(env) {
  const options = {};
  const organization = env.SENTRY_ORG?.trim();
  const project = env.SENTRY_PROJECT?.trim();
  if (organization) options.organization = organization;
  if (project) options.project = project;
  return options;
}

function requireReleaseBuildSecrets(buildProfile, buildPlatform, env) {
  if (buildProfile !== "production" && buildProfile !== "preview") return;

  requirePublicApiUrlForReleaseBuild(buildProfile, env.EXPO_PUBLIC_API_URL);
  const required = [
    ["EXPO_PUBLIC_EAS_PROJECT_ID", env.EXPO_PUBLIC_EAS_PROJECT_ID],
    ["EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID", env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID],
  ];
  if (buildPlatform !== "android") {
    required.push(
      ["EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID", env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID],
      ["EXPO_PUBLIC_REVENUECAT_IOS_API_KEY", env.EXPO_PUBLIC_REVENUECAT_IOS_API_KEY],
    );
  }
  if (buildPlatform !== "ios") {
    required.push([
      "EXPO_PUBLIC_REVENUECAT_ANDROID_API_KEY",
      env.EXPO_PUBLIC_REVENUECAT_ANDROID_API_KEY,
    ]);
  }

  const missing = required.filter(([, value]) => !value?.trim()).map(([key]) => key);
  const missingSentry = missingSentryUploadSecrets(env);
  if (missing.length > 0 || missingSentry.length > 0) {
    const sentryHint =
      missingSentry.length > 0
        ? ". EXPO_PUBLIC_SENTRY_DSN is set, so the build uploads source maps to Sentry;" +
          " set the Sentry values or SENTRY_DISABLE_AUTO_UPLOAD=true"
        : "";
    throw new Error(
      `Missing EAS secrets for ${buildProfile} ${buildPlatform || "release"} build: ${[...missing, ...missingSentry].join(", ")}${sentryHint}`,
    );
  }
}

module.exports = {
  includeDevClientPlugin,
  releaseProfile,
  updatesUrl,
  requirePublicApiUrlForReleaseBuild,
  requireReleaseBuildSecrets,
  sentryPluginOptions,
  simulatorWithoutAppleSignIn,
};
