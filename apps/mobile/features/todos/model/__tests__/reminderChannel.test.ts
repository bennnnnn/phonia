/**
 * Push and local reminders post to one Android channel. Creating it is a native call,
 * made once per run whichever of them asks first.
 */
import * as Notifications from "expo-notifications";

import { syncTodoReminders } from "@/features/todos/model/todoReminders";
import type { Todo } from "@/lib/api/types";
import { configurePushNotificationHandler } from "@/features/notifications/model/pushNotifications";

jest.mock("react-native", () => ({ Platform: { OS: "android" }, AppState: { addEventListener: jest.fn() } }));
jest.mock("@/lib/api", () => ({ api: {} }));
jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => 1, getToken: jest.fn(async () => "tok") }));
jest.mock("@/lib/i18n", () => ({ __esModule: true, default: { t: (key: string) => key } }));
jest.mock("@/lib/expoRuntime", () => ({ isExpoGo: () => false, isPhysicalDevice: () => true }));
jest.mock("@/lib/sentry", () => ({ reportPushUnregisterFailed: jest.fn() }));
jest.mock("@/lib/installationId", () => ({ getInstallationId: jest.fn(async () => "dev-1") }));
jest.mock("@/lib/reportRecoverableError", () => ({ reportRecoverableWarning: jest.fn() }));
jest.mock("@/lib/syncRecords", () => ({ recentSyncAt: jest.fn(), recordSync: jest.fn(), forgetSyncRecords: jest.fn() }));
jest.mock("expo-constants", () => ({ __esModule: true, default: { expoConfig: { extra: {} } } }));
jest.mock("expo-notifications", () => ({
  setNotificationChannelAsync: jest.fn(async () => null),
  setNotificationHandler: jest.fn(),
  getPermissionsAsync: jest.fn(async () => ({ status: "granted" })),
  getAllScheduledNotificationsAsync: jest.fn(async () => []),
  cancelScheduledNotificationAsync: jest.fn(),
  scheduleNotificationAsync: jest.fn(async () => "id"),
  AndroidImportance: { HIGH: 4 },
  SchedulableTriggerInputTypes: { DATE: "date" },
}));

const todo: Todo = {
  id: "t1", content: "Flight", topic: "Reminders", checked: false, due_at: "2099-01-01T12:00:00Z",
  created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-01T00:00:00Z", sort_order: null, chat_id: null,
  notify_at: "2099-01-01T11:50:00Z",
};

it("creates the reminders channel once for launch and a local reminder sync", async () => {
  configurePushNotificationHandler();
  await syncTodoReminders([todo], { remotePush: false });

  expect(Notifications.scheduleNotificationAsync).toHaveBeenCalledTimes(1);
  expect(Notifications.setNotificationChannelAsync).toHaveBeenCalledTimes(1);
});
