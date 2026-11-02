import {
  allowReminderAlerts,
  resetAlertsOffNotice,
  shouldTellAlertsOff,
} from "@/features/todos/model/reminderAlerts";
import { ensureNotificationPermission } from "@/features/notifications/model/pushNotifications";

jest.mock("@/features/notifications/model/pushNotifications", () => ({ ensureNotificationPermission: jest.fn() }));

beforeEach(() => {
  jest.clearAllMocks();
  resetAlertsOffNotice();
});

it.each([
  [true, "on"],
  [false, "off"],
])("permission %s means alerts are %s", async (granted, alerts) => {
  jest.mocked(ensureNotificationPermission).mockResolvedValue(granted);
  await expect(allowReminderAlerts()).resolves.toBe(alerts);
});

it("a failed ask counts as off, never as an error", async () => {
  jest.mocked(ensureNotificationPermission).mockRejectedValue(new Error("native"));
  await expect(allowReminderAlerts()).resolves.toBe("off");
});

it("tells the user once per launch", () => {
  expect(shouldTellAlertsOff()).toBe(true);
  expect(shouldTellAlertsOff()).toBe(false);
  resetAlertsOffNotice();
  expect(shouldTellAlertsOff()).toBe(true);
});
