import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

import { devicePushTokenFingerprint, fingerprint } from "@/features/notifications/model/devicePushToken";
import { isExpoGo } from "@/lib/expoRuntime";

jest.mock("expo-notifications", () => ({ getDevicePushTokenAsync: jest.fn() }));
jest.mock("react-native", () => ({ Platform: { OS: "ios" } }));
jest.mock("@/lib/expoRuntime", () => ({ isExpoGo: jest.fn(() => false) }));

const readToken = Notifications.getDevicePushTokenAsync as jest.Mock;

beforeEach(() => {
  jest.clearAllMocks();
  Platform.OS = "ios";
  (isExpoGo as jest.Mock).mockReturnValue(false);
});

describe("device push token fingerprint", () => {
  it("tells tokens apart without keeping them", async () => {
    expect(fingerprint("apns-token-1")).toBe(fingerprint("apns-token-1"));
    expect(fingerprint("apns-token-1")).not.toBe(fingerprint("apns-token-2"));
    expect(fingerprint("apns-token-1")).toMatch(/^[0-9a-f]{8}$/);

    readToken.mockResolvedValue({ type: "ios", data: "apns-token-1" });
    await expect(devicePushTokenFingerprint()).resolves.toBe(fingerprint("apns-token-1"));
  });

  it("answers null where there is no token to read", async () => {
    readToken.mockRejectedValue(new Error("no APNs on a simulator"));
    await expect(devicePushTokenFingerprint()).resolves.toBeNull();

    (isExpoGo as jest.Mock).mockReturnValue(true);
    await expect(devicePushTokenFingerprint()).resolves.toBeNull();
    (isExpoGo as jest.Mock).mockReturnValue(false);

    Platform.OS = "web";
    await expect(devicePushTokenFingerprint()).resolves.toBeNull();
    expect(readToken).toHaveBeenCalledTimes(1);
  });

  it("does not hold a sync on a slow read", async () => {
    jest.useFakeTimers();
    try {
      readToken.mockReturnValue(new Promise(() => {}));
      const read = devicePushTokenFingerprint();
      jest.advanceTimersByTime(3_000);
      await expect(read).resolves.toBeNull();
    } finally {
      jest.useRealTimers();
    }
  });
});
