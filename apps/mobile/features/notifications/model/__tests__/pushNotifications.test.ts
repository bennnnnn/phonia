import type { ActionFeedbackApi } from "@/contexts/actionFeedbackCore";

jest.mock("@/lib/api", () => ({
  api: {
    registerPushToken: jest.fn().mockResolvedValue(undefined),
    unregisterPushToken: jest.fn().mockResolvedValue(undefined),
    recordProductEvents: jest.fn().mockResolvedValue(undefined),
    updateMe: jest.fn().mockResolvedValue({}),
  },
}));

// Analytics reads the session's token when it sends; a sign-out moves the generation.
let mockGeneration = 1;
const mockReportUnregisterFailed = jest.fn();
jest.mock("@/lib/sentry", () => ({
  reportPushUnregisterFailed: (error: unknown) => mockReportUnregisterFailed(error),
}));
jest.mock("@/lib/auth", () => ({
  getToken: jest.fn(async () => "tok"),
  getSessionGeneration: () => mockGeneration,
}));

jest.mock("@/lib/installationId", () => ({
  getInstallationId: jest.fn().mockResolvedValue("dev-1"),
}));

jest.mock("expo-constants", () => ({
  __esModule: true,
  default: { expoConfig: { extra: { eas: { projectId: "p1" } } } },
}));

jest.mock("expo-notifications", () => ({
  getPermissionsAsync: jest.fn().mockResolvedValue({ status: "granted" }),
  requestPermissionsAsync: jest.fn().mockResolvedValue({ status: "granted" }),
  setNotificationChannelAsync: jest.fn().mockResolvedValue(undefined),
  getExpoPushTokenAsync: jest.fn().mockResolvedValue({ data: "ExponentPushToken[abc]" }),
  getDevicePushTokenAsync: jest.fn().mockResolvedValue({ type: "ios", data: "apns-token-1" }),
  setNotificationHandler: jest.fn(),
  AndroidImportance: { HIGH: 4, DEFAULT: 3 },
}));

jest.mock("@/lib/expoRuntime", () => ({
  isExpoGo: jest.fn(() => false),
  isPhysicalDevice: jest.fn(() => true),
}));

jest.mock("@/lib/reportRecoverableError", () => ({ reportRecoverableWarning: jest.fn() }));

/** The file prefs `lib/syncRecords.ts` keeps, which outlive a cold start. */
const mockSyncRecords = new Map<string, { account: string; variant: string; at: number }>();
jest.mock("@/lib/syncRecords", () => ({
  recentSyncAt: jest.fn(async (kind: string, account: string, maxAgeMs: number, variant = "") => {
    const record = mockSyncRecords.get(kind);
    if (!record || record.account !== account || record.variant !== variant) return null;
    const age = Date.now() - record.at;
    return age >= 0 && age < maxAgeMs ? record.at : null;
  }),
  recordSync: jest.fn(async (kind: string, account: string, variant = "", at = Date.now()) => {
    mockSyncRecords.set(kind, { account, variant, at });
  }),
  forgetSyncRecords: jest.fn(async () => { mockSyncRecords.clear(); }),
}));

const mockAppStateHandlers = new Set<(state: string) => void>();

jest.mock("react-native", () => ({
  Platform: { OS: "ios" },
  AppState: {
    addEventListener: (_event: string, handler: (state: string) => void) => {
      mockAppStateHandlers.add(handler);
      return { remove: jest.fn(() => mockAppStateHandlers.delete(handler)) };
    },
  },
}));

import { Platform } from "react-native";
import * as Notifications from "expo-notifications";

import { api } from "@/lib/api";
import {
  attachPushForegroundSync,
  clearPushSyncRecord,
  ensureNotificationPermission,
  getNotificationPermissionGranted,
  registerRemotePushToken,
  unregisterRemotePushToken,
} from "@/features/notifications/model/pushNotifications";

const registerMock = api.registerPushToken as jest.MockedFunction<typeof api.registerPushToken>;
const unregisterMock = api.unregisterPushToken as jest.MockedFunction<
  typeof api.unregisterPushToken
>;
const updateMeMock = api.updateMe as jest.MockedFunction<typeof api.updateMe>;

describe("push gating on user.push_notifications_enabled", () => {
  beforeEach(() => {
    Platform.OS = "ios";
    registerMock.mockClear();
    unregisterMock.mockClear();
    updateMeMock.mockClear();
    (api.recordProductEvents as jest.Mock).mockClear();
    (Notifications.getPermissionsAsync as jest.Mock).mockResolvedValue({ status: "granted" });
    (Notifications.requestPermissionsAsync as jest.Mock).mockReset();
    (Notifications.requestPermissionsAsync as jest.Mock).mockResolvedValue({ status: "granted" });
  });

  it("registerRemotePushToken registers when pushNotificationsEnabled=true", async () => {
    await expect(registerRemotePushToken("tok", true)).resolves.toBe("registered");
    expect(registerMock).toHaveBeenCalledTimes(1);
    expect(registerMock).toHaveBeenCalledWith(
      "tok",
      expect.objectContaining({
        expo_push_token: "ExponentPushToken[abc]",
        device_id: "dev-1",
      }),
    );
    expect(registerMock.mock.calls[0]?.[1]).not.toHaveProperty("android_channels");
    expect(updateMeMock).not.toHaveBeenCalled();
  });

  it("registerRemotePushToken tells the API this Android install created the tone channels", async () => {
    Platform.OS = "android";
    await expect(registerRemotePushToken("tok", true)).resolves.toBe("registered");
    expect(registerMock).toHaveBeenCalledWith(
      "tok",
      expect.objectContaining({ android_channels: "tone", platform: "android" }),
    );
  });

  it("records the result only when the OS permission prompt is shown", async () => {
    (Notifications.getPermissionsAsync as jest.Mock).mockResolvedValue({ status: "denied" });
    (Notifications.requestPermissionsAsync as jest.Mock).mockResolvedValue({ status: "denied" });

    await expect(ensureNotificationPermission()).resolves.toBe(false);
    await new Promise<void>((resolve) => setTimeout(resolve, 0));

    expect(api.recordProductEvents).toHaveBeenCalledWith(
      "tok",
      expect.arrayContaining([
        expect.objectContaining({
          name: "push_permission",
          properties: { status: "denied" },
        }),
      ]),
    );
  });

  it("registerRemotePushToken is a no-op when pushNotificationsEnabled=false", async () => {
    // Without this gate, the backend holds a live push token for a user who
    // opted out and keeps sending them notifications.
    await expect(registerRemotePushToken("tok", false)).resolves.toBe("skipped");
    expect(registerMock).not.toHaveBeenCalled();
    expect(updateMeMock).not.toHaveBeenCalled();
  });

  it("registerRemotePushToken flips the server pref off when OS permission is denied", async () => {
    (Notifications.getPermissionsAsync as jest.Mock).mockResolvedValue({ status: "denied" });
    (Notifications.requestPermissionsAsync as jest.Mock).mockResolvedValue({ status: "denied" });

    await expect(registerRemotePushToken("tok", true)).resolves.toBe("disabled_permission");
    expect(registerMock).not.toHaveBeenCalled();
    expect(updateMeMock).toHaveBeenCalledWith("tok", { push_notifications_enabled: false });
  });

  it("getNotificationPermissionGranted is read-only and does not prompt", async () => {
    (Notifications.getPermissionsAsync as jest.Mock).mockResolvedValue({ status: "denied" });
    await expect(getNotificationPermissionGranted()).resolves.toBe(false);
    expect(Notifications.requestPermissionsAsync).not.toHaveBeenCalled();
  });

  it("unregisterRemotePushToken calls the server unregister endpoint", async () => {
    await unregisterRemotePushToken("tok");
    expect(unregisterMock).toHaveBeenCalledTimes(1);
    expect(unregisterMock).toHaveBeenCalledWith(
      "tok",
      expect.objectContaining({ expo_push_token: "ExponentPushToken[abc]" }),
    );
  });

  it("unregisterRemotePushToken reports a failed removal instead of hiding it", async () => {
    const failure = new Error("422");
    unregisterMock.mockRejectedValueOnce(failure);
    await expect(unregisterRemotePushToken("tok")).resolves.toBe(false);
    expect(mockReportUnregisterFailed).toHaveBeenCalledWith(failure);
  });

  it("registerRemotePushToken throws when the Expo token cannot be resolved", async () => {
    (Notifications.getExpoPushTokenAsync as jest.Mock).mockRejectedValueOnce(new Error("no eas"));
    await expect(registerRemotePushToken("tok", true)).rejects.toThrow("push_token_unavailable");
    expect(registerMock).not.toHaveBeenCalled();
  });

  it("registerRemotePushToken throws when the API register call fails", async () => {
    registerMock.mockRejectedValueOnce(new Error("rebind rejected"));
    await expect(registerRemotePushToken("tok", true)).rejects.toThrow("rebind rejected");
  });

  it("attachPushForegroundSync returns a cleanup function and does not throw", () => {
    // The register/unregister behaviour is covered by the direct tests above;
    // here we just verify the sync contract: returns a cleanup fn, no throw.
    const cleanupOn = attachPushForegroundSync("tok", true);
    expect(typeof cleanupOn).toBe("function");
    cleanupOn();

    const cleanupOff = attachPushForegroundSync("tok", false);
    expect(typeof cleanupOff).toBe("function");
    cleanupOff();
  });

  it("attachPushForegroundSync notifies when permission denial disables the pref", async () => {
    (Notifications.getPermissionsAsync as jest.Mock).mockResolvedValue({ status: "denied" });
    (Notifications.requestPermissionsAsync as jest.Mock).mockResolvedValue({ status: "denied" });
    const onPref = jest.fn();
    const cleanup = attachPushForegroundSync("tok", true, onPref);
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
    expect(onPref).toHaveBeenCalledWith(false);
    cleanup();
  });

  it("attachPushForegroundSync is a no-op when apiToken is null", () => {
    const cleanup = attachPushForegroundSync(null, true);
    expect(typeof cleanup).toBe("function");
    cleanup();
    expect(registerMock).not.toHaveBeenCalled();
    expect(unregisterMock).not.toHaveBeenCalled();
  });
});

describe("whether the server holds this device's token (local reminders follow it)", () => {
  const { remotePushRegistered, subscribeRemotePushRegistered } =
    jest.requireActual<typeof import("@/features/notifications/model/pushRegistration")>("@/features/notifications/model/pushRegistration");

  beforeEach(async () => {
    Platform.OS = "ios";
    registerMock.mockClear();
    registerMock.mockResolvedValue(undefined);
    (Notifications.getPermissionsAsync as jest.Mock).mockResolvedValue({ status: "granted" });
    (Notifications.requestPermissionsAsync as jest.Mock).mockResolvedValue({ status: "granted" });
    (Notifications.getExpoPushTokenAsync as jest.Mock).mockResolvedValue({ data: "ExponentPushToken[abc]" });
    await clearPushSyncRecord();
  });

  it("is true only after the server accepted the token, and tells subscribers", async () => {
    const seen: boolean[] = [];
    const stop = subscribeRemotePushRegistered(() => seen.push(remotePushRegistered()));
    expect(remotePushRegistered()).toBe(false);
    await registerRemotePushToken("tok", true);
    expect(remotePushRegistered()).toBe(true);
    stop();
    expect(seen).toEqual([true]);
  });

  it("stays false when no token can be had: Expo Go, no project, a failed request", async () => {
    (Notifications.getExpoPushTokenAsync as jest.Mock).mockRejectedValueOnce(new Error("no token"));
    await expect(registerRemotePushToken("tok", true)).rejects.toThrow();
    expect(remotePushRegistered()).toBe(false);
    registerMock.mockRejectedValueOnce(new Error("offline"));
    await expect(registerRemotePushToken("tok", true)).rejects.toThrow("offline");
    expect(remotePushRegistered()).toBe(false);
  });

  it("goes false when push is switched off, permission is denied, or the user signs out", async () => {
    await registerRemotePushToken("tok", true);
    await unregisterRemotePushToken("tok");
    expect(remotePushRegistered()).toBe(false);

    await registerRemotePushToken("tok", true);
    await registerRemotePushToken("tok", false);
    expect(remotePushRegistered()).toBe(false);

    await registerRemotePushToken("tok", true);
    (Notifications.getPermissionsAsync as jest.Mock).mockResolvedValue({ status: "denied" });
    (Notifications.requestPermissionsAsync as jest.Mock).mockResolvedValue({ status: "denied" });
    await registerRemotePushToken("tok", true);
    expect(remotePushRegistered()).toBe(false);

    (Notifications.getPermissionsAsync as jest.Mock).mockResolvedValue({ status: "granted" });
    await registerRemotePushToken("tok", true);
    await clearPushSyncRecord();
    expect(remotePushRegistered()).toBe(false);
  });
});

describe("push re-sync on launch, token refresh and foreground", () => {
  const tokenMock = Notifications.getExpoPushTokenAsync as jest.Mock;
  const settle = () => new Promise<void>((resolve) => setTimeout(resolve, 0));
  const foreground = async () => {
    for (const handler of [...mockAppStateHandlers]) handler("active");
    await settle();
  };
  // The signed-in account: a fresh one per test.
  let n = 100;
  let account = "user-100";

  beforeEach(() => {
    n += 1;
    account = `user-${n}`;
    mockSyncRecords.clear();
    Platform.OS = "ios";
    jest.clearAllMocks();
    mockAppStateHandlers.clear();
    (Notifications.getPermissionsAsync as jest.Mock).mockResolvedValue({ status: "granted" });
  });
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("re-registers at most twice a day, not on every return to the app", async () => {
    const cleanup = attachPushForegroundSync("tok", true, undefined, account);
    await settle();
    expect(registerMock).toHaveBeenCalledTimes(1);
    expect(tokenMock).toHaveBeenCalledTimes(1);

    // Each sync was a request to Expo's push service plus one to our API.
    await foreground();
    await foreground();
    await foreground();
    expect(registerMock).toHaveBeenCalledTimes(1);
    expect(tokenMock).toHaveBeenCalledTimes(1);

    const now = Date.now();
    jest.spyOn(Date, "now").mockReturnValue(now + 13 * 60 * 60_000);
    await foreground();
    expect(registerMock).toHaveBeenCalledTimes(2);
    cleanup();
  });

  it("does not register again when the hourly token refresh re-attaches", async () => {
    attachPushForegroundSync("tok", true, undefined, account)();
    await settle();
    attachPushForegroundSync("tok-refreshed", true, undefined, account)();
    await settle();
    expect(registerMock).toHaveBeenCalledTimes(1);
  });

  it("registers again after another account signs in on this device", async () => {
    attachPushForegroundSync("tok-a", true, undefined, account)();
    await settle();
    // Another account's sign-in rebinds the device token to that account.
    attachPushForegroundSync("tok-b", true, undefined, `${account}-other`)();
    await settle();
    expect(registerMock).toHaveBeenCalledTimes(2);
  });

  it("does not register again on a cold start within 12 hours (NET-19)", async () => {
    attachPushForegroundSync("tok", true, undefined, account)();
    await settle();
    expect(registerMock).toHaveBeenCalledTimes(1);
    // A new process: module memory is gone, the file is not.
    let reloaded!: typeof import("@/features/notifications/model/pushNotifications");
    jest.isolateModules(() => {
      reloaded = jest.requireActual<typeof import("@/features/notifications/model/pushNotifications")>("@/features/notifications/model/pushNotifications");
    });
    reloaded.attachPushForegroundSync("tok", true, undefined, account)();
    await settle();
    expect(registerMock).toHaveBeenCalledTimes(1);
    expect(tokenMock).toHaveBeenCalledTimes(1);
  });

  it("registers again after sign-out, which forgets the device's token on the server", async () => {
    attachPushForegroundSync("tok", true, undefined, account)();
    await settle();
    await clearPushSyncRecord();
    attachPushForegroundSync("tok-again", true, undefined, account)();
    await settle();
    expect(registerMock).toHaveBeenCalledTimes(2);
  });

  it("does not let a sync that ends after sign-out vouch for the next sign-in", async () => {
    registerMock.mockImplementationOnce(async () => { mockGeneration += 1; });
    attachPushForegroundSync("tok", true, undefined, account)();
    await settle();
    expect(mockSyncRecords.size).toBe(0);
    attachPushForegroundSync("tok-next", true, undefined, account)();
    await settle();
    expect(registerMock).toHaveBeenCalledTimes(2);
  });

  it("still notices a permission turned off in Settings on return", async () => {
    const onPref = jest.fn();
    const cleanup = attachPushForegroundSync("tok", true, onPref, account);
    await settle();
    (Notifications.getPermissionsAsync as jest.Mock).mockResolvedValue({ status: "denied" });
    (Notifications.requestPermissionsAsync as jest.Mock).mockResolvedValue({ status: "denied" });
    await foreground();
    expect(onPref).toHaveBeenCalledWith(false);
    expect(updateMeMock).toHaveBeenCalledWith("tok", { push_notifications_enabled: false });
    cleanup();
  });

  it("retries on the next return after a failed sync", async () => {
    registerMock.mockRejectedValueOnce(new Error("offline"));
    const cleanup = attachPushForegroundSync("tok", true, undefined, account);
    await settle();
    await foreground();
    expect(registerMock).toHaveBeenCalledTimes(2);
    cleanup();
  });

  it("unregisters once for a user who turned push off, and retries a failure", async () => {
    unregisterMock.mockRejectedValueOnce(new Error("offline"));
    const cleanup = attachPushForegroundSync("tok", false, undefined, account);
    await settle();
    await foreground();
    await foreground();
    expect(unregisterMock).toHaveBeenCalledTimes(2);
    cleanup();
  });
});

describe("push sync across a cold start", () => {
  const settle = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

  /** A new app run: nothing in memory, the same files on disk. */
  function coldStart() {
    jest.resetModules();
    mockAppStateHandlers.clear();
    return {
      push: jest.requireActual<typeof import("@/features/notifications/model/pushNotifications")>("@/features/notifications/model/pushNotifications"),
      api: jest.requireMock<{ api: Record<string, jest.Mock> }>("@/lib/api").api,
      notifications: jest.requireMock<Record<string, jest.Mock>>("expo-notifications"),
    };
  }

  async function launch(account: string, enabled = true, deviceToken: string | null = "apns-token-1") {
    const run = coldStart();
    if (deviceToken === null) {
      run.notifications.getDevicePushTokenAsync.mockRejectedValue(new Error("no APNs"));
    } else {
      run.notifications.getDevicePushTokenAsync.mockResolvedValue({ type: "ios", data: deviceToken });
    }
    run.push.attachPushForegroundSync("tok", enabled, undefined, account, null)();
    await settle();
    return run;
  }

  beforeEach(() => {
    mockSyncRecords.clear();
  });
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("a sync an earlier launch made still counts as registered, so reminders are not doubled", async () => {
    await launch("user-9");
    const second = await launch("user-9");
    expect(second.api.registerPushToken).not.toHaveBeenCalled();
    expect(jest.requireActual<typeof import("@/features/notifications/model/pushRegistration")>("@/features/notifications/model/pushRegistration").remotePushRegistered()).toBe(true);
  });

  it("does not register again when this account synced within the last 12 hours", async () => {
    const first = await launch("user-1");
    expect(first.api.registerPushToken).toHaveBeenCalledTimes(1);

    const second = await launch("user-1");
    expect(second.api.registerPushToken).not.toHaveBeenCalled();
    expect(second.notifications.getExpoPushTokenAsync).not.toHaveBeenCalled();
    // The OS permission is still read: turning it off must reach the server.
    expect(second.notifications.getPermissionsAsync).toHaveBeenCalled();
  });

  it("registers again for another account, another setting, or after 12 hours", async () => {
    await launch("user-1");
    expect((await launch("user-2")).api.registerPushToken).toHaveBeenCalledTimes(1);
    expect((await launch("user-2", false)).api.unregisterPushToken).toHaveBeenCalledTimes(1);

    await launch("user-1");
    const now = Date.now();
    jest.spyOn(Date, "now").mockReturnValue(now + 13 * 60 * 60_000);
    expect((await launch("user-1")).api.registerPushToken).toHaveBeenCalledTimes(1);
  });

  it("registers again when the push service rolled this install's token since", async () => {
    await launch("user-1", true, "apns-token-1");
    const rolled = await launch("user-1", true, "apns-token-2");
    expect(rolled.api.registerPushToken).toHaveBeenCalledTimes(1);
    // The record keeps a fingerprint of the token, never the token.
    expect(JSON.stringify([...mockSyncRecords.values()])).not.toContain("apns-token");
  });

  it("trusts no record when the device token cannot be read", async () => {
    await launch("user-1", true, null);
    expect(mockSyncRecords.size).toBe(0);
    expect((await launch("user-1", true, null)).api.registerPushToken).toHaveBeenCalledTimes(1);
  });

  it("keeps no record without the account, as the Settings switch calls it", async () => {
    await launch("");
    expect(mockSyncRecords.size).toBe(0);
  });
});

describe("push token failures are reported, routine states stay quiet", () => {
  const settle = () => new Promise<void>((resolve) => setTimeout(resolve, 0));
  const feedback: ActionFeedbackApi = {
    show: jest.fn(),
    success: jest.fn(),
    info: jest.fn(),
    warning: jest.fn(),
    error: jest.fn(),
    dismiss: jest.fn(),
  };
  const UNAVAILABLE = "Push notifications aren't working on this device right now.";

  /** A fresh module per test: the report is once per app run. */
  function load() {
    jest.resetModules();
    mockAppStateHandlers.clear();
    mockSyncRecords.clear();
    return {
      push: jest.requireActual<typeof import("@/features/notifications/model/pushNotifications")>("@/features/notifications/model/pushNotifications"),
      notifications: jest.requireMock<Record<string, jest.Mock>>("expo-notifications"),
      runtime: jest.requireMock<Record<string, jest.Mock>>("@/lib/expoRuntime"),
      report: jest.requireMock<Record<string, jest.Mock>>("@/lib/reportRecoverableError")
        .reportRecoverableWarning,
    };
  }
  const foreground = async () => {
    for (const handler of [...mockAppStateHandlers]) handler("active");
    await settle();
  };
  const tokenError = (code: string) =>
    Object.assign(new Error("received: ExponentPushToken[secret-device-token]"), { code });

  let warn: jest.SpyInstance;
  beforeEach(() => {
    warn = jest.spyOn(console, "warn").mockImplementation(() => {});
  });
  afterEach(() => {
    warn.mockRestore();
  });

  it("warns once per app run when push is off for no routine reason", async () => {
    const { push, notifications, report } = load();
    notifications.getExpoPushTokenAsync.mockRejectedValue(tokenError("ERR_NOTIFICATIONS_SERVER_ERROR"));
    const cleanup = push.attachPushForegroundSync("tok", true, undefined, "u1", feedback);
    await settle();
    // A failed sync retries on every return to the app; the warning does not.
    await foreground();
    await foreground();
    cleanup();
    expect(notifications.getExpoPushTokenAsync).toHaveBeenCalledTimes(3);
    expect(report).toHaveBeenCalledTimes(1);
    expect(report).toHaveBeenCalledWith(feedback, UNAVAILABLE);
    // The log names the error code, never Expo's message (it can carry the token).
    expect(warn).toHaveBeenCalledWith(expect.stringContaining("ERR_NOTIFICATIONS_SERVER_ERROR"));
    expect(JSON.stringify(warn.mock.calls)).not.toContain("secret-device-token");
  });

  it("warns when the token for turning push off cannot be read either", async () => {
    const { push, notifications, report } = load();
    notifications.getExpoPushTokenAsync.mockRejectedValue(new Error("E_REGISTRATION_FAILED"));
    push.attachPushForegroundSync("tok", false, undefined, "u1", feedback)();
    await settle();
    expect(report).toHaveBeenCalledWith(feedback, UNAVAILABLE);
  });

  it.each([
    ["offline (the next sync retries)", () => {}, tokenError("ERR_NOTIFICATIONS_NETWORK_ERROR")],
    ["in Expo Go", (m: ReturnType<typeof load>) => m.runtime.isExpoGo.mockReturnValue(true), new Error("removed from Expo Go")],
    ["on a simulator", (m: ReturnType<typeof load>) => m.runtime.isPhysicalDevice.mockReturnValue(false), new Error("no APNs")],
    [
      "with notifications denied",
      (m: ReturnType<typeof load>) => m.notifications.getPermissionsAsync.mockResolvedValue({ status: "denied" }),
      new Error("no token"),
    ],
  ])("stays quiet %s", async (_state, arrange, error) => {
    const loaded = load();
    arrange(loaded);
    loaded.notifications.getExpoPushTokenAsync.mockRejectedValue(error);
    // Unregister reads the token whatever the permission says.
    loaded.push.attachPushForegroundSync("tok", false, undefined, "u1", feedback)();
    await settle();
    expect(loaded.notifications.getExpoPushTokenAsync).toHaveBeenCalled();
    expect(loaded.report).not.toHaveBeenCalled();
  });

  it("stays quiet without an EAS project id, as before", async () => {
    const loaded = load();
    const constants = jest.requireMock<{ default: { expoConfig: unknown } }>("expo-constants");
    const config = constants.default.expoConfig;
    constants.default.expoConfig = {};
    try {
      loaded.push.attachPushForegroundSync("tok", true, undefined, "u1", feedback)();
      await settle();
    } finally {
      constants.default.expoConfig = config;
    }
    expect(loaded.notifications.getExpoPushTokenAsync).not.toHaveBeenCalled();
    expect(loaded.report).not.toHaveBeenCalled();
  });

  it("leaves the Settings switch to report its own failure", async () => {
    const { push, notifications, report } = load();
    notifications.getExpoPushTokenAsync.mockRejectedValue(new Error("E_REGISTRATION_FAILED"));
    await expect(push.registerRemotePushToken("tok", true)).rejects.toThrow("push_token_unavailable");
    expect(report).not.toHaveBeenCalled();
  });
});
