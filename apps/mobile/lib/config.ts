import Constants from "expo-constants";

/** Build-time settings. The API's URL comes from getApiUrl() below. */
export const config = {
  googleWebClientId:
    process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID ??
    "your-google-web-client-id.apps.googleusercontent.com",
  googleIosClientId:
    process.env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID ??
    "your-ios-client-id.apps.googleusercontent.com",
  devAuthEnabled: process.env.EXPO_PUBLIC_DEV_AUTH_ENABLED === "true",
  /** Settings → Help emails it; without one the help rows are hidden. */
  supportEmail: process.env.EXPO_PUBLIC_SUPPORT_EMAIL?.trim() || null,
} as const;

/** True when the Google OAuth web client ID is set (required on all platforms). */
export function isGoogleWebClientConfigured(): boolean {
  return !/your-google-web-client-id|your-google/i.test(config.googleWebClientId);
}

/** True when real Google OAuth client IDs are set (web + iOS for native sign-in). */
export function isGoogleSignInConfigured(): boolean {
  if (!isGoogleWebClientConfigured()) return false;
  return !/your-ios-client-id|your-ios/i.test(config.googleIosClientId);
}

export function getApiUrl(): string {
  // .env wins over app.json (app.json extra is fallback for EAS builds)
  if (process.env.EXPO_PUBLIC_API_URL) {
    return process.env.EXPO_PUBLIC_API_URL;
  }
  const extra = Constants.expoConfig?.extra as { apiUrl?: string } | undefined;
  return extra?.apiUrl ?? "http://localhost:8000";
}
