import { useCallback, useRef, useState } from "react";
import { Platform } from "react-native";
import { useTranslation } from "react-i18next";

import { useAuth } from "@/contexts/AuthContext";
import { useActionFeedbackOptional } from "@/contexts/actionFeedbackCore";
import { AccountExistsError } from "@/features/auth/model/accountExists";
import { SIGN_IN_GENERIC_KEY, SignInRefusedError } from "@/features/auth/model/signInRefusal";
import { formatAppleSignInError } from "@/lib/apple-auth";
import { isGoogleSignInConfigured, isGoogleWebClientConfigured } from "@/lib/config";
import { formatGoogleSignInError, isExpoGo } from "@/lib/google-auth";
import { tap } from "@/lib/haptics";
import { alertDialog } from "@/ui/overlay/dialogs";

export type LoginProvider = "apple" | "google" | "dev";

/** Setup problems only a developer can fix. Their copy names commands and env vars, so a
 * release build shows the generic error instead (still logged to the console). */
const SETUP_ERROR_KEYS: Record<string, string> = {
  bundle_load_failed: "login.error_bundle",
  native_module_missing: "login.error_native_module",
  not_configured: "login.error_not_configured",
  android_oauth_setup: "login.error_android_google",
};

function setupErrorKey(key: string): string {
  return __DEV__ ? key : "login.error_generic";
}

/** What the person can do about it: a phone without Play services, an Apple ID signed out. */
const DEVICE_ERROR_KEYS: Record<string, string> = {
  play_services_missing: "login.error_play_services",
  apple_unavailable_device: "login.error_apple_unavailable_device",
};

export function useLoginActions() {
  const { signInWithApple, signInWithGoogle, signInWithDev } = useAuth();
  const { t } = useTranslation();
  const feedback = useActionFeedbackOptional();
  const busyRef = useRef(false);
  const [busyProvider, setBusyProvider] = useState<LoginProvider | null>(null);

  const showSignInError = useCallback(
    (message: string) => {
      if (feedback) feedback.error(message);
      else void alertDialog({ title: t("login.sign_in_failed"), message });
    },
    [feedback, t],
  );

  const signInErrorMessage = useCallback(
    (error: unknown, provider: Exclude<LoginProvider, "dev">) => {
      if (error instanceof AccountExistsError) {
        return error.signInWith === "apple"
          ? t("login.error_account_exists_apple")
          : t("login.error_account_exists_google");
      }
      if (error instanceof SignInRefusedError) return t(error.key);
      const key =
        provider === "google"
          ? formatGoogleSignInError(error)
          : formatAppleSignInError(error);
      if (key === "cancelled") return null;
      const setupKey = SETUP_ERROR_KEYS[key];
      if (setupKey) {
        if (!__DEV__) console.warn(`[auth] ${provider} sign-in setup error: ${key}`);
        return t(setupErrorKey(setupKey));
      }
      if (key === "generic" && __DEV__) console.warn(`[auth] ${provider} sign-in failed`, error);
      return t(DEVICE_ERROR_KEYS[key] ?? SIGN_IN_GENERIC_KEY);
    },
    [t],
  );

  const handleApple = useCallback(async () => {
    if (busyRef.current) return;
    tap();
    busyRef.current = true;
    setBusyProvider("apple");
    try {
      await signInWithApple();
    } catch (error) {
      const message = signInErrorMessage(error, "apple");
      if (message) showSignInError(message);
    } finally {
      busyRef.current = false;
      setBusyProvider(null);
    }
  }, [showSignInError, signInErrorMessage, signInWithApple]);

  const handleGoogle = useCallback(async () => {
    if (busyRef.current) return;
    tap();
    if (isExpoGo()) {
      void alertDialog({
        title: t("login.google_unavailable_title"),
        message: t("login.google_unavailable_body"),
      });
      return;
    }
    if (!isGoogleWebClientConfigured()) {
      showSignInError(t(setupErrorKey("login.error_not_configured")));
      return;
    }
    if (Platform.OS === "ios" && !isGoogleSignInConfigured()) {
      showSignInError(t(setupErrorKey("login.error_not_configured")));
      return;
    }
    busyRef.current = true;
    setBusyProvider("google");
    try {
      await signInWithGoogle();
    } catch (error) {
      const message = signInErrorMessage(error, "google");
      if (message) showSignInError(message);
    } finally {
      busyRef.current = false;
      setBusyProvider(null);
    }
  }, [showSignInError, signInErrorMessage, signInWithGoogle, t]);

  const handleDev = useCallback(async () => {
    if (busyRef.current) return;
    tap();
    busyRef.current = true;
    setBusyProvider("dev");
    try {
      await signInWithDev();
    } catch (error) {
      showSignInError(t(error instanceof SignInRefusedError ? error.key : SIGN_IN_GENERIC_KEY));
    } finally {
      busyRef.current = false;
      setBusyProvider(null);
    }
  }, [showSignInError, signInWithDev, t]);

  return {
    busyProvider,
    busy: busyProvider !== null,
    handleApple,
    handleGoogle,
    handleDev,
  };
}
