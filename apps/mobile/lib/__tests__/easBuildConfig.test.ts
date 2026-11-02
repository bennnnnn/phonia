import {
  includeDevClientPlugin,
  releaseProfile,
  requirePublicApiUrlForReleaseBuild,
  requireReleaseBuildSecrets,
  sentryPluginOptions,
  simulatorWithoutAppleSignIn,
  updatesUrl,
} from "@/lib/easBuildConfig";

describe("easBuildConfig", () => {
  it("drops Sign in with Apple only for a local simulator build", () => {
    expect(simulatorWithoutAppleSignIn("", {})).toBe(false);
    expect(simulatorWithoutAppleSignIn("", { RECALL_IOS_SIMULATOR: "1" })).toBe(true);
    expect(simulatorWithoutAppleSignIn("development", { RECALL_IOS_SIMULATOR: "1" })).toBe(true);
    expect(() => simulatorWithoutAppleSignIn("production", { RECALL_IOS_SIMULATOR: "1" })).toThrow(
      /not a production build/,
    );
    expect(() => simulatorWithoutAppleSignIn("preview", { RECALL_IOS_SIMULATOR: "1" })).toThrow(
      /not a preview build/,
    );
    expect(simulatorWithoutAppleSignIn("production", {})).toBe(false);
  });

  it("includes dev client only for local/dev EAS profile", () => {
    expect(includeDevClientPlugin("")).toBe(true);
    expect(includeDevClientPlugin("development")).toBe(true);
    expect(includeDevClientPlugin("preview")).toBe(false);
    expect(includeDevClientPlugin("production")).toBe(false);
  });

  it("requires a public HTTPS EXPO_PUBLIC_API_URL for release builds", () => {
    expect(() => requirePublicApiUrlForReleaseBuild("development", undefined)).not.toThrow();
    expect(() =>
      requirePublicApiUrlForReleaseBuild("development", "http://localhost:8000"),
    ).not.toThrow();
    expect(() =>
      requirePublicApiUrlForReleaseBuild("production", "https://api.example.com"),
    ).not.toThrow();
    expect(() => requirePublicApiUrlForReleaseBuild("production", undefined)).toThrow(
      /EXPO_PUBLIC_API_URL/,
    );
    expect(() => requirePublicApiUrlForReleaseBuild("preview", "  ")).toThrow(
      /EXPO_PUBLIC_API_URL/,
    );
    expect(() =>
      requirePublicApiUrlForReleaseBuild("production", "http://api.example.com"),
    ).toThrow(/https:\/\//);
    expect(() =>
      requirePublicApiUrlForReleaseBuild("preview", "https://localhost"),
    ).toThrow(/https:\/\//);
    expect(() =>
      requirePublicApiUrlForReleaseBuild("production", "https://127.0.0.1"),
    ).toThrow(/https:\/\//);
    expect(() => requirePublicApiUrlForReleaseBuild("production", "not-a-url")).toThrow(
      /valid https:\/\//,
    );
  });

  const completeEnv = {
    EXPO_PUBLIC_API_URL: "https://api.recall.test",
    EXPO_PUBLIC_EAS_PROJECT_ID: "project-id",
    EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID: "web.apps.googleusercontent.com",
    EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID: "ios.apps.googleusercontent.com",
    EXPO_PUBLIC_REVENUECAT_IOS_API_KEY: "appl_test",
    EXPO_PUBLIC_REVENUECAT_ANDROID_API_KEY: "goog_test",
  };

  it("requires beta-critical service keys for release builds", () => {
    expect(() =>
      requireReleaseBuildSecrets("production", "ios", completeEnv),
    ).not.toThrow();
    expect(() =>
      requireReleaseBuildSecrets("production", "ios", {
        ...completeEnv,
        EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID: "",
        EXPO_PUBLIC_REVENUECAT_IOS_API_KEY: undefined,
      }),
    ).toThrow(/EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID.*EXPO_PUBLIC_REVENUECAT_IOS_API_KEY/);
  });

  it("requires only platform-relevant RevenueCat keys", () => {
    expect(() =>
      requireReleaseBuildSecrets("preview", "android", {
        ...completeEnv,
        EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID: undefined,
        EXPO_PUBLIC_REVENUECAT_IOS_API_KEY: undefined,
      }),
    ).not.toThrow();
    expect(() =>
      requireReleaseBuildSecrets("preview", "android", {
        ...completeEnv,
        EXPO_PUBLIC_REVENUECAT_ANDROID_API_KEY: "",
      }),
    ).toThrow(/EXPO_PUBLIC_REVENUECAT_ANDROID_API_KEY/);
  });

  const sentryUpload = {
    EXPO_PUBLIC_SENTRY_DSN: "https://key@o1.ingest.sentry.io/2",
    EAS_BUILD: "true",
    SENTRY_ORG: "recall",
    SENTRY_PROJECT: "recall-mobile",
    SENTRY_AUTH_TOKEN: "sntrys_test",
  };

  it("requires Sentry upload credentials when an EAS release build has a DSN", () => {
    expect(() =>
      requireReleaseBuildSecrets("production", "ios", { ...completeEnv, ...sentryUpload }),
    ).not.toThrow();
    expect(() =>
      requireReleaseBuildSecrets("preview", "android", {
        ...completeEnv,
        ...sentryUpload,
        SENTRY_ORG: "",
        SENTRY_AUTH_TOKEN: undefined,
      }),
    ).toThrow(/SENTRY_ORG, SENTRY_AUTH_TOKEN.*SENTRY_DISABLE_AUTO_UPLOAD=true/);
    // Reported with the other missing secrets in one message.
    expect(() =>
      requireReleaseBuildSecrets("production", "ios", {
        ...completeEnv,
        ...sentryUpload,
        EXPO_PUBLIC_EAS_PROJECT_ID: "",
        SENTRY_PROJECT: " ",
      }),
    ).toThrow(/EXPO_PUBLIC_EAS_PROJECT_ID, SENTRY_PROJECT/);
  });

  it("skips the Sentry check without a DSN, off the EAS worker, or with uploads off", () => {
    const noCredentials = {
      ...completeEnv,
      ...sentryUpload,
      SENTRY_ORG: undefined,
      SENTRY_PROJECT: undefined,
      SENTRY_AUTH_TOKEN: undefined,
    };
    expect(() =>
      requireReleaseBuildSecrets("production", "ios", {
        ...noCredentials,
        EXPO_PUBLIC_SENTRY_DSN: "  ",
      }),
    ).not.toThrow();
    // eas-cli resolves the config locally without EAS_BUILD or Secret variables.
    expect(() =>
      requireReleaseBuildSecrets("production", "ios", { ...noCredentials, EAS_BUILD: undefined }),
    ).not.toThrow();
    expect(() =>
      requireReleaseBuildSecrets("production", "ios", {
        ...noCredentials,
        SENTRY_DISABLE_AUTO_UPLOAD: "true",
      }),
    ).not.toThrow();
    expect(() => requireReleaseBuildSecrets("development", "ios", noCredentials)).not.toThrow();
  });

  it("names the Sentry org and project for the upload step when they are set", () => {
    expect(sentryPluginOptions(sentryUpload)).toEqual({
      organization: "recall",
      project: "recall-mobile",
    });
    expect(sentryPluginOptions({ SENTRY_ORG: " recall ", SENTRY_PROJECT: "" })).toEqual({
      organization: "recall",
    });
    expect(sentryPluginOptions({})).toEqual({});
  });

  it("does not require release secrets for development builds", () => {
    expect(() => requireReleaseBuildSecrets("development", "ios", {})).not.toThrow();
  });

  it("checks an over-the-air update like a release build of the same profile", () => {
    expect(releaseProfile({ EAS_BUILD_PROFILE: "preview" })).toBe("preview");
    expect(releaseProfile({ RECALL_UPDATE_PROFILE: "production" })).toBe("production");
    expect(
      releaseProfile({ EAS_BUILD_PROFILE: "preview", RECALL_UPDATE_PROFILE: "production" }),
    ).toBe("preview");
    expect(releaseProfile({})).toBe("");
    // A production update without its API URL fails instead of shipping a broken bundle.
    const profile = releaseProfile({ RECALL_UPDATE_PROFILE: "production" });
    expect(() => requireReleaseBuildSecrets(profile, "", {})).toThrow(/EXPO_PUBLIC_API_URL/);
  });

  it("points updates at EAS Update only when the project ID is known", () => {
    expect(updatesUrl("abc-123")).toBe("https://u.expo.dev/abc-123");
    expect(updatesUrl(" abc-123 ")).toBe("https://u.expo.dev/abc-123");
    expect(updatesUrl(undefined)).toBeNull();
    expect(updatesUrl("  ")).toBeNull();
  });
});
