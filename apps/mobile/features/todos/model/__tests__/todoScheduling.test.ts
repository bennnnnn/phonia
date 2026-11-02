import * as Notifications from "expo-notifications";
import {
  cancelAllTodoReminders,
  MAX_SCHEDULED_REMINDERS,
  syncTodoReminders,
  todoNotificationId,
} from "@/features/todos/model/todoReminders";
import { ensureNotificationPermission } from "@/features/notifications/model/pushNotifications";
import type { Todo } from "@/lib/api/types";
let mockSession = 1;
const scheduled = new Map<string, unknown>();
const todo: Todo = { id: "t1", content: "Flight", topic: "Reminders", checked: false,
  due_at: "2099-01-01T12:00:00Z", created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z", sort_order: null, chat_id: null, notify_at: "2099-01-01T11:50:00Z" };
jest.mock("react-native", () => ({ Platform: { OS: "ios" } }));
let mockExpoGo = false;
jest.mock("@/lib/expoRuntime", () => ({ isExpoGo: () => mockExpoGo }));
jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => mockSession }));
jest.mock("@/features/notifications/model/pushNotifications", () => ({
  ensureNotificationPermission: jest.fn(async () => true),
  ensureReminderChannel: jest.fn(async () => undefined),
}));
jest.mock("@/lib/i18n", () => ({ t: (key: string) => key }));
jest.mock("expo-notifications", () => ({
  getPermissionsAsync: jest.fn(), getAllScheduledNotificationsAsync: jest.fn(),
  cancelScheduledNotificationAsync: jest.fn(), scheduleNotificationAsync: jest.fn(),
  SchedulableTriggerInputTypes: { DATE: "date" },
}));
beforeEach(async () => {
  jest.clearAllMocks(); mockSession = 1; scheduled.clear(); mockExpoGo = false;
  jest.mocked(Notifications.getPermissionsAsync).mockResolvedValue({ status: "granted" } as never);
  jest.mocked(Notifications.getAllScheduledNotificationsAsync).mockImplementation(async () =>
    [...scheduled.keys()].map((identifier) => ({ identifier })) as never);
  jest.mocked(Notifications.cancelScheduledNotificationAsync).mockImplementation(async (id) => { scheduled.delete(id); });
  jest.mocked(Notifications.scheduleNotificationAsync).mockImplementation(async (item) => {
    scheduled.set(item.identifier!, item.trigger); return item.identifier!;
  });
  await cancelAllTodoReminders();
});

it("never requests OS permission from background synchronization", async () => {
  await syncTodoReminders([todo], { remotePush: false });
  expect(ensureNotificationPermission).not.toHaveBeenCalled();
  expect(Notifications.getPermissionsAsync).toHaveBeenCalled();
});

it.each([
  [false, "recall_notify.wav"],
  [true, "default"],
])("a reminder in Expo Go %s plays %s, never a sound Expo Go lacks", async (expoGo, sound) => {
  mockExpoGo = expoGo;
  await syncTodoReminders([todo], { remotePush: false });
  expect(Notifications.scheduleNotificationAsync).toHaveBeenCalledWith(
    expect.objectContaining({ content: expect.objectContaining({ sound }) }),
  );
});

it("waits for an already-started native schedule before cancelling on signout", async () => {
  let finish!: () => void;
  let started!: () => void;
  const began = new Promise<void>((resolve) => { started = resolve; });
  jest.mocked(Notifications.scheduleNotificationAsync).mockImplementationOnce(async (item) => {
    started(); await new Promise<void>((resolve) => { finish = resolve; });
    scheduled.set(item.identifier!, item.trigger); return item.identifier!;
  });
  const old = syncTodoReminders([todo], { remotePush: false });
  await began;
  mockSession++;
  const clearing = cancelAllTodoReminders();
  finish();
  await Promise.all([old, clearing]);
  expect(scheduled.size).toBe(0);
});

it("keeps the latest due date when native scheduling finishes out of order", async () => {
  let finish!: () => void;
  let started!: () => void;
  const began = new Promise<void>((resolve) => { started = resolve; });
  jest.mocked(Notifications.scheduleNotificationAsync).mockImplementationOnce(async (item) => {
    started(); await new Promise<void>((resolve) => { finish = resolve; });
    scheduled.set(item.identifier!, item.trigger); return item.identifier!;
  });
  const old = syncTodoReminders([todo], { remotePush: false });
  await began;
  const changed = { ...todo, due_at: "2099-01-02T12:00:00Z", notify_at: "2099-01-02T11:50:00Z" };
  const latest = syncTodoReminders([changed], { remotePush: false });
  await Promise.resolve(); await Promise.resolve();
  finish();
  await Promise.all([old, latest]);
  expect(scheduled.get(todoNotificationId(todo.id))).toMatchObject({ date: new Date("2099-01-02T11:50:00Z") });
});

it("removes local reminders when the server holds this device's push token", async () => {
  scheduled.set(todoNotificationId(todo.id), {});
  await syncTodoReminders([todo], { remotePush: true });
  expect(scheduled.size).toBe(0);
});

it("removes local reminders when the Reminders alert is switched off", async () => {
  scheduled.set(todoNotificationId(todo.id), {});
  await syncTodoReminders([todo], { remotePush: false, remindersEnabled: false });
  expect(scheduled.size).toBe(0);
  expect(Notifications.scheduleNotificationAsync).not.toHaveBeenCalled();
});

it("does not schedule unconfirmed optimistic reminders", async () => {
  await syncTodoReminders([{ ...todo, id: "local-create" }], { remotePush: false });
  expect(Notifications.scheduleNotificationAsync).not.toHaveBeenCalled();
});

it("ignores a sync retained from an old account before touching the device", async () => {
  mockSession++;
  jest.mocked(Notifications.getAllScheduledNotificationsAsync).mockClear();
  await syncTodoReminders([todo], { remotePush: false, session: mockSession - 1 });
  expect(Notifications.getAllScheduledNotificationsAsync).not.toHaveBeenCalled();
  expect(Notifications.scheduleNotificationAsync).not.toHaveBeenCalled();
});

it("does not prompt or schedule when notification permission is denied", async () => {
  jest.mocked(Notifications.getPermissionsAsync).mockResolvedValue({ status: "denied" } as never);
  await syncTodoReminders([todo], { remotePush: false });
  expect(ensureNotificationPermission).not.toHaveBeenCalled();
  expect(Notifications.scheduleNotificationAsync).not.toHaveBeenCalled();
});

it("does not repeat an unchanged reminder after another list refresh", async () => {
  await syncTodoReminders([todo], { remotePush: false });
  scheduled.clear(); // The existing alert was already delivered.
  await syncTodoReminders([todo], { remotePush: false });
  expect(Notifications.scheduleNotificationAsync).toHaveBeenCalledTimes(1);
});

it("allows a later job to retry after native scheduling fails", async () => {
  jest.mocked(Notifications.scheduleNotificationAsync).mockRejectedValueOnce(new Error("native unavailable"));
  await expect(syncTodoReminders([todo], { remotePush: false })).rejects.toThrow("native unavailable");
  await syncTodoReminders([todo], { remotePush: false });
  expect(scheduled.has(todoNotificationId(todo.id))).toBe(true);
});

it("asks the OS for its pending alerts once per sync, not once per to-do", async () => {
  const many = Array.from({ length: 50 }, (_, i) => {
    const due = new Date(Date.UTC(2099, 0, 1) + i * 3_600_000).toISOString();
    return { ...todo, id: `t${i}`, due_at: due, notify_at: due };
  });
  jest.mocked(Notifications.getAllScheduledNotificationsAsync).mockClear();
  await syncTodoReminders(many, { remotePush: false });
  // A first sync of 50 to-dos listed them 51 times.
  expect(Notifications.getAllScheduledNotificationsAsync).toHaveBeenCalledTimes(1);
  expect(scheduled.size).toBe(50);
});

it("replaces a moved to-do's alert from that one listing", async () => {
  const other = { ...todo, id: "t2", due_at: "2099-01-03T12:00:00Z", notify_at: "2099-01-03T11:50:00Z" };
  await syncTodoReminders([todo, other], { remotePush: false });
  const moved = { ...todo, due_at: "2099-01-05T12:00:00Z", notify_at: "2099-01-05T11:50:00Z" };
  await syncTodoReminders([moved, other], { remotePush: false });
  expect(Notifications.cancelScheduledNotificationAsync).toHaveBeenCalledWith(todoNotificationId(todo.id));
  expect(scheduled.get(todoNotificationId(todo.id))).toMatchObject({ date: new Date("2099-01-05T11:50:00Z") });
  expect(scheduled.has(todoNotificationId(other.id))).toBe(true);
  expect(Notifications.scheduleNotificationAsync).toHaveBeenCalledTimes(3);
});

describe("the alert goes at the server's notify_at, as it is", () => {
  it("schedules at notify_at, not the due time minus a lead it worked out", async () => {
    // Quiet hours 22:00-07:00: due 23:30, the server says 07:00 the next morning.
    const night = { ...todo, due_at: "2099-01-01T23:30:00Z", notify_at: "2099-01-02T07:00:00Z" };
    await syncTodoReminders([night], { remotePush: false });
    expect(scheduled.get(todoNotificationId(night.id))).toEqual({ type: "date", date: new Date("2099-01-02T07:00:00Z") });
  });

  it.each([
    ["null", null],
    ["already past", "2020-01-01T00:00:00Z"],
  ])("schedules nothing, and drops an alert it had, when notify_at is %s", async (_label, notifyAt) => {
    await syncTodoReminders([todo], { remotePush: false });
    expect(scheduled.has(todoNotificationId(todo.id))).toBe(true);
    jest.mocked(Notifications.scheduleNotificationAsync).mockClear();
    await syncTodoReminders([{ ...todo, notify_at: notifyAt }], { remotePush: false });
    expect(Notifications.scheduleNotificationAsync).not.toHaveBeenCalled();
    expect(scheduled.size).toBe(0);
  });

  it("moves the alert when only notify_at moved (the lead or quiet hours changed)", async () => {
    await syncTodoReminders([todo], { remotePush: false });
    await syncTodoReminders([{ ...todo, notify_at: "2099-01-01T11:30:00Z" }], { remotePush: false });
    expect(scheduled.get(todoNotificationId(todo.id))).toMatchObject({ date: new Date("2099-01-01T11:30:00Z") });
    expect(Notifications.scheduleNotificationAsync).toHaveBeenCalledTimes(2);
  });

  it("still leaves every alert to push when the server holds this device's token", async () => {
    await syncTodoReminders([todo], { remotePush: true });
    expect(Notifications.scheduleNotificationAsync).not.toHaveBeenCalled();
  });
});

describe("the iOS pending-alert limit", () => {
  // Reminder i is due i hours into 2099, listed latest first.
  const many = Array.from({ length: MAX_SCHEDULED_REMINDERS + 10 }, (_, i) => ({
    ...todo,
    id: `t${i}`,
    notify_at: new Date(Date.UTC(2099, 0, 1, i)).toISOString(),
  })).reverse();

  it("schedules only the soonest alerts", async () => {
    await syncTodoReminders(many, { remotePush: false });
    expect(scheduled.size).toBe(MAX_SCHEDULED_REMINDERS);
    expect(scheduled.has(todoNotificationId("t0"))).toBe(true);
    expect(scheduled.has(todoNotificationId(`t${MAX_SCHEDULED_REMINDERS - 1}`))).toBe(true);
    expect(scheduled.has(todoNotificationId(`t${MAX_SCHEDULED_REMINDERS}`))).toBe(false);
  });

  it("gives a fired alert's slot to the next reminder on the next sync", async () => {
    await syncTodoReminders(many, { remotePush: false });
    // t0 fired (the OS drops it), and the list read on coming back says it is past.
    scheduled.delete(todoNotificationId("t0"));
    const later = many.map((item) => (item.id === "t0" ? { ...item, notify_at: "2020-01-01T00:00:00Z" } : item));
    await syncTodoReminders(later, { remotePush: false });
    expect(scheduled.size).toBe(MAX_SCHEDULED_REMINDERS);
    expect(scheduled.has(todoNotificationId(`t${MAX_SCHEDULED_REMINDERS}`))).toBe(true);
  });
});
