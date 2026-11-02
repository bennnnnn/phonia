/** Types for `easBuildConfig.js`, the EAS build profile helpers. The helpers stay CJS
 * so Expo's isolated app.config compile can require them. */

type BuildEnvironment = Record<string, string | undefined>;

export function includeDevClientPlugin(buildProfile: string): boolean;

/** EAS Build sets EAS_BUILD_PROFILE; an over-the-air update sets RECALL_UPDATE_PROFILE
 * so its bundle is checked like a release build of the same profile. */
export function releaseProfile(env: BuildEnvironment): string;

/** EAS Update's address for the project. Without a project ID, updates stay off. */
export function updatesUrl(projectId: string | undefined): string | null;

export function requirePublicApiUrlForReleaseBuild(
  buildProfile: string,
  apiUrl: string | undefined,
): void;

/** `pnpm ios:sim` sets RECALL_IOS_SIMULATOR=1: a local simulator build without Sign in
 * with Apple. A release build never drops it. */
export function simulatorWithoutAppleSignIn(buildProfile: string, env: BuildEnvironment): boolean;

/** Options for `@sentry/react-native/expo`: the org and project its upload step names. */
export function sentryPluginOptions(env: BuildEnvironment): {
  organization?: string;
  project?: string;
};

export function requireReleaseBuildSecrets(
  buildProfile: string,
  buildPlatform: string,
  env: BuildEnvironment,
): void;
