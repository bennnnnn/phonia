import { Alert } from "react-native";
import { act, render } from "@testing-library/react-native";
import NotificationsSettingsScreen from "@/features/account/screens/NotificationsSettingsScreen";
import { cancelAllTodoReminders, syncTodoReminders } from "@/features/todos/model/todoReminders";
import { ensureNotificationPermission, getNotificationPermissionGranted, registerRemotePushToken, unregisterRemotePushToken } from "@/features/notifications/model/pushNotifications";

type PushRegistration = Awaited<ReturnType<typeof registerRemotePushToken>>;

let mockSession = 0;
let mockFocused = true;
const mockUpdate = jest.fn();
const mockFeedback = { error: jest.fn() };
const mockSwitches: Record<string, { onValueChange: (value: boolean) => Promise<void>; disabled: boolean; value?: boolean }> = {};
const mockLinks: Record<string, { onPress: () => void; value: string }> = {};
let mockPicker: { onSelect: (key: string) => void };
let mockTimePicker: { visible: boolean; onConfirm: (time: { hour: number; minute: number }) => void };
jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => mockSession }));
let mockUser: {
  id: string;
  reminder_lead_minutes: number;
  push_notifications_enabled: boolean;
  quiet_hours_enabled?: boolean;
  quiet_hours_start_minute?: number;
  quiet_hours_end_minute?: number;
  email_reminders_available?: boolean;
} = { id: "user", reminder_lead_minutes: 10, push_notifications_enabled: false };
jest.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ token: "token", user: mockUser, updateUser: mockUpdate }) }));
jest.mock("@/features/todos/context/TodosContext", () => ({ useTodos: () => ({ todos: [{ id: "stale-row" }] }) }));
jest.mock("@/contexts/actionFeedbackCore", () => ({ useActionFeedbackOptional: () => mockFeedback }));
jest.mock("@/lib/theme", () => ({ useTheme: () => ({}) }));
jest.mock("@/features/account/components/settingsUi", () => ({
  SettingsPage: ({ children }: { children: React.ReactNode }) => children,
  SettingsGroup: ({ children }: { children: React.ReactNode }) => children,
  SettingsSwitchRow: (props: { title: string } & (typeof mockSwitches)[string]) => { mockSwitches[props.title] = props; return null; },
  SettingsLinkRow: (props: { title: string } & (typeof mockLinks)[string]) => { mockLinks[props.title] = props; return null; },
  SettingsMenuRow: (props: typeof mockPicker) => { mockPicker = props; return null; },
}));
jest.mock("@/ui/pickers/TimePickerDialog", () => ({
  TimePickerDialog: (props: typeof mockTimePicker) => {
    mockTimePicker = props;
    return null;
  },
}));
jest.mock("@/features/todos/model/todoReminders", () => ({ cancelAllTodoReminders: jest.fn(), syncTodoReminders: jest.fn() }));
jest.mock("@/features/notifications/model/pushNotifications", () => ({
  ensureNotificationPermission: jest.fn(async () => true),
  getNotificationPermissionGranted: jest.fn(async () => true),
  registerRemotePushToken: jest.fn(async () => undefined),
  unregisterRemotePushToken: jest.fn(async () => undefined),
}));
jest.mock("expo-router", () => ({ Redirect: () => null,
  useFocusEffect: (effect: () => void | (() => void)) => {
    const React = jest.requireActual("react");
    const focused = mockFocused;
    React.useEffect(() => focused ? effect() : undefined, [effect, focused]);
  },
}));
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}
beforeEach(() => {
  jest.clearAllMocks(); mockSession++; mockFocused = true; mockUpdate.mockResolvedValue(undefined);
  mockUser = { id: "user", reminder_lead_minutes: 10, push_notifications_enabled: false };
  jest.mocked(getNotificationPermissionGranted).mockResolvedValue(true);
  jest.spyOn(Alert, "alert").mockImplementation(() => {});
});

it("never resyncs a captured todo list after a delayed settings save", async () => {
  const saving = deferred<void>();
  mockUpdate.mockReturnValueOnce(saving.promise);
  await render(<NotificationsSettingsScreen />);
  await act(() => { mockPicker.onSelect("30"); });
  await act(async () => { saving.resolve(); });
  expect(mockUpdate).toHaveBeenCalledWith({ reminder_lead_minutes: 30 });
  expect(syncTodoReminders).not.toHaveBeenCalled();
  expect(cancelAllTodoReminders).not.toHaveBeenCalled();
});

it("offers email reminders only when the server can send email", async () => {
  delete mockSwitches["settings.email_reminders"];
  await render(<NotificationsSettingsScreen />);
  expect(mockSwitches["settings.email_reminders"]).toBeDefined();

  delete mockSwitches["settings.email_reminders"];
  mockUser = { ...mockUser, email_reminders_available: false };
  await render(<NotificationsSettingsScreen />);
  expect(mockSwitches["settings.email_reminders"]).toBeUndefined();
});

it("saves one quiet-hours selection for the current account", async () => {
  mockUser = {
    id: "user",
    reminder_lead_minutes: 10,
    push_notifications_enabled: false,
    quiet_hours_enabled: true,
    quiet_hours_start_minute: 1320,
    quiet_hours_end_minute: 420,
  };
  await render(<NotificationsSettingsScreen />);
  await act(() => mockLinks["settings.quiet_hours_start"].onPress());
  expect(mockTimePicker.visible).toBe(true);

  await act(() => mockTimePicker.onConfirm({ hour: 23, minute: 15 }));

  expect(mockUpdate).toHaveBeenCalledTimes(1);
  expect(mockUpdate).toHaveBeenCalledWith({ quiet_hours_start_minute: 1395 });
});

it("rejects a quiet-hours save after the account changes", async () => {
  mockUser = {
    id: "user",
    reminder_lead_minutes: 10,
    push_notifications_enabled: false,
    quiet_hours_enabled: true,
    quiet_hours_start_minute: 1320,
    quiet_hours_end_minute: 420,
  };
  await render(<NotificationsSettingsScreen />);
  await act(() => mockLinks["settings.quiet_hours_start"].onPress());
  mockSession++;

  await act(() => mockTimePicker.onConfirm({ hour: 23, minute: 15 }));

  expect(mockUpdate).not.toHaveBeenCalled();
});

it("does not register push or change the next account after delayed permission", async () => {
  const permission = deferred<boolean>();
  jest.mocked(ensureNotificationPermission).mockReturnValueOnce(permission.promise);
  await render(<NotificationsSettingsScreen />);
  let pending!: Promise<void>;
  await act(async () => { pending = mockSwitches["settings.push_notifications"].onValueChange(true); });
  mockSession++;
  await act(async () => { permission.resolve(true); await pending; });
  expect(registerRemotePushToken).not.toHaveBeenCalled();
  expect(mockUpdate).not.toHaveBeenCalled();
});

it("rejects settings callbacks retained from a previous focus visit", async () => {
  const ui = await render(<NotificationsSettingsScreen />);
  const toggle = mockSwitches["settings.push_notifications"].onValueChange;
  mockFocused = false; await ui.rerender(<NotificationsSettingsScreen />);
  mockFocused = true; await ui.rerender(<NotificationsSettingsScreen />);
  await act(async () => { await toggle(false); });
  expect(mockUpdate).not.toHaveBeenCalled();
  expect(unregisterRemotePushToken).not.toHaveBeenCalled();
});

it("keeps a pending settings mutation locked when the screen remounts", async () => {
  const saving = deferred<void>();
  mockUpdate.mockReturnValueOnce(saving.promise);
  const first = await render(<NotificationsSettingsScreen />);
  let pending!: Promise<void>;
  await act(async () => { pending = mockSwitches["settings.push_notifications"].onValueChange(false); });
  await first.unmount();
  await render(<NotificationsSettingsScreen />);
  expect(mockSwitches["settings.push_notifications"].disabled).toBe(true);
  await act(async () => { await mockSwitches["settings.push_notifications"].onValueChange(true); });
  expect(mockUpdate).toHaveBeenCalledTimes(1);
  await act(async () => { saving.resolve(); await pending; });
  expect(mockSwitches["settings.push_notifications"].disabled).toBe(false);
});

it.each([false, true])("finishes disabling after unmount only in the same account (account changed: %s)", async (accountChanged) => {
  const saving = deferred<void>();
  mockUpdate.mockReturnValueOnce(saving.promise);
  const ui = await render(<NotificationsSettingsScreen />);
  let pending!: Promise<void>;
  await act(async () => { pending = mockSwitches["settings.push_notifications"].onValueChange(false); });
  await ui.unmount();
  if (accountChanged) mockSession++;
  await act(async () => { saving.resolve(); await pending; });
  expect(mockUpdate).toHaveBeenCalledWith({ push_notifications_enabled: false });
  expect(unregisterRemotePushToken).toHaveBeenCalledTimes(accountChanged ? 0 : 1);
});

it.each([false, true])("finishes enabling after registration while offscreen only in the same account (account changed: %s)", async (accountChanged) => {
  const registration = deferred<PushRegistration>();
  jest.mocked(registerRemotePushToken).mockReturnValueOnce(registration.promise);
  const ui = await render(<NotificationsSettingsScreen />);
  let pending!: Promise<void>;
  await act(async () => { pending = mockSwitches["settings.push_notifications"].onValueChange(true); });
  expect(registerRemotePushToken).toHaveBeenCalledTimes(1);
  await ui.unmount();
  if (accountChanged) mockSession++;
  await act(async () => { registration.resolve("registered"); await pending; });
  expect(mockUpdate).toHaveBeenCalledTimes(accountChanged ? 0 : 1);
  if (!accountChanged) expect(mockUpdate).toHaveBeenCalledWith({ push_notifications_enabled: true });
});

it.each([false, true])("shows a delayed permission denial only in its current view (unmounted: %s)", async (unmounted) => {
  const permission = deferred<boolean>();
  jest.mocked(ensureNotificationPermission).mockReturnValueOnce(permission.promise);
  const ui = await render(<NotificationsSettingsScreen />);
  let pending!: Promise<void>;
  await act(async () => { pending = mockSwitches["settings.push_notifications"].onValueChange(true); });
  if (unmounted) await ui.unmount();
  await act(async () => { permission.resolve(false); await pending; });
  expect(Alert.alert).toHaveBeenCalledTimes(unmounted ? 0 : 1);
  expect(registerRemotePushToken).not.toHaveBeenCalled();
  expect(mockUpdate).not.toHaveBeenCalled();
});

it("shows push off when OS permission is denied even if the server pref is on", async () => {
  mockUser = { id: "user", reminder_lead_minutes: 10, push_notifications_enabled: true };
  jest.mocked(getNotificationPermissionGranted).mockResolvedValue(false);
  await render(<NotificationsSettingsScreen />);
  await act(async () => { await Promise.resolve(); });
  expect(mockSwitches["settings.push_notifications"].value).toBe(false);
});

it("turns the server pref off when enabling push is blocked by the OS", async () => {
  mockUser = { id: "user", reminder_lead_minutes: 10, push_notifications_enabled: true };
  jest.mocked(getNotificationPermissionGranted).mockResolvedValue(false);
  jest.mocked(ensureNotificationPermission).mockResolvedValueOnce(false);
  await render(<NotificationsSettingsScreen />);
  await act(async () => { await Promise.resolve(); });
  await act(async () => { await mockSwitches["settings.push_notifications"].onValueChange(true); });
  expect(Alert.alert).toHaveBeenCalledTimes(1);
  expect(registerRemotePushToken).not.toHaveBeenCalled();
  expect(mockUpdate).toHaveBeenCalledWith({ push_notifications_enabled: false });
});

it("optimistically turns push on while registration is pending", async () => {
  const registration = deferred<PushRegistration>();
  jest.mocked(registerRemotePushToken).mockReturnValueOnce(registration.promise);
  await render(<NotificationsSettingsScreen />);

  let pending!: Promise<void>;
  await act(async () => {
    pending = mockSwitches["settings.push_notifications"].onValueChange(true);
    await Promise.resolve();
  });
  expect(mockSwitches["settings.push_notifications"].value).toBe(true);
  expect(mockSwitches["settings.push_notifications"].disabled).toBe(true);
  expect(mockUpdate).not.toHaveBeenCalled();

  await act(async () => {
    registration.resolve("registered");
    await pending;
  });
  expect(mockUpdate).toHaveBeenCalledWith({ push_notifications_enabled: true });
});

it("rolls an optimistic push enablement back when registration fails", async () => {
  jest.mocked(registerRemotePushToken).mockRejectedValueOnce(new Error("offline"));
  await render(<NotificationsSettingsScreen />);

  await act(async () => {
    await mockSwitches["settings.push_notifications"].onValueChange(true);
  });

  expect(mockSwitches["settings.push_notifications"].value).toBe(false);
  expect(mockUpdate).not.toHaveBeenCalled();
  expect(mockFeedback.error).toHaveBeenCalledWith("settings.push_register_failed");
});

it("rolls an optimistic push disablement back when the preference save fails", async () => {
  mockUser = { id: "user", reminder_lead_minutes: 10, push_notifications_enabled: true };
  mockUpdate.mockRejectedValueOnce(new Error("offline"));
  await render(<NotificationsSettingsScreen />);
  await act(async () => {
    await Promise.resolve();
  });

  await act(async () => {
    await mockSwitches["settings.push_notifications"].onValueChange(false);
  });

  expect(mockSwitches["settings.push_notifications"].value).toBe(true);
  expect(unregisterRemotePushToken).not.toHaveBeenCalled();
  expect(mockFeedback.error).toHaveBeenCalledWith("settings.push_register_failed");
});

it("surfaces an initial OS permission read failure and stays off", async () => {
  jest.mocked(getNotificationPermissionGranted).mockRejectedValueOnce(new Error("native failure"));
  await render(<NotificationsSettingsScreen />);
  await act(async () => {
    await Promise.resolve();
  });

  expect(mockSwitches["settings.push_notifications"].value).toBe(false);
  expect(mockFeedback.error).toHaveBeenCalledWith("settings.push_register_failed");
});

it("shows each push kind under the master switch and saves it alone", async () => {
  mockUser = { id: "user", reminder_lead_minutes: 10, push_notifications_enabled: true };
  await render(<NotificationsSettingsScreen />);
  await act(async () => {
    await Promise.resolve();
  });

  expect(mockSwitches["settings.push_reminders"].value).toBe(true);
  await act(async () => {
    await mockSwitches["settings.push_reminders"].onValueChange(false);
  });
  expect(mockUpdate).toHaveBeenCalledWith({ push_reminders_enabled: false });
});

it("hides the push kinds while push is off", async () => {
  for (const key of Object.keys(mockSwitches)) delete mockSwitches[key];
  await render(<NotificationsSettingsScreen />);
  await act(async () => {
    await Promise.resolve();
  });
  expect(mockSwitches["settings.push_notifications"].value).toBe(false);
  expect(mockSwitches["settings.push_reminders"]).toBeUndefined();
});
