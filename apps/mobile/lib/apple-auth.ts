import Constants from "expo-constants";
import * as Crypto from "expo-crypto";
import { Platform } from "react-native";

import { isExpoGo } from "@/lib/expoRuntime";

type AppleAuthModule = typeof import("expo-apple-authentication");

let appleModule: AppleAuthModule | null | undefined;

async function loadAppleAuth(): Promise<AppleAuthModule> {
  if (appleModule) return appleModule;
  try {
    appleModule = await import("expo-apple-authentication");
    return appleModule;
  } catch {
    throw new Error(
      "Sign in with Apple native module is missing. Rebuild the dev client: cd apps/mobile && pnpm expo run:ios",
    );
  }
}

/** Sign in with Apple is iOS-only; never shown on Android. */
function isAppleSignInPlatform(): boolean {
  return Platform.OS === "ios";
}

/**
 * Show the Apple button on iOS; check availability when the user taps. A
 * `pnpm ios:sim` build leaves Sign in with Apple out, so it has no button. Expo Go
 * has none either: Apple signs its token for Expo Go's own bundle id
 * (host.exp.Exponent), which our server rightly refuses.
 */
export function shouldShowAppleSignInButton(): boolean {
  if (!isAppleSignInPlatform() || isExpoGo()) return false;
  const extra = Constants.expoConfig?.extra as { appleSignIn?: boolean } | undefined;
  return extra?.appleSignIn !== false;
}

type AppleSignInResult = {
  idToken: string;
  name: string | null;
  /** Raw nonce for the server; Apple's token carries its SHA-256. */
  nonce: string;
};

function newRawNonce(): string {
  return Array.from(Crypto.getRandomBytes(32), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

/** Map native / Metro errors to a key the login screen words, never the error's English. */
export function formatAppleSignInError(error: unknown): string {
  const message =
    error instanceof Error ? error.message : typeof error === "string" ? error : "";
  if (/could not load bundle/i.test(message)) {
    return "bundle_load_failed";
  }
  if (/native module/i.test(message)) {
    return "native_module_missing";
  }
  if (/cancel/i.test(message)) {
    return "cancelled";
  }
  if (/not available on this device/i.test(message)) {
    return "apple_unavailable_device";
  }
  return "generic";
}

export async function signInWithAppleCredentials(): Promise<AppleSignInResult> {
  if (!isAppleSignInPlatform()) {
    throw new Error("Sign in with Apple is only available on iOS.");
  }
  const AppleAuthentication = await loadAppleAuth();
  const available = await AppleAuthentication.isAvailableAsync();
  if (!available) {
    throw new Error(
      "Sign in with Apple is not available on this device. On the iOS Simulator, open Settings → Apple Account and sign in, then try again.",
    );
  }

  // The server only accepts an Apple token together with the raw value whose
  // hash the token carries, so a token copied from elsewhere cannot sign in.
  const nonce = newRawNonce();
  const hashedNonce = await Crypto.digestStringAsync(
    Crypto.CryptoDigestAlgorithm.SHA256,
    nonce,
  );
  const credential = await AppleAuthentication.signInAsync({
    requestedScopes: [
      AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
      AppleAuthentication.AppleAuthenticationScope.EMAIL,
    ],
    nonce: hashedNonce,
  });

  const idToken = credential.identityToken;
  if (!idToken) {
    throw new Error("Apple Sign-In did not return an identity token.");
  }

  const given = credential.fullName?.givenName?.trim();
  const family = credential.fullName?.familyName?.trim();
  const name = [given, family].filter(Boolean).join(" ") || null;

  return { idToken, name, nonce };
}

/**
 * Deleting an Apple-linked account asks Apple once more for a fresh
 * authorization code; the server trades it for the user's Apple token and
 * revokes that (App Review 5.1.1(v)). Cancelling the sheet means the user
 * changed their mind. When Sign in with Apple cannot run here (Android, a
 * build without it), the delete goes ahead without a code.
 */
export type AppleDeleteConsent =
  | { kind: "code"; code: string }
  | { kind: "cancelled" }
  | { kind: "unavailable" };

function isAppleCancel(error: unknown): boolean {
  const code = (error as { code?: unknown } | null)?.code;
  return code === "ERR_REQUEST_CANCELED" || formatAppleSignInError(error) === "cancelled";
}

export async function appleConsentForAccountDelete(): Promise<AppleDeleteConsent> {
  if (!isAppleSignInPlatform()) return { kind: "unavailable" };
  try {
    const AppleAuthentication = await loadAppleAuth();
    if (!(await AppleAuthentication.isAvailableAsync())) return { kind: "unavailable" };
    // No scopes: only the authorization code is needed, nothing about the user.
    const credential = await AppleAuthentication.signInAsync({ requestedScopes: [] });
    const code = credential.authorizationCode?.trim();
    return code ? { kind: "code", code } : { kind: "unavailable" };
  } catch (error) {
    return isAppleCancel(error) ? { kind: "cancelled" } : { kind: "unavailable" };
  }
}
