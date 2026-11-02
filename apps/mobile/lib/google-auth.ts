import { Platform } from "react-native";

import { config, isGoogleSignInConfigured, isGoogleWebClientConfigured } from "@/lib/config";
import { isExpoGo } from "@/lib/expoRuntime";

export { isExpoGo } from "@/lib/expoRuntime";

const EXPO_GO_MESSAGE =
  "Google Sign-In does not work in Expo Go. Build and run the Recall app on your simulator or device:\n\ncd apps/mobile && pnpm expo run:ios";

type GoogleSignInModule = typeof import("@react-native-google-signin/google-signin");

let configured = false;
let googleModule: GoogleSignInModule | null = null;

async function loadGoogleSignIn(): Promise<GoogleSignInModule> {
  if (googleModule) return googleModule;
  try {
    googleModule = await import("@react-native-google-signin/google-signin");
    return googleModule;
  } catch {
    throw new Error(
      "Google Sign-In native module is missing. Rebuild the dev client: cd apps/mobile && pnpm expo run:ios",
    );
  }
}

async function ensureGoogleConfigured() {
  if (configured) return;
  if (!isGoogleWebClientConfigured()) {
    throw new Error(
      "Google Sign-In is not configured. Set EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID in apps/mobile/.env, then rebuild.",
    );
  }
  if (Platform.OS === "ios" && !isGoogleSignInConfigured()) {
    throw new Error(
      "Google Sign-In is not configured. Set EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID in apps/mobile/.env, then rebuild.",
    );
  }
  const { GoogleSignin } = await loadGoogleSignIn();
  GoogleSignin.configure({
    webClientId: config.googleWebClientId,
    ...(Platform.OS === "ios" ? { iosClientId: config.googleIosClientId } : {}),
    offlineAccess: false,
  });
  configured = true;
}

/** Map native / Metro errors to the login screen's own copy: a key it words, never the
 * error's English (the native SDK's messages are English in every language). */
export function formatGoogleSignInError(error: unknown): string {
  const message =
    error instanceof Error ? error.message : typeof error === "string" ? error : "";
  if (/could not load bundle/i.test(message)) {
    return "bundle_load_failed";
  }
  if (/RNGoogleSignin|native module/i.test(message)) {
    return "native_module_missing";
  }
  if (/not configured/i.test(message)) {
    return "not_configured";
  }
  if (/DEVELOPER_ERROR|12500|10:/i.test(message)) {
    return "android_oauth_setup";
  }
  if (/cancel/i.test(message)) {
    return "cancelled";
  }
  if (/play services/i.test(message)) {
    return "play_services_missing";
  }
  return "generic";
}

/** Recall account sign-in — identity only (an ID token, no extra OAuth scopes). */
async function signInWithGoogleNative(): Promise<string> {
  await ensureGoogleConfigured();
  const { GoogleSignin, statusCodes } = await loadGoogleSignIn();

  try {
    if (Platform.OS === "android") {
      await GoogleSignin.hasPlayServices({ showPlayServicesUpdateDialog: true });
    }
    const response = await GoogleSignin.signIn();
    const idToken = response.data?.idToken;
    if (!idToken) {
      throw new Error("Google Sign-In did not return an ID token.");
    }
    return idToken;
  } catch (error: unknown) {
    const err = error as { code?: string; message?: string };
    if (err.code === statusCodes.SIGN_IN_CANCELLED) {
      throw new Error("Sign-in cancelled");
    }
    if (err.code === statusCodes.IN_PROGRESS) {
      throw new Error("Sign-in already in progress");
    }
    if (err.code === statusCodes.PLAY_SERVICES_NOT_AVAILABLE) {
      throw new Error("Google Play Services not available");
    }
    throw new Error(err.message ?? "Google Sign-In failed.");
  }
}

export async function signInWithGoogleIdToken(): Promise<string> {
  if (isExpoGo()) {
    throw new Error(EXPO_GO_MESSAGE);
  }
  return signInWithGoogleNative();
}

export async function signOutGoogle() {
  if (isExpoGo()) return;
  try {
    await ensureGoogleConfigured();
    const { GoogleSignin } = await loadGoogleSignIn();
    await GoogleSignin.signOut();
  } catch {
    // Best-effort
  }
}
