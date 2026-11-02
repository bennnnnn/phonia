import { act, renderHook } from "@testing-library/react-native";
import { Alert, Platform } from "react-native";

import { AccountExistsError } from "@/features/auth/model/accountExists";
import { SignInRefusedError } from "@/features/auth/model/signInRefusal";
import { useLoginActions } from "@/features/auth/hooks/useLoginActions";
import { formatAppleSignInError } from "@/lib/apple-auth";
import {
  isGoogleSignInConfigured,
  isGoogleWebClientConfigured,
} from "@/lib/config";
import { formatGoogleSignInError, isExpoGo } from "@/lib/google-auth";

const mockApple = jest.fn();
const mockGoogle = jest.fn();
const mockDev = jest.fn();
const mockFeedback = { error: jest.fn() };

jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    signInWithApple: mockApple,
    signInWithGoogle: mockGoogle,
    signInWithDev: mockDev,
  }),
}));
jest.mock("@/contexts/actionFeedbackCore", () => ({
  useActionFeedbackOptional: () => mockFeedback,
}));
jest.mock("@/lib/haptics", () => ({ tap: jest.fn() }));
jest.mock("@/lib/apple-auth", () => ({
  formatAppleSignInError: jest.fn(),
}));
jest.mock("@/lib/google-auth", () => ({
  formatGoogleSignInError: jest.fn(),
  isExpoGo: jest.fn(),
}));
jest.mock("@/lib/config", () => ({
  isGoogleSignInConfigured: jest.fn(),
  isGoogleWebClientConfigured: jest.fn(),
}));

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

beforeEach(() => {
  jest.clearAllMocks();
  jest.replaceProperty(Platform, "OS", "ios");
  jest.mocked(isExpoGo).mockReturnValue(false);
  jest.mocked(isGoogleSignInConfigured).mockReturnValue(true);
  jest.mocked(isGoogleWebClientConfigured).mockReturnValue(true);
  jest.mocked(formatAppleSignInError).mockReturnValue("generic");
  jest.mocked(formatGoogleSignInError).mockReturnValue("generic");
  mockApple.mockResolvedValue(undefined);
  mockGoogle.mockResolvedValue(undefined);
  mockDev.mockResolvedValue(undefined);
});

afterEach(() => jest.restoreAllMocks());

it.each([
  ["apple", "handleApple", mockApple],
  ["google", "handleGoogle", mockGoogle],
  ["dev", "handleDev", mockDev],
] as const)("tracks only the active %s provider", async (provider, action, signIn) => {
  const pending = deferred();
  signIn.mockReturnValueOnce(pending.promise);
  const { result } = await renderHook(useLoginActions);

  let request!: Promise<void>;
  await act(async () => {
    request = result.current[action]();
    await Promise.resolve();
  });
  expect(result.current.busy).toBe(true);
  expect(result.current.busyProvider).toBe(provider);

  await act(async () => {
    pending.resolve();
    await request;
  });
  expect(result.current.busy).toBe(false);
  expect(result.current.busyProvider).toBeNull();
});

it.each([
  ["bundle_load_failed", "login.error_bundle"],
  ["native_module_missing", "login.error_native_module"],
  ["not_configured", "login.error_not_configured"],
  ["android_oauth_setup", "login.error_android_google"],
  ["generic", "login.error_generic"],
  ["play_services_missing", "login.error_play_services"],
  // The SDK's own English was shown as it came, in every language.
  ["provider detail", "login.error_generic"],
] as const)("maps Google error %s to %s", async (providerError, expected) => {
  jest.mocked(formatGoogleSignInError).mockReturnValue(providerError);
  mockGoogle.mockRejectedValueOnce(new Error("failed"));
  const { result } = await renderHook(useLoginActions);

  await act(async () => result.current.handleGoogle());

  expect(mockFeedback.error).toHaveBeenCalledWith(expected);
});

describe("in a release build", () => {
  const devHolder = globalThis as unknown as { __DEV__?: boolean };
  const originalDev = devHolder.__DEV__;
  beforeEach(() => {
    devHolder.__DEV__ = false;
    jest.spyOn(console, "warn").mockImplementation(() => undefined);
  });
  afterEach(() => {
    devHolder.__DEV__ = originalDev;
  });

  it.each(["bundle_load_failed", "native_module_missing", "not_configured", "android_oauth_setup"])(
    "shows the generic error, not setup steps, for %s",
    async (providerError) => {
      jest.mocked(formatGoogleSignInError).mockReturnValue(providerError);
      mockGoogle.mockRejectedValueOnce(new Error("failed"));
      const { result } = await renderHook(useLoginActions);

      await act(async () => result.current.handleGoogle());

      expect(mockFeedback.error).toHaveBeenCalledWith("login.error_generic");
    },
  );

  it("shows the generic error when Google sign-in has no client id", async () => {
    jest.mocked(isGoogleWebClientConfigured).mockReturnValue(false);
    const { result } = await renderHook(useLoginActions);

    await act(async () => result.current.handleGoogle());

    expect(mockGoogle).not.toHaveBeenCalled();
    expect(mockFeedback.error).toHaveBeenCalledWith("login.error_generic");
  });
});

it("tells an iPhone without an Apple Account signed in what to do, translated", async () => {
  jest.mocked(formatAppleSignInError).mockReturnValue("apple_unavailable_device");
  mockApple.mockRejectedValueOnce(new Error("Sign in with Apple is not available on this device."));
  const { result } = await renderHook(useLoginActions);

  await act(async () => result.current.handleApple());

  expect(mockFeedback.error).toHaveBeenCalledWith("login.error_apple_unavailable_device");
});

it("does not report a cancelled provider flow", async () => {
  jest.mocked(formatAppleSignInError).mockReturnValue("cancelled");
  mockApple.mockRejectedValueOnce(new Error("cancelled"));
  const { result } = await renderHook(useLoginActions);

  await act(async () => result.current.handleApple());

  expect(mockFeedback.error).not.toHaveBeenCalled();
});

it("keeps a second provider from starting while one is pending", async () => {
  const pending = deferred();
  mockApple.mockReturnValueOnce(pending.promise);
  const { result } = await renderHook(useLoginActions);

  let request!: Promise<void>;
  await act(async () => {
    request = result.current.handleApple();
    await result.current.handleGoogle();
  });
  expect(mockGoogle).not.toHaveBeenCalled();

  await act(async () => {
    pending.resolve();
    await request;
  });
});

it.each([
  ["handleGoogle", mockGoogle, "apple", "login.error_account_exists_apple"],
  ["handleApple", mockApple, "google", "login.error_account_exists_google"],
] as const)(
  "%s names the earlier sign-in when the email already has an account",
  async (action, signIn, signInWith, message) => {
    signIn.mockRejectedValueOnce(new AccountExistsError(signInWith));
    const { result } = await renderHook(useLoginActions);

    await act(async () => result.current[action]());

    expect(mockFeedback.error).toHaveBeenCalledWith(message);
  },
);

it.each([
  ["handleGoogle", mockGoogle, "login.error_rate_limited"],
  ["handleApple", mockApple, "login.error_apple_email_missing"],
  ["handleDev", mockDev, "login.error_unavailable"],
] as const)("%s shows the refusal's own translated line", async (action, signIn, key) => {
  // The server's words are English: the screen showed them as they came, in every language.
  signIn.mockRejectedValueOnce(new SignInRefusedError(key));
  const { result } = await renderHook(useLoginActions);

  await act(async () => result.current[action]());

  expect(mockFeedback.error).toHaveBeenCalledWith(key);
  expect(formatGoogleSignInError).not.toHaveBeenCalled();
  expect(formatAppleSignInError).not.toHaveBeenCalled();
});

it("shows dev login's other failures as the generic line, not their English", async () => {
  // It showed the server's raw JSON body, or the error's own English.
  mockDev.mockRejectedValueOnce(new Error('{"detail":"Dev auth disabled"}'));
  const { result } = await renderHook(useLoginActions);

  await act(async () => result.current.handleDev());

  expect(mockFeedback.error).toHaveBeenCalledWith("login.error_generic");
});

it("preserves the Expo Go Google availability alert", async () => {
  jest.mocked(isExpoGo).mockReturnValue(true);
  jest.spyOn(Alert, "alert").mockImplementation(() => {});
  const { result } = await renderHook(useLoginActions);

  await act(async () => result.current.handleGoogle());

  expect(Alert.alert).toHaveBeenCalledWith(
    "login.google_unavailable_title",
    "login.google_unavailable_body",
  );
  expect(mockGoogle).not.toHaveBeenCalled();
});
