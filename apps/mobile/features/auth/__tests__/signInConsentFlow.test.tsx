/**
 * Agree by signing in, end to end: the real auth context, sign-in page, consent gate and
 * consent screen over a stand-in server that keeps `ai_data_consent_at` as the API does
 * (set by a sign-in that says the user agreed, or by `PATCH /auth/me`). A new sign-in
 * used to stop on the consent screen and send a second request to agree.
 */
import { useEffect, useLayoutEffect, useState } from "react";
import { Text } from "react-native";
import { act, fireEvent, render } from "@testing-library/react-native";
import { Redirect } from "expo-router";

import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { AiConsentRedirect } from "@/features/auth/components/AiConsentRedirect";
import AiConsentScreen from "@/features/auth/screens/AiConsentScreen";
import LoginScreen from "@/features/auth/screens/LoginScreen";
import type { User } from "@/lib/api/types";

const AGREED_AT = "2026-10-25T09:00:00Z";

type Sent = { method: string; path: string; body: Record<string, unknown> };
const mockSent: Sent[] = [];
const mockServer = { consentAt: null as string | null };
let mockStoredToken: string | null = null;

function mockAccount(): User {
  return {
    id: "account-a", name: "Ann", email: "ann@example.com", locale: "en",
    ai_data_consent_at: mockServer.consentAt,
  } as User;
}

/** The API's rule: a sign-in that says the user agreed stores the time once. */
function mockAnswer(method: string, path: string, body: Record<string, unknown>): unknown {
  mockSent.push({ method, path, body });
  if (path.startsWith("/auth/") && method === "POST") {
    if (body.ai_data_consent === true && mockServer.consentAt === null) mockServer.consentAt = AGREED_AT;
    return { access_token: "access-a", refresh_token: "refresh-a", user: mockAccount() };
  }
  if (path === "/auth/me" && method === "PATCH") {
    mockServer.consentAt = body.ai_data_consent ? AGREED_AT : null;
    return mockAccount();
  }
  throw new Error(`unexpected ${method} ${path}`);
}

jest.mock("@/lib/api/client", () => ({
  ...jest.requireActual("@/lib/api/client"),
  apiUrl: (path: string) => `https://api.test${path}`,
  fetchWithTimeout: async (url: string, init: RequestInit) => {
    const answer = mockAnswer(init.method ?? "GET", url.replace("https://api.test", ""), JSON.parse(String(init.body)));
    return { ok: true, status: 200, json: async () => answer } as unknown as Response;
  },
  request: async (path: string, _token: string, init: RequestInit = {}) =>
    mockAnswer(init.method ?? "GET", path, init.body ? JSON.parse(String(init.body)) : {}),
  accessTokenNeedsRefresh: () => false,
  refreshedAccount: () => null,
}));
jest.mock("@/lib/api", () => {
  const auth = jest.requireActual("@/features/auth/api");
  return {
    api: { me: jest.fn(async () => mockAccount()), updateMe: jest.fn(), deleteAccount: jest.fn() },
    loginWithGoogle: auth.loginWithGoogle,
    loginWithApple: auth.loginWithApple,
    loginWithDev: auth.loginWithDev,
    agreeToAiDataSharing: auth.agreeToAiDataSharing,
    logoutSession: jest.fn(async () => undefined),
    setTokenRefreshHandler: jest.fn(),
    setUnauthorizedHandler: jest.fn(),
    setConsentRequiredHandler: jest.fn(),
  };
});
jest.mock("@/lib/auth", () => {
  let generation = 0;
  return {
    getSessionGeneration: () => generation,
    invalidateSession: () => ++generation,
    getToken: jest.fn(async () => mockStoredToken),
    getRefreshToken: jest.fn(async () => mockStoredToken && "refresh-a"),
    setTokenPair: jest.fn(async () => true),
    clearToken: jest.fn(async () => { generation++; }),
    getOnboarded: jest.fn(async () => true), setOnboarded: jest.fn(), clearOnboarded: jest.fn(),
    CorruptSessionError: class CorruptSessionError extends Error {},
  };
});
jest.mock("@/lib/onboarding", () => ({
  getOnboarded: jest.fn(async () => true), setOnboarded: jest.fn(), clearOnboarded: jest.fn(),
}));
jest.mock("@/lib/cachedUser", () => ({
  cachedUserMatchesToken: jest.fn(() => true),
  readCachedUser: jest.fn(async () => null), writeCachedUser: jest.fn(), clearCachedUser: jest.fn(),
  mergeCachedUser: (value: User) => value,
}));
jest.mock("@/lib/i18n", () => ({ ensureLocale: jest.fn() }));
jest.mock("@/hooks/useBootstrapSync", () => ({ useBootstrapSync: jest.fn() }));
jest.mock("@/lib/signOutCleanup", () => ({ clearSignedOutAccount: jest.fn(async () => undefined) }));
jest.mock("@/lib/syncRecords", () => ({ forgetSyncRecords: jest.fn(async () => undefined) }));
jest.mock("@/features/notifications/model/pushNotifications", () => ({ devicePushToken: jest.fn(async () => null) }));
jest.mock("@/lib/haptics", () => ({ tap: jest.fn() }));
jest.mock("expo-linear-gradient", () => {
  const { View } = jest.requireActual("react-native");
  return { LinearGradient: View };
});
jest.mock("@/lib/apple-auth", () => ({
  shouldShowAppleSignInButton: () => false,
  formatAppleSignInError: () => "generic",
  signInWithAppleCredentials: jest.fn(),
  appleConsentForAccountDelete: jest.fn(),
}));
jest.mock("@/lib/google-auth", () => ({
  isExpoGo: () => false,
  formatGoogleSignInError: () => "generic",
  signInWithGoogleIdToken: jest.fn(async () => "google-id-token"),
  signOutGoogle: jest.fn(async () => undefined),
}));
jest.mock("@/lib/config", () => ({
  config: { devAuthEnabled: false },
  isGoogleSignInConfigured: () => true,
  isGoogleWebClientConfigured: () => true,
}));
jest.mock("@/lib/legalUrls", () => ({
  getLegalPrivacyUrl: () => "https://example.com/privacy",
  getLegalTermsUrl: () => "https://example.com/terms",
}));

// expo-router: the route on screen, moved by Redirect and router.replace as the app's are.
let mockRoute = "/";
const mockRouteListeners = new Set<(route: string) => void>();
function mockGo(href: string) {
  mockRoute = href;
  for (const listener of mockRouteListeners) listener(href);
}
jest.mock("expo-router", () => {
  const React = jest.requireActual("react");
  return {
    Redirect: ({ href }: { href: string }) => {
      React.useEffect(() => mockGo(href), [href]);
      return null;
    },
    useRouter: () => ({ replace: mockGo }),
    usePathname: () => mockRoute,
    useRootNavigationState: () => ({ key: "root" }),
  };
});

/** The chat route's stand-in: a signed-out visit goes to sign-in, as the root layout does. */
function Chat() {
  const { token, loading } = useAuth();
  if (loading) return null;
  if (!token) return <Redirect href="/login" />;
  return <Text>chat</Text>;
}

/** The introduction a sign-out opens on; its Get started goes on to sign-in. */
function Onboarding() {
  const { completeOnboarding } = useAuth();
  const getStarted = async () => {
    await completeOnboarding();
    mockGo("/login");
  };
  return <Text onPress={() => void getStarted()}>get started</Text>;
}

function App() {
  const [route, setRoute] = useState(mockRoute);
  useLayoutEffect(() => {
    mockRouteListeners.add(setRoute);
    return () => void mockRouteListeners.delete(setRoute);
  }, []);
  useEffect(() => setRoute(mockRoute), []);
  return (
    <>
      <AiConsentRedirect />
      {route === "/login" ? <LoginScreen /> : route === "/consent" ? <AiConsentScreen /> : route === "/onboarding" ? <Onboarding /> : <Chat />}
    </>
  );
}

async function settle() {
  await act(async () => {
    for (let i = 0; i < 20; i += 1) await Promise.resolve();
  });
}

beforeEach(() => {
  mockSent.length = 0;
  mockServer.consentAt = null;
  mockStoredToken = null;
  mockRoute = "/";
});

it("a new sign-in opens the chat with no consent screen, and the server records the agreement", async () => {
  const view = await render(<AuthProvider><App /></AuthProvider>);
  await settle();
  expect(view.getByText("login.consent_line")).toBeOnTheScreen();

  await act(async () => fireEvent.press(view.getByText("login.google")));
  await settle();

  expect(view.getByText("chat")).toBeOnTheScreen();
  expect(view.queryByText("onboarding.consent_title")).toBeNull();
  expect(mockServer.consentAt).toBe(AGREED_AT);
  // One request: the sign-in itself. The consent screen's PATCH /auth/me is gone.
  expect(mockSent.map((r) => `${r.method} ${r.path}`)).toEqual(["POST /auth/google"]);
});

it("an account without the agreement (from before, or withdrawn) is still asked, and agreeing opens the chat", async () => {
  mockStoredToken = "access-a";
  const view = await render(<AuthProvider><App /></AuthProvider>);
  await settle();

  expect(mockRoute).toBe("/consent");
  expect(view.getByText("onboarding.consent_title")).toBeOnTheScreen();

  await act(async () => fireEvent.press(view.getByText("onboarding.consent_agree")));
  await settle();

  expect(view.getByText("chat")).toBeOnTheScreen();
  expect(mockSent.map((r) => `${r.method} ${r.path} ${JSON.stringify(r.body)}`)).toEqual([
    'PATCH /auth/me {"ai_data_consent":true}',
  ]);
});

it("after a withdrawal, signing out from the consent screen and in again agrees by the tap", async () => {
  // Withdrawn in Data controls: the server holds no agreement, and the gate asks again.
  mockStoredToken = "access-a";
  const view = await render(<AuthProvider><App /></AuthProvider>);
  await settle();
  expect(view.getByText("onboarding.consent_title")).toBeOnTheScreen();

  await act(async () => fireEvent.press(view.getByText("onboarding.consent_decline")));
  await settle();
  await act(async () => fireEvent.press(view.getByText("get started")));
  await settle();
  expect(view.getByText("login.consent_line")).toBeOnTheScreen();

  await act(async () => fireEvent.press(view.getByText("login.google")));
  await settle();

  expect(view.getByText("chat")).toBeOnTheScreen();
  expect(mockServer.consentAt).toBe(AGREED_AT);
  expect(mockSent.at(-1)).toMatchObject({ method: "POST", path: "/auth/google", body: { ai_data_consent: true } });
});
