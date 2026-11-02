import React, { useLayoutEffect } from "react";
import { Text } from "react-native";
import { act, fireEvent, render } from "@testing-library/react-native";

import { AuthProvider, useAuth, useAuthUserReader } from "@/contexts/AuthContext";
import { api, loginWithDev, logoutSession, setTokenRefreshHandler, type User } from "@/lib/api";
import { clearOnboarded, clearToken, CorruptSessionError, getToken, setTokenPair } from "@/lib/auth";
import { cachedUserMatchesToken, clearCachedUser, readCachedUser, writeCachedUser } from "@/lib/cachedUser";
import { ensureLocale } from "@/lib/i18n";
import { reportCorruptSessionCleared } from "@/lib/sentry";
import { clearSignedOutAccount } from "@/lib/signOutCleanup";
import { forgetSyncRecords } from "@/lib/syncRecords";
import { onAppEvent } from "@/lib/appEvents";
import { confirmDialog } from "@/ui/overlay/dialogs";

jest.mock("@/lib/api", () => ({
  api: { me: jest.fn(), updateMe: jest.fn() },
  loginWithGoogle: jest.fn(), loginWithApple: jest.fn(), loginWithDev: jest.fn(),
  logoutSession: jest.fn(), setTokenRefreshHandler: jest.fn(), setUnauthorizedHandler: jest.fn(),
  setConsentRequiredHandler: jest.fn(),
}));
jest.mock("@/lib/auth", () => {
  let generation = 0;
  return {
    getSessionGeneration: () => generation,
    invalidateSession: () => ++generation,
    getToken: jest.fn(), getRefreshToken: jest.fn(async () => "refresh-a"),
    setTokenPair: jest.fn(async () => true),
    clearToken: jest.fn(async () => { generation++; }),
    getOnboarded: jest.fn(async () => true), setOnboarded: jest.fn(), clearOnboarded: jest.fn(),
    CorruptSessionError: class CorruptSessionError extends Error {},
  };
});
jest.mock("@/lib/cachedUser", () => ({
  cachedUserMatchesToken: jest.fn(() => true),
  readCachedUser: jest.fn(), writeCachedUser: jest.fn(), clearCachedUser: jest.fn(),
  mergeCachedUser: (value: User) => value,
}));
jest.mock("@/lib/theme", () => ({ useTheme: () => ({ bg: "white", primary: "blue" }) }));
jest.mock("@/lib/i18n", () => ({ ensureLocale: jest.fn() }));
jest.mock("@/hooks/useBootstrapSync", () => ({ useBootstrapSync: jest.fn() }));
jest.mock("@/lib/apple-auth", () => ({ signInWithAppleCredentials: jest.fn() }));
jest.mock("@/lib/google-auth", () => ({ signInWithGoogleIdToken: jest.fn(), signOutGoogle: jest.fn() }));
jest.mock("@/lib/signOutCleanup", () => ({ clearSignedOutAccount: jest.fn() }));
jest.mock("@/lib/sentry", () => ({ reportCorruptSessionCleared: jest.fn() }));
jest.mock("@/lib/syncRecords", () => ({ forgetSyncRecords: jest.fn(async () => undefined) }));
jest.mock("@/features/notifications/model/pushNotifications", () => ({ devicePushToken: jest.fn(async () => null) }));
jest.mock("@/ui/overlay/dialogs", () => ({ confirmDialog: jest.fn(async () => true) }));

const userA = { id: "account-a", name: "Alice", locale: "en" } as User;
const userB = { id: "account-b", name: "Bob", locale: "en" } as User;
let current: ReturnType<typeof useAuth>;

function Probe() {
  const auth = useAuth();
  useLayoutEffect(() => { current = auth; }, [auth]);
  return <Text>{auth.user?.name ?? "signed-out"}</Text>;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

async function mount() {
  return render(<AuthProvider><Probe /></AuthProvider>);
}

beforeEach(() => {
  jest.clearAllMocks();
  (getToken as jest.Mock).mockResolvedValue("access-a");
  (readCachedUser as jest.Mock).mockResolvedValue(userA);
  (api.me as jest.Mock).mockResolvedValue(userA);
  (logoutSession as jest.Mock).mockResolvedValue(undefined);
  (loginWithDev as jest.Mock).mockResolvedValue({ access_token: "access-b", refresh_token: "refresh-b", user: userB });
});

it("reads the current user for a row's handler without re-rendering the row on a profile patch", async () => {
  const rowRendered = jest.fn<void, [() => User | null]>();
  function Row() {
    rowRendered(useAuthUserReader());
    return null;
  }
  const row = <Row />;
  await render(<AuthProvider><Probe />{row}</AuthProvider>);
  const settled = rowRendered.mock.calls.length;
  const reader = rowRendered.mock.calls.at(-1)![0];

  await act(async () => { current.mergeUser({ name: "Alice B." }); });
  expect(current.user?.name).toBe("Alice B.");
  expect(rowRendered).toHaveBeenCalledTimes(settled);
  expect(reader()?.name).toBe("Alice B.");
});

it("asks for consent again when the server refuses a turn for want of it", async () => {
  (api.me as jest.Mock).mockResolvedValue({ ...userA, ai_data_consent_at: "2026-10-19T09:00:00Z" });
  await mount();
  const { setConsentRequiredHandler } = jest.requireMock("@/lib/api");
  await act(async () => { setConsentRequiredHandler.mock.calls.at(-1)[0](); });
  expect(current.user?.ai_data_consent_at).toBeNull();
  expect(current.user?.id).toBe(userA.id);
});

it("clears the visible account before a slow logout request finishes", async () => {
  const logout = deferred<void>();
  (logoutSession as jest.Mock).mockReturnValue(logout.promise);
  await mount();
  let pending!: Promise<void>;
  await act(async () => { pending = current.signOut(); });
  expect(current.user).toBeNull();
  expect(current.token).toBeNull();
  await act(async () => { logout.resolve(); await pending; });
});

it("does not restore an account or its cache when startup validation finishes after signout", async () => {
  const me = deferred<User>();
  (api.me as jest.Mock).mockReturnValue(me.promise);
  await mount();
  await act(async () => { await current.signOut(); });
  (writeCachedUser as jest.Mock).mockClear();
  await act(async () => { me.resolve(userA); });
  expect(current.user).toBeNull();
  expect(writeCachedUser).not.toHaveBeenCalled();
});

it("keeps the refreshed access token when uncached startup validation succeeds", async () => {
  (readCachedUser as jest.Mock).mockResolvedValue(null);
  (api.me as jest.Mock).mockImplementation(async () => {
    (getToken as jest.Mock).mockResolvedValue("access-refreshed");
    const callback = (setTokenRefreshHandler as jest.Mock).mock.calls.at(-1)[0];
    callback("access-refreshed", userA);
    return userA;
  });
  await mount();
  expect(current.user?.id).toBe(userA.id);
  expect(current.token).toBe("access-refreshed");
});

it("ignores a profile refresh belonging to a previous account", async () => {
  await mount();
  const me = deferred<User>();
  (api.me as jest.Mock).mockReturnValue(me.promise);
  let pending!: Promise<void>;
  await act(async () => { pending = current.refreshUser(); });
  await act(async () => { await current.signOut(); await current.signInWithDev(); });
  (writeCachedUser as jest.Mock).mockClear();
  await act(async () => { me.resolve(userA); await pending; });
  expect(current.user?.id).toBe(userB.id);
  expect(writeCachedUser).not.toHaveBeenCalled();
});

it("does not roll back a new account when the previous account's profile update fails", async () => {
  await mount();
  const update = deferred<User>();
  (api.updateMe as jest.Mock).mockReturnValue(update.promise);
  let pending!: Promise<void>;
  await act(async () => { pending = current.updateUser({ name: "Changed" }).catch(() => {}); });
  await act(async () => { await current.signOut(); await current.signInWithDev(); });
  await act(async () => { update.reject(new Error("offline")); await pending; });
  expect(current.user?.id).toBe(userB.id);
});

it("keeps the latest sign-in when an older sign-in completes last", async () => {
  await mount();
  const older = deferred<{ access_token: string; refresh_token: string; user: User }>();
  (loginWithDev as jest.Mock).mockReturnValueOnce(older.promise);
  let pending!: Promise<void>;
  await act(async () => { pending = current.signInWithDev(); });
  await act(async () => { await current.signInWithDev(); });
  (setTokenPair as jest.Mock).mockClear();
  await act(async () => {
    older.resolve({ access_token: "access-old", refresh_token: "refresh-old", user: userA });
    await pending;
  });
  expect(current.user?.id).toBe(userB.id);
  expect(setTokenPair).not.toHaveBeenCalled();
});

it("does not persist credentials from a sign-in cancelled by signout", async () => {
  await mount();
  const login = deferred<{ access_token: string; refresh_token: string; user: User }>();
  (loginWithDev as jest.Mock).mockReturnValue(login.promise);
  let pending!: Promise<void>;
  await act(async () => { pending = current.signInWithDev(); });
  await act(async () => { await current.signOut(); });
  await act(async () => {
    login.resolve({ access_token: "access-b", refresh_token: "refresh-b", user: userB });
    await pending;
  });
  expect(current.user).toBeNull();
  expect(setTokenPair).not.toHaveBeenCalled();
});

it("does not let a retained merge callback change the next account", async () => {
  await mount();
  const mergePreviousUser = current.mergeUser;
  await act(async () => { await current.signOut(); await current.signInWithDev(); });
  await act(async () => { mergePreviousUser({ name: "Alice's delayed update" }); });
  expect(current.user?.name).toBe("Bob");
});

it("does not bootstrap account preferences from cached display defaults", async () => {
  const me = deferred<User>();
  (api.me as jest.Mock).mockReturnValue(me.promise);
  await mount();
  const { useBootstrapSync } = jest.requireMock("@/hooks/useBootstrapSync");
  expect(current.user?.id).toBe(userA.id);
  expect(useBootstrapSync.mock.calls.at(-1)[0]).toEqual(expect.objectContaining({ token: null, user: null }));
  await act(async () => { me.resolve(userA); });
  expect(useBootstrapSync.mock.calls.at(-1)[0]).toEqual(expect.objectContaining({ token: "access-a", user: userA }));
});

it("retries secure credential loading without treating a storage failure as logout", async () => {
  (getToken as jest.Mock).mockRejectedValueOnce(new Error("keychain unavailable"));
  const rendered = await mount();
  expect(rendered.getByText("login.error_generic")).toBeTruthy();
  expect(rendered.queryByText("signed-out")).toBeNull();
  await fireEvent.press(rendered.getByRole("button", { name: "common.retry" }));
  expect(current.user?.id).toBe(userA.id);
});

it("retries offline startup without a cached user", async () => {
  (readCachedUser as jest.Mock).mockResolvedValue(null);
  (api.me as jest.Mock).mockRejectedValueOnce(new Error("offline"));
  const rendered = await mount();
  expect(rendered.getByText("login.error_generic")).toBeTruthy();
  expect(rendered.queryByText("signed-out")).toBeNull();
  await fireEvent.press(rendered.getByRole("button", { name: "common.retry" }));
  expect(current.user?.id).toBe(userA.id);
});

it("signs out when startup validation reports a genuine unauthorized session", async () => {
  (readCachedUser as jest.Mock).mockResolvedValue(null);
  (api.me as jest.Mock).mockImplementation(async () => {
    const { setUnauthorizedHandler } = jest.requireMock("@/lib/api");
    setUnauthorizedHandler.mock.calls.at(-1)[0]();
    throw new Error("unauthorized");
  });
  const rendered = await mount();
  expect(rendered.getByText("signed-out")).toBeTruthy();
  expect(rendered.queryByText("login.error_generic")).toBeNull();
});

it("does not authenticate credentials returned by a dismissed native login", async () => {
  const native = deferred<string>();
  const { signInWithGoogleIdToken } = jest.requireMock("@/lib/google-auth");
  const { loginWithGoogle } = jest.requireMock("@/lib/api");
  signInWithGoogleIdToken.mockReturnValue(native.promise);
  await mount();
  let pending!: Promise<void>;
  await act(async () => { pending = current.signInWithGoogle(); });
  await act(async () => { await current.signOut(); });
  await act(async () => { native.resolve("id-token"); await pending; });
  expect(loginWithGoogle).not.toHaveBeenCalled();
});

it("waits for local account cleanup before another login, without waiting for backend logout", async () => {
  const cleanup = deferred<void>();
  const logout = deferred<void>();
  const { clearSignedOutAccount } = jest.requireMock("@/lib/signOutCleanup");
  clearSignedOutAccount.mockReturnValueOnce(cleanup.promise);
  (logoutSession as jest.Mock).mockReturnValueOnce(logout.promise);
  await mount();
  let signingOut!: Promise<void>;
  let signingIn!: Promise<void>;
  await act(async () => {
    signingOut = current.signOut();
    signingIn = current.signInWithDev();
  });
  expect(current.user).toBeNull();
  expect(loginWithDev).not.toHaveBeenCalled();
  await act(async () => { cleanup.resolve(); await signingOut; await signingIn; });
  expect(current.user?.id).toBe(userB.id);
  await act(async () => { logout.resolve(); });
  expect(current.user?.id).toBe(userB.id);
});

it("never paints another account's cached profile while validating stored credentials", async () => {
  const me = deferred<User>();
  const { cachedUserMatchesToken } = jest.requireMock("@/lib/cachedUser");
  cachedUserMatchesToken.mockReturnValueOnce(false);
  (api.me as jest.Mock).mockReturnValue(me.promise);
  const rendered = await mount();
  expect(rendered.queryByText("Alice")).toBeNull();
  await act(async () => { me.resolve(userB); });
  expect(current.user?.id).toBe(userB.id);
});

it("preserves matching cached first paint during a temporary startup outage", async () => {
  (api.me as jest.Mock).mockRejectedValue(new Error("offline"));
  const rendered = await mount();
  expect(rendered.getByText("Alice")).toBeTruthy();
  expect(current.token).toBe("access-a");
  expect(rendered.queryByText("login.error_generic")).toBeNull();
});

it("keeps bootstrap gated when a profile edit supersedes startup validation and then fails", async () => {
  const me = deferred<User>();
  const update = deferred<User>();
  const cached = { ...userA, push_notifications_enabled: false, reminder_lead_minutes: 0 };
  const verified = { ...userA, push_notifications_enabled: true, reminder_lead_minutes: 30 };
  (readCachedUser as jest.Mock).mockResolvedValue(cached);
  (api.me as jest.Mock).mockReturnValueOnce(me.promise);
  (api.updateMe as jest.Mock).mockReturnValueOnce(update.promise);
  await mount();
  const { useBootstrapSync } = jest.requireMock("@/hooks/useBootstrapSync");
  let pending!: Promise<void>;
  await act(async () => { pending = current.updateUser({ name: "Edited" }).catch(() => {}); });
  await act(async () => { me.resolve(verified); });
  expect(useBootstrapSync.mock.calls.at(-1)[0]).toEqual(expect.objectContaining({ token: null, user: null }));
  await act(async () => { update.reject(new Error("offline")); await pending; });
  expect(current.user).toEqual(cached);
  expect(useBootstrapSync.mock.calls.at(-1)[0]).toEqual(expect.objectContaining({ token: null, user: null }));

  (api.me as jest.Mock).mockResolvedValueOnce(verified);
  await act(async () => { await current.refreshUser(); });
  expect(useBootstrapSync.mock.calls.at(-1)[0]).toEqual(expect.objectContaining({ token: "access-a", user: verified }));
});

it("enables bootstrap when a superseding profile edit adopts a full server profile", async () => {
  const me = deferred<User>();
  const update = deferred<User>();
  const verified = { ...userA, name: "Edited", push_notifications_enabled: true, reminder_lead_minutes: 30 };
  (api.me as jest.Mock).mockReturnValueOnce(me.promise);
  (api.updateMe as jest.Mock).mockReturnValueOnce(update.promise);
  await mount();
  const { useBootstrapSync } = jest.requireMock("@/hooks/useBootstrapSync");
  let pending!: Promise<void>;
  await act(async () => { pending = current.updateUser({ name: "Edited" }); });
  await act(async () => { me.resolve(userA); });
  expect(useBootstrapSync.mock.calls.at(-1)[0]).toEqual(expect.objectContaining({ token: null, user: null }));
  await act(async () => { update.resolve(verified); await pending; });
  expect(useBootstrapSync.mock.calls.at(-1)[0]).toEqual(expect.objectContaining({ token: "access-a", user: verified }));
});

it("restores an unvalidated cache flag when a failed edit rolls back after token refresh", async () => {
  const me = deferred<User>();
  const update = deferred<User>();
  const verified = { ...userA, push_notifications_enabled: true, reminder_lead_minutes: 30 };
  (api.me as jest.Mock).mockReturnValueOnce(me.promise);
  (api.updateMe as jest.Mock).mockReturnValueOnce(update.promise);
  await mount();
  const { useBootstrapSync } = jest.requireMock("@/hooks/useBootstrapSync");
  let pending!: Promise<void>;
  await act(async () => { pending = current.updateUser({ name: "Edited" }).catch(() => {}); });
  await act(async () => {
    const refresh = (setTokenRefreshHandler as jest.Mock).mock.calls.at(-1)[0];
    refresh("refreshed", verified);
  });
  expect(useBootstrapSync.mock.calls.at(-1)[0]).toEqual(expect.objectContaining({ user: verified }));
  await act(async () => { update.reject(new Error("offline")); await pending; me.resolve(verified); });
  expect(current.user).toEqual(userA);
  expect(useBootstrapSync.mock.calls.at(-1)[0]).toEqual(expect.objectContaining({ token: null, user: null }));
});

describe("launch restore", () => {
  it("reports the restore from the cache before /auth/me answers", async () => {
    const me = deferred<User>();
    (api.me as jest.Mock).mockReturnValue(me.promise);
    const onRestored = jest.fn();
    await render(<AuthProvider onRestored={onRestored}><Probe /></AuthProvider>);
    expect(onRestored).toHaveBeenCalled();
    expect(current.user?.id).toBe(userA.id);
    expect(current.profileValidated).toBe(false);

    await act(async () => { me.resolve(userA); });
    expect(current.profileValidated).toBe(true);
  });

  it("reports a signed-out launch, and one whose restore failed, so the splash can go", async () => {
    (getToken as jest.Mock).mockResolvedValueOnce(null);
    const signedOut = jest.fn();
    const first = await render(<AuthProvider onRestored={signedOut}><Probe /></AuthProvider>);
    expect(signedOut).toHaveBeenCalled();
    await first.unmount();

    (readCachedUser as jest.Mock).mockResolvedValue(null);
    (api.me as jest.Mock).mockRejectedValue(new Error("offline"));
    const failed = jest.fn();
    await render(<AuthProvider onRestored={failed}><Probe /></AuthProvider>);
    expect(failed).toHaveBeenCalled();
  });

  it("waits for /auth/me without a cached account", async () => {
    const me = deferred<User>();
    (readCachedUser as jest.Mock).mockResolvedValue(null);
    (api.me as jest.Mock).mockReturnValue(me.promise);
    const onRestored = jest.fn();
    await render(<AuthProvider onRestored={onRestored}><Probe /></AuthProvider>);
    expect(onRestored).not.toHaveBeenCalled();
    await act(async () => { me.resolve(userA); });
    expect(onRestored).toHaveBeenCalled();
  });
});

describe("a cache that is not this sign-in's", () => {
  it("is cleared, and its language with it, when nobody is signed in", async () => {
    (getToken as jest.Mock).mockResolvedValueOnce(null);
    (readCachedUser as jest.Mock).mockResolvedValue({ ...userA, locale: "de" });
    await mount();
    expect(clearCachedUser).toHaveBeenCalled();
    expect(ensureLocale).toHaveBeenCalledWith("en");
    expect(current.user).toBeNull();
  });

  it("is cleared when it belongs to another account than the stored token", async () => {
    (cachedUserMatchesToken as jest.Mock).mockReturnValueOnce(false);
    (readCachedUser as jest.Mock).mockResolvedValue({ ...userB, locale: "de" });
    await mount();
    expect(clearCachedUser).toHaveBeenCalled();
    expect(ensureLocale).toHaveBeenCalledWith("en");
    expect(current.user?.id).toBe(userA.id);
  });

  it("is kept for the signed-in account", async () => {
    const german = { ...userA, locale: "de" };
    (readCachedUser as jest.Mock).mockResolvedValue(german);
    (api.me as jest.Mock).mockResolvedValue(german);
    await mount();
    expect(clearCachedUser).not.toHaveBeenCalled();
    expect(ensureLocale).not.toHaveBeenCalledWith("en");
  });
});

it("forgets the push and location sync records when an account signs in", async () => {
  (getToken as jest.Mock).mockResolvedValueOnce(null);
  await mount();
  await act(async () => { await current.signInWithDev(); });
  expect(forgetSyncRecords).toHaveBeenCalledTimes(1);
  expect(current.user?.id).toBe(userB.id);
});

it("hands the server this device's push token with the logout", async () => {
  const { devicePushToken } = jest.requireMock("@/features/notifications/model/pushNotifications");
  devicePushToken.mockResolvedValueOnce("ExponentPushToken[this-phone]");
  await mount();
  await act(async () => { await current.signOut(); });
  await act(async () => { for (let i = 0; i < 10; i += 1) await Promise.resolve(); });
  expect(logoutSession).toHaveBeenCalledWith("access-a", "refresh-a", "ExponentPushToken[this-phone]");
});

it("still logs out when the push token cannot be read", async () => {
  const { devicePushToken } = jest.requireMock("@/features/notifications/model/pushNotifications");
  devicePushToken.mockRejectedValueOnce(new Error("expo push service down"));
  await mount();
  await act(async () => { await current.signOut(); });
  await act(async () => { for (let i = 0; i < 10; i += 1) await Promise.resolve(); });
  expect(logoutSession).toHaveBeenCalledWith("access-a", "refresh-a", null);
});

it("shows the account a sync returns without asking /auth/me again (NET-19)", async () => {
  await mount();
  (api.me as jest.Mock).mockClear();
  const synced = { ...userA, plan: "pro" } as User;
  const read = jest.fn(async () => synced);
  await act(async () => { await current.refreshUser(read); });
  expect(read).toHaveBeenCalledWith(current.token);
  expect(api.me).not.toHaveBeenCalled();
  expect(current.user?.plan).toBe("pro");
});

it("announces the profile fields the server saved, after it saved them", async () => {
  const update = deferred<User>();
  const saved = { ...userA, reminder_lead_minutes: 30 } as User;
  (api.me as jest.Mock).mockResolvedValueOnce({ ...userA, reminder_lead_minutes: 10 });
  (api.updateMe as jest.Mock).mockReturnValueOnce(update.promise).mockRejectedValueOnce(new Error("offline"));
  await mount();
  const announced = jest.fn();
  const stop = onAppEvent("userUpdated", announced);
  let pending!: Promise<void>;
  await act(async () => { pending = current.updateUser({ reminder_lead_minutes: 30, name: userA.name }); });
  // Shown at once, announced only once saved: the to-do list must not read the old instants.
  expect(announced).not.toHaveBeenCalled();
  await act(async () => { update.resolve(saved); await pending; });
  expect(announced).toHaveBeenCalledWith({ fields: ["reminder_lead_minutes"] });
  announced.mockClear();
  await act(async () => { await current.updateUser({ quiet_hours_enabled: true }).catch(() => {}); });
  expect(announced).not.toHaveBeenCalled();
  stop();
});

describe("the stored sign-in at launch", () => {
  const settle = async () => {
    for (let i = 0; i < 10; i += 1) await Promise.resolve();
  };

  it("is cleared when the record is corrupt, and the app opens on sign-in", async () => {
    (getToken as jest.Mock).mockRejectedValue(new CorruptSessionError());
    const rendered = await mount();

    expect(rendered.getByText("signed-out")).toBeTruthy();
    expect(rendered.queryByText("login.error_generic")).toBeNull();
    expect(clearToken).toHaveBeenCalledTimes(1);
    expect(clearCachedUser).toHaveBeenCalled();
    expect(clearSignedOutAccount).toHaveBeenCalledWith(userA.id);
    expect(api.me).not.toHaveBeenCalled();
    // Sign-in itself, not the introduction before it.
    expect(current.onboarded).toBe(true);
    expect(clearOnboarded).not.toHaveBeenCalled();
    // Counted once, and told nothing: not the record, a token or whose it was.
    expect(reportCorruptSessionCleared).toHaveBeenCalledTimes(1);
    expect(reportCorruptSessionCleared).toHaveBeenCalledWith();
  });

  it("is kept through a network error, and Retry restores it", async () => {
    (readCachedUser as jest.Mock).mockResolvedValue(null);
    (api.me as jest.Mock).mockRejectedValueOnce(new TypeError("Network request failed"));
    const rendered = await mount();

    expect(rendered.getByText("login.error_generic")).toBeTruthy();
    expect(rendered.getByRole("button", { name: "settings.sign_out" })).toBeTruthy();
    expect(clearToken).not.toHaveBeenCalled();

    await fireEvent.press(rendered.getByRole("button", { name: "common.retry" }));
    expect(current.user?.id).toBe(userA.id);
    expect(api.me).toHaveBeenCalledTimes(2);
    expect(clearToken).not.toHaveBeenCalled();
    // A read error is not a corrupt record: nothing was cleared, nothing counted as one.
    expect(reportCorruptSessionCleared).not.toHaveBeenCalled();
  });

  it("is kept when the keychain cannot be read yet", async () => {
    (getToken as jest.Mock).mockRejectedValueOnce(new Error("User interaction is not allowed"));
    const rendered = await mount();

    expect(rendered.getByText("login.error_generic")).toBeTruthy();
    expect(rendered.getByRole("button", { name: "settings.sign_out" })).toBeTruthy();
    expect(clearToken).not.toHaveBeenCalled();
    expect(reportCorruptSessionCleared).not.toHaveBeenCalled();
  });

  it("can be signed out of after a network error, the way Settings signs out", async () => {
    const jwt = `e30.${btoa(JSON.stringify({ sub: userA.id })).replace(/=+$/, "")}.sig`;
    (getToken as jest.Mock).mockResolvedValue(jwt);
    (readCachedUser as jest.Mock).mockResolvedValue(null);
    (api.me as jest.Mock).mockRejectedValue(new TypeError("Network request failed"));
    const rendered = await mount();

    await fireEvent.press(rendered.getByRole("button", { name: "settings.sign_out" }));
    await act(settle);

    expect(confirmDialog).toHaveBeenCalledWith(
      expect.objectContaining({ title: "settings.sign_out_confirm_title", destructive: true }),
    );
    expect(rendered.getByText("signed-out")).toBeTruthy();
    expect(rendered.queryByText("login.error_generic")).toBeNull();
    expect(clearToken).toHaveBeenCalledTimes(1);
    expect(clearSignedOutAccount).toHaveBeenCalledWith(userA.id);
    expect(clearOnboarded).toHaveBeenCalled();
    // The server forgets the session too, with the token the launch read.
    expect(logoutSession).toHaveBeenCalledWith(jwt, "refresh-a", null);
  });

  it("stays when the sign-out is cancelled", async () => {
    (readCachedUser as jest.Mock).mockResolvedValue(null);
    (api.me as jest.Mock).mockRejectedValue(new TypeError("Network request failed"));
    (confirmDialog as jest.Mock).mockResolvedValueOnce(false);
    const rendered = await mount();

    await fireEvent.press(rendered.getByRole("button", { name: "settings.sign_out" }));
    await act(settle);

    expect(rendered.getByText("login.error_generic")).toBeTruthy();
    expect(clearToken).not.toHaveBeenCalled();
  });

  it("opens the app when it is valid, and is never cleared", async () => {
    const rendered = await mount();

    expect(rendered.getByText("Alice")).toBeTruthy();
    expect(rendered.queryByRole("button", { name: "settings.sign_out" })).toBeNull();
    expect(clearToken).not.toHaveBeenCalled();
    expect(clearSignedOutAccount).not.toHaveBeenCalled();
    expect(reportCorruptSessionCleared).not.toHaveBeenCalled();
  });
});
