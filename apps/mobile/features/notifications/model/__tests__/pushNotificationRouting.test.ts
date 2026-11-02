jest.mock("@/lib/api", () => ({
  api: {
    registerPushToken: jest.fn(),
    unregisterPushToken: jest.fn(),
    recordProductEvents: jest.fn(),
    updateMe: jest.fn(),
  },
}));

// Analytics reads the session's token when it sends.
jest.mock("@/lib/auth", () => ({
  getToken: jest.fn(async () => "tok"),
  getSessionGeneration: () => 1,
}));

jest.mock("@/lib/cache/cacheFile", () => ({
  cacheFile: () => ({ read: async () => null, write: async () => undefined, clear: async () => undefined }),
}));

jest.mock("@/lib/installationId", () => ({
  getInstallationId: jest.fn().mockResolvedValue("dev-1"),
}));

jest.mock("expo-constants", () => ({
  __esModule: true,
  default: { expoConfig: { extra: { eas: { projectId: "p1" } } } },
}));

jest.mock("expo-notifications", () => ({
  getPermissionsAsync: jest.fn(),
  requestPermissionsAsync: jest.fn(),
  setNotificationChannelAsync: jest.fn(),
  getExpoPushTokenAsync: jest.fn(),
  setNotificationHandler: jest.fn(),
}));

jest.mock("react-native", () => ({
  Platform: { OS: "ios" },
  AppState: { addEventListener: () => ({ remove: jest.fn() }) },
}));

jest.mock("@/lib/syncRecords", () => ({ recentSyncAt: jest.fn(), recordSync: jest.fn() }));

import { handlePushNotificationResponse } from "@/features/notifications/model/pushNotifications";

function fakeRouter() {
  return { push: jest.fn(), replace: jest.fn() };
}

describe("handlePushNotificationResponse: retired kinds", () => {
  it.each(["email_suggestion", "calendar_nudge"])(
    "ignores a retired %s push still in the notification tray",
    async (type) => {
      const router = fakeRouter();
      await handlePushNotificationResponse(router, { type });
      expect(router.push).not.toHaveBeenCalled();
      expect(router.replace).not.toHaveBeenCalled();
    },
  );
});

describe("handlePushNotificationResponse: already on target", () => {
  it("replaces instead of stacking a duplicate route", async () => {
    const router = fakeRouter();
    await handlePushNotificationResponse(
      router,
      { type: "todo_due", todo_id: "t1" },
      "/todos",
    );
    expect(router.push).not.toHaveBeenCalled();
    expect(router.replace).toHaveBeenCalledWith({
      pathname: "/todos",
      params: { highlight: "t1" },
    });
  });
});
