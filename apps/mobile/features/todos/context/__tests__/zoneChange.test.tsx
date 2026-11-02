/**
 * @jest-environment ./jest.timeZoneEnvironment.js
 */
/**
 * The phone's zone reaches the server the moment it changes, and every reminder follows
 * it: the zone report (useBootstrapSync), the to-do list's read again (TodosContext) and
 * the phone's own alert at the to-do's new notify_at (todoReminders), with the requests
 * each move costs. Quiet hours 22:00-07:00, a to-do due at 18:00 UTC with a 10-minute
 * lead: 17:50 UTC is 23:35 in Kathmandu, inside quiet hours, so there it waits until
 * 07:00 (01:15 UTC); in UTC and Kiritimati (07:50 the next day) it is not.
 */
import { useState, type ReactNode } from "react";
import { AppState, type AppStateStatus } from "react-native";
import { act, render } from "@testing-library/react-native";

import { TodosProvider } from "@/features/todos/context/TodosContext";
import { useBootstrapSync } from "@/hooks/useBootstrapSync";
import { api, type Todo, type User } from "@/lib/api";

declare const setTestTimeZone: (zone: string) => void;

type MockAuth = { token: string; user: User | null };
jest.mock("@/contexts/AuthContext", () => {
  const { createContext: create, useContext } = jest.requireActual<typeof import("react")>("react");
  const context = create<MockAuth | null>(null);
  return { MockAuthContext: context, useAuthOptional: () => useContext(context) };
});
jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => 1, requireTokenSession: jest.fn() }));
jest.mock("@/lib/api", () => ({ api: { updateMe: jest.fn(), listTodos: jest.fn(), syncSubscription: jest.fn() } }));
jest.mock("@/features/billing/model/purchases", () => ({ isPurchasesConfigured: () => false, configurePurchases: jest.fn(),
  registerPlanChangeListener: jest.fn() }));
jest.mock("@/features/notifications/model/pushNotifications", () => ({ attachPushForegroundSync: jest.fn(),
  ensureReminderChannel: jest.fn(async () => undefined), ensureNotificationPermission: jest.fn(async () => true) }));
jest.mock("@/lib/deviceLocation", () => ({ getDeviceLocationLabel: jest.fn(async () => null) }));
jest.mock("@/lib/syncRecords", () => ({ recentSyncAt: jest.fn(async () => null), recordSync: jest.fn() }));
jest.mock("@/lib/filePrefs", () => ({}));
jest.mock("@/features/todos/model/reminderSeen", () => ({
  ...jest.requireActual("@/features/todos/model/reminderSeen"),
  loadSeenReminderIds: jest.fn(async () => new Set()),
  saveSeenReminderIds: jest.fn(async () => undefined),
}));
jest.mock("@/features/todos/model/homeReminderNudges", () => ({
  ...jest.requireActual("@/features/todos/model/homeReminderNudges"),
  loadHomeNudgeState: jest.fn(async () => ({ dismissed: new Set() })),
  saveHomeNudgeState: jest.fn(async () => undefined),
}));
// The OS's clock-change event (expo-localization's onCalendarSettingsChanged).
const mockClockListeners = new Set<() => void>();
jest.mock("@/lib/datetime/phoneClock", () => ({
  ...jest.requireActual("@/lib/datetime/phoneClock"),
  onPhoneClockChange: (listener: () => void) => {
    mockClockListeners.add(listener);
    return () => { mockClockListeners.delete(listener); };
  },
}));
const mockAlerts = new Map<string, Date>();
jest.mock("expo-notifications", () => ({
  getPermissionsAsync: jest.fn(async () => ({ status: "granted" })),
  getAllScheduledNotificationsAsync: jest.fn(async () => [...mockAlerts.keys()].map((identifier) => ({ identifier }))),
  cancelScheduledNotificationAsync: jest.fn(async (id: string) => { mockAlerts.delete(id); }),
  scheduleNotificationAsync: jest.fn(async (item: { identifier: string; trigger: { date: Date } }) => {
    mockAlerts.set(item.identifier, item.trigger.date);
    return item.identifier;
  }),
  SchedulableTriggerInputTypes: { DATE: "date" },
}));

const { MockAuthContext } = jest.requireMock<{ MockAuthContext: React.Context<MockAuth | null> }>(
  "@/contexts/AuthContext");

const NOW = new Date("2026-10-25T12:00:00Z");
/** What the server answers for notify_at in each zone its profile holds (see above). Node's
 * ICU names Kathmandu by its older spelling, Asia/Katmandu; the server knows both. */
const NOTIFY_AT: Record<string, string> = {
  UTC: "2026-10-25T17:50:00.000Z",
  "Asia/Kathmandu": "2026-10-26T01:15:00.000Z",
  "Asia/Katmandu": "2026-10-26T01:15:00.000Z",
  "Pacific/Kiritimati": "2026-10-25T17:50:00.000Z",
};
/** The zone the phone names now. */
const deviceZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone;
let serverZone = "UTC";
const todo = (): Todo => ({
  id: "t1", content: "Call Sam", topic: "Reminders", checked: false, due_at: "2026-10-25T18:00:00.000Z",
  recurrence_rule: null, sort_order: null, chat_id: null, created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T00:00:00Z", notify_at: NOTIFY_AT[serverZone],
});
const USER = {
  id: "u1", timezone: "UTC", location_enabled: false, push_notifications_enabled: false,
  push_reminders_enabled: true, reminder_lead_minutes: 10, quiet_hours_enabled: true,
  quiet_hours_start_minute: 1320, quiet_hours_end_minute: 420,
} as User;

function App({ children }: { children?: ReactNode }) {
  const [user, setUser] = useState<User | null>(USER);
  // AuthProvider sits above TodosProvider, as in app/_layout.tsx.
  useBootstrapSync({ token: "a", user, setUser });
  return (
    <MockAuthContext.Provider value={{ token: "a", user }}>
      <TodosProvider>{children}</TodosProvider>
    </MockAuthContext.Provider>
  );
}

let appStateListener: ((state: AppStateStatus) => void) | null = null;
const settle = (ms = 0) => act(async () => { await jest.advanceTimersByTimeAsync(ms); });
const clockChanged = () => act(async () => { for (const listener of [...mockClockListeners]) listener(); });
async function appState(state: AppStateStatus): Promise<void> {
  await act(async () => { appStateListener?.(state); });
}
const alertAt = () => mockAlerts.get("todo-due-t1")?.toISOString();
const reads = () => jest.mocked(api.listTodos).mock.calls.length;
const zonePatches = () => jest.mocked(api.updateMe).mock.calls.map(([, body]) => body.timezone);

beforeEach(() => {
  jest.clearAllMocks();
  jest.useFakeTimers({ now: NOW });
  setTestTimeZone("UTC");
  serverZone = "UTC";
  mockAlerts.clear();
  jest.spyOn(AppState, "addEventListener").mockImplementation((_type, listener) => {
    appStateListener = listener as (state: AppStateStatus) => void;
    return { remove: () => { appStateListener = null; } } as ReturnType<typeof AppState.addEventListener>;
  });
  jest.mocked(api.listTodos).mockImplementation(async () => ({ todos: [todo()], olderCompleted: false }));
  jest.mocked(api.updateMe).mockImplementation(async (_token, body) => {
    serverZone = String(body.timezone);
    return { ...USER, timezone: serverZone } as User;
  });
});

afterEach(() => {
  jest.useRealTimers();
  jest.restoreAllMocks();
});

it("a zone change while the app runs: one PATCH, one to-do read, the alert at the new notify_at", async () => {
  await render(<App />);
  await settle(100);
  expect([zonePatches(), reads(), alertAt()]).toEqual([[], 1, "2026-10-25T17:50:00.000Z"]);

  // Over the border into Nepal with the app open: the OS says the zone changed.
  setTestTimeZone("Asia/Kathmandu");
  const kathmandu = deviceZone();
  await clockChanged();
  await settle(100);
  expect([zonePatches(), reads()]).toEqual([[kathmandu], 2]);
  // 23:35 in Kathmandu is inside quiet hours: the alert waits until 07:00 there.
  expect(alertAt()).toBe("2026-10-26T01:15:00.000Z");

  // The OS says it again (midnight, a locale change): nothing to send.
  await clockChanged();
  await settle(100);
  expect([zonePatches(), reads()]).toEqual([[kathmandu], 2]);
});

it("a return to the foreground: nothing when the zone is the server's, one PATCH and one read after a flight", async () => {
  await render(<App />);
  await settle(100);
  expect(reads()).toBe(1);

  await appState("background");
  await settle(5_000);
  await appState("active");
  await settle(100);
  expect([zonePatches(), reads()]).toEqual([[], 1]);

  // A flight: hours in the background, landing in another zone. The return's own read of
  // the list (stale by now) waits for the zone report, so the list is read once, in the new zone.
  await appState("background");
  await settle(3 * 60 * 60_000);
  setTestTimeZone("Asia/Kathmandu");
  const kathmandu = deviceZone();
  await appState("active");
  await settle(100);
  expect([zonePatches(), reads()]).toEqual([[kathmandu], 2]);
  expect(alertAt()).toBe("2026-10-26T01:15:00.000Z");

  await appState("background");
  await settle(2 * 60 * 60_000);
  setTestTimeZone("Pacific/Kiritimati");
  await appState("active");
  await settle(100);
  expect([zonePatches(), reads()]).toEqual([[kathmandu, "Pacific/Kiritimati"], 3]);
  expect(alertAt()).toBe("2026-10-25T17:50:00.000Z");
});
