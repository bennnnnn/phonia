import * as Notifications from "expo-notifications";

import { ensureAndroidNotificationChannels, notificationSound } from "@/features/notifications/model/notificationChannels";

let mockExpoGo = false;
jest.mock("@/lib/expoRuntime", () => ({ isExpoGo: () => mockExpoGo }));
jest.mock("expo-notifications", () => ({
  setNotificationChannelAsync: jest.fn(),
  AndroidImportance: { HIGH: 4, DEFAULT: 3 },
}));

describe("notification channels", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockExpoGo = false;
  });

  it("creates only the reminders channel", async () => {
    await ensureAndroidNotificationChannels({ reminders: "Reminders" });
    expect(Notifications.setNotificationChannelAsync).toHaveBeenCalledTimes(1);
    expect(Notifications.setNotificationChannelAsync).toHaveBeenCalledWith(
      "recall-reminders-v2",
      expect.objectContaining({ name: "Reminders", importance: 4, sound: "recall_notify.wav" }),
    );
  });

  it.each([
    [false, "recall_notify.wav"],
    [true, "default"],
  ])("Expo Go %s plays %s, since Expo Go has none of the app's sounds", async (expoGo, sound) => {
    mockExpoGo = expoGo;
    expect(notificationSound()).toBe(sound);
    await ensureAndroidNotificationChannels({ reminders: "Reminders" });
    expect(Notifications.setNotificationChannelAsync).toHaveBeenCalledWith(
      "recall-reminders-v2",
      expect.objectContaining({ sound }),
    );
  });
});
