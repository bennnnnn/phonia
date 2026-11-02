// The launch over the real credential store (lib/auth.ts): what is in the
// keychain decides between opening the app, the sign-in and "error + Retry".
import { Text } from "react-native";
import { act, fireEvent, render } from "@testing-library/react-native";

import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { api, type User } from "@/lib/api";

const mockKeychain = new Map<string, string>();
const mockGetItem = jest.fn(async (key: string) => mockKeychain.get(key) ?? null);

jest.mock("expo-secure-store", () => ({
  getItemAsync: (key: string) => mockGetItem(key),
  setItemAsync: jest.fn(async (key: string, value: string) => {
    mockKeychain.set(key, value);
  }),
  deleteItemAsync: jest.fn(async (key: string) => {
    mockKeychain.delete(key);
  }),
}));
jest.mock("@/lib/onboarding", () => ({
  getOnboarded: jest.fn(async () => true), setOnboarded: jest.fn(), clearOnboarded: jest.fn(),
}));
jest.mock("@/lib/api", () => ({
  api: { me: jest.fn(), updateMe: jest.fn() },
  loginWithGoogle: jest.fn(), loginWithApple: jest.fn(), loginWithDev: jest.fn(),
  logoutSession: jest.fn(async () => undefined), setTokenRefreshHandler: jest.fn(),
  setUnauthorizedHandler: jest.fn(), setConsentRequiredHandler: jest.fn(),
}));
jest.mock("@/lib/api/client", () => ({
  accessTokenNeedsRefresh: () => false,
  freshAccessToken: jest.fn(),
  refreshedAccount: () => null,
}));
jest.mock("@/lib/cachedUser", () => ({
  cachedUserMatchesToken: jest.fn(() => true),
  readCachedUser: jest.fn(async () => null), writeCachedUser: jest.fn(), clearCachedUser: jest.fn(),
  mergeCachedUser: (value: User) => value,
}));
jest.mock("@/lib/theme", () => ({ useTheme: () => ({ bg: "white", primary: "blue" }) }));
jest.mock("@/lib/i18n", () => ({ ensureLocale: jest.fn() }));
jest.mock("@/hooks/useBootstrapSync", () => ({ useBootstrapSync: jest.fn() }));
jest.mock("@/lib/apple-auth", () => ({ signInWithAppleCredentials: jest.fn() }));
jest.mock("@/lib/google-auth", () => ({ signInWithGoogleIdToken: jest.fn(), signOutGoogle: jest.fn() }));
jest.mock("@/lib/signOutCleanup", () => ({ clearSignedOutAccount: jest.fn(async () => undefined) }));
jest.mock("@/lib/syncRecords", () => ({ forgetSyncRecords: jest.fn(async () => undefined) }));
jest.mock("@/features/notifications/model/pushNotifications", () => ({ devicePushToken: jest.fn(async () => null) }));

const SESSION_KEY = "recall_session_v1";
const alice = { id: "account-a", name: "Alice", locale: "en" } as User;

function Probe() {
  return <Text>{useAuth().user?.name ?? "signed-out"}</Text>;
}

beforeEach(() => {
  jest.clearAllMocks();
  mockKeychain.clear();
  (api.me as jest.Mock).mockResolvedValue(alice);
});

it("opens the app from a valid record", async () => {
  mockKeychain.set(SESSION_KEY, JSON.stringify({ accessToken: "access-a", refreshToken: "refresh-a" }));
  const rendered = await render(<AuthProvider><Probe /></AuthProvider>);

  expect(rendered.getByText("Alice")).toBeTruthy();
  expect(mockKeychain.get(SESSION_KEY)).toContain("access-a");
});

it("clears a record cut short and opens on sign-in, where Retry once led nowhere", async () => {
  mockKeychain.set(SESSION_KEY, '{"accessToken":"access-a","refre');
  const rendered = await render(<AuthProvider><Probe /></AuthProvider>);
  await act(async () => {
    for (let i = 0; i < 10; i += 1) await Promise.resolve();
  });

  expect(rendered.queryByRole("button", { name: "common.retry" })).toBeNull();
  expect(rendered.getByText("signed-out")).toBeTruthy();
  expect(mockKeychain.get(SESSION_KEY)).toBe("null");
  expect(api.me).not.toHaveBeenCalled();
});

it("keeps a valid record while the server is unreachable", async () => {
  mockKeychain.set(SESSION_KEY, JSON.stringify({ accessToken: "access-a", refreshToken: "refresh-a" }));
  (api.me as jest.Mock).mockRejectedValueOnce(new TypeError("Network request failed"));
  const rendered = await render(<AuthProvider><Probe /></AuthProvider>);

  expect(rendered.getByText("login.error_generic")).toBeTruthy();
  expect(mockKeychain.get(SESSION_KEY)).toContain("access-a");

  await fireEvent.press(rendered.getByRole("button", { name: "common.retry" }));
  expect(rendered.getByText("Alice")).toBeTruthy();
  expect(mockKeychain.get(SESSION_KEY)).toContain("access-a");
});
