import * as Notifications from "expo-notifications";

import { cancelAllTodoReminders, syncTodoReminders } from "@/features/todos/model/todoReminders";
import type { Todo } from "@/lib/api/types";
import { refreshPhoneClock } from "@/lib/datetime/format";
import type { HourCycle } from "@/lib/datetime/phoneClock";

/**
 * A phone without push schedules its own alert, which says the to-do's time in the app's
 * language, the phone's 12/24-hour clock and its zone. The alert was written again only
 * when the to-do's text, due time, topic or notify_at changed, so after a change of
 * language or clock it still spoke the old one.
 */
let mockLanguage = "en";
let mockHourCycle: HourCycle = "h12";
let mockZone = "UTC";
const scheduled = new Map<string, unknown>();
jest.mock("react-native", () => ({ Platform: { OS: "ios" } }));
jest.mock("@/lib/expoRuntime", () => ({ isExpoGo: () => false }));
jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => 1 }));
jest.mock("@/features/notifications/model/pushNotifications", () => ({
  ensureNotificationPermission: jest.fn(async () => true),
  ensureReminderChannel: jest.fn(async () => undefined),
}));
// The app's language: the alert's words; the time inside it is formatDate's.
jest.mock("@/lib/i18n", () => ({
  t: (key: string, values?: { time?: string }) => `${mockLanguage}:${key}${values?.time ? `:${values.time}` : ""}`,
}));
jest.mock("@/lib/datetime/phoneClock", () => ({
  ...jest.requireActual("@/lib/datetime/phoneClock"),
  readPhoneClock: () => ({ timeZone: mockZone, hourCycle: mockHourCycle }),
}));
jest.mock("expo-notifications", () => ({
  getPermissionsAsync: jest.fn(async () => ({ status: "granted" })),
  getAllScheduledNotificationsAsync: jest.fn(async () => [...scheduled.keys()].map((identifier) => ({ identifier }))),
  cancelScheduledNotificationAsync: jest.fn(async (id: string) => { scheduled.delete(id); }),
  scheduleNotificationAsync: jest.fn(async (item: { identifier: string; trigger: unknown }) => {
    scheduled.set(item.identifier, item.trigger);
    return item.identifier;
  }),
  SchedulableTriggerInputTypes: { DATE: "date" },
}));

const todo: Todo = {
  id: "t1", content: "Call Sam", topic: "Reminders", checked: false, due_at: "2099-01-01T23:30:00Z",
  created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-01T00:00:00Z", sort_order: null, chat_id: null,
  notify_at: "2099-01-01T23:20:00Z",
};
type Written = { content: { title: string; body: string } };
const written = () => jest.mocked(Notifications.scheduleNotificationAsync).mock.calls
  .map(([item]) => `${(item as Written).content.title} | ${(item as Written).content.body.replace(/\s/g, " ")}`);
const sync = () => syncTodoReminders([todo], { remotePush: false });

beforeEach(async () => {
  await cancelAllTodoReminders();
  jest.clearAllMocks();
  scheduled.clear();
  mockLanguage = "en";
  mockHourCycle = "h12";
  mockZone = "UTC";
  refreshPhoneClock();
});

it("writes the alert again in a new language, 12/24-hour clock or zone, and only then", async () => {
  await sync();
  await sync();
  mockHourCycle = "h23";
  refreshPhoneClock();
  await sync();
  mockLanguage = "de";
  await sync();
  await sync();
  mockZone = "Asia/Kathmandu";
  refreshPhoneClock();
  await sync();
  expect(written()).toEqual([
    "en:notifications.todo_reminder_title | en:notifications.todo_reminder_body:11:30 PM",
    "en:notifications.todo_reminder_title | en:notifications.todo_reminder_body:23:30",
    "de:notifications.todo_reminder_title | de:notifications.todo_reminder_body:23:30",
    "de:notifications.todo_reminder_title | de:notifications.todo_reminder_body:05:15",
  ]);
  // One alert, replaced each time, still at the server's notify_at.
  expect([...scheduled.entries()]).toEqual([
    ["todo-due-t1", { type: "date", date: new Date("2099-01-01T23:20:00Z") }],
  ]);
});
