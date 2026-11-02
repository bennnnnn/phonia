/**
 * The login screen words a native sign-in failure by key. An unknown message was handed
 * back as the line to show: the SDK's English ("Google Play Services not available", "The
 * authorization attempt failed for an unknown reason") in every language.
 */
import { formatAppleSignInError } from "@/lib/apple-auth";
import { formatGoogleSignInError } from "@/lib/google-auth";

jest.mock("@/lib/config", () => ({
  config: {},
  isGoogleSignInConfigured: () => true,
  isGoogleWebClientConfigured: () => true,
}));

it.each([
  ["Sign-in cancelled", "cancelled"],
  ["Google Play Services not available", "play_services_missing"],
  ["DEVELOPER_ERROR", "android_oauth_setup"],
  ["Google Sign-In did not return an ID token.", "generic"],
  ["A non-recoverable sign in failure occurred", "generic"],
  ["", "generic"],
])("Google: %j → %s", (message, key) => {
  expect(formatGoogleSignInError(new Error(message))).toBe(key);
});

it.each([
  ["The user canceled the authorization attempt.", "cancelled"],
  [
    "Sign in with Apple is not available on this device. On the iOS Simulator, open Settings → Apple Account and sign in, then try again.",
    "apple_unavailable_device",
  ],
  ["The authorization attempt failed for an unknown reason", "generic"],
  ["Apple Sign-In did not return an identity token.", "generic"],
])("Apple: %j → %s", (message, key) => {
  expect(formatAppleSignInError(new Error(message))).toBe(key);
});
