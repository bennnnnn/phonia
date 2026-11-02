const mockVibrate = jest.fn();
const mockImpactAsync = jest.fn().mockResolvedValue(undefined);
const mockSelectionAsync = jest.fn().mockResolvedValue(undefined);
const mockNotificationAsync = jest.fn().mockResolvedValue(undefined);
const mockPerformAndroidHapticsAsync = jest.fn().mockResolvedValue(undefined);

jest.mock("react-native", () => ({
  Platform: { OS: "ios", Version: 34 },
  Vibration: { vibrate: mockVibrate },
}));

jest.mock("expo-haptics", () => ({
  ImpactFeedbackStyle: { Light: "light", Medium: "medium" },
  NotificationFeedbackType: { Success: "success", Warning: "warning", Error: "error" },
  AndroidHaptics: {
    Confirm: "confirm",
    Reject: "reject",
    Clock_Tick: "clock-tick",
    Long_Press: "long-press",
    Virtual_Key: "virtual-key",
    Segment_Tick: "segment-tick",
  },
  impactAsync: mockImpactAsync,
  selectionAsync: mockSelectionAsync,
  notificationAsync: mockNotificationAsync,
  performAndroidHapticsAsync: mockPerformAndroidHapticsAsync,
}));

import { Platform } from "react-native";

import {
  impactMedium,
  notifyDestructive,
  notifyError,
  notifySuccess,
  notifyWarning,
  hapticsEnabled,
  selection,
  setHapticsEnabledSnapshot,
  subscribeHaptics,
  tap,
} from "@/lib/haptics";

const flush = async () => {
  await Promise.resolve();
  await Promise.resolve();
};

function onDevice(os: "ios" | "android", version = 34) {
  Object.assign(Platform, { OS: os, Version: version });
}

describe("haptics", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockImpactAsync.mockResolvedValue(undefined);
    mockSelectionAsync.mockResolvedValue(undefined);
    mockNotificationAsync.mockResolvedValue(undefined);
    mockPerformAndroidHapticsAsync.mockResolvedValue(undefined);
    setHapticsEnabledSnapshot(true);
    onDevice("ios");
  });

  it.each([
    ["tap", tap, mockImpactAsync, "light"],
    ["selection", selection, mockSelectionAsync, undefined],
    ["impactMedium", impactMedium, mockImpactAsync, "medium"],
    ["notifySuccess", notifySuccess, mockNotificationAsync, "success"],
    ["notifyWarning", notifyWarning, mockNotificationAsync, "warning"],
    ["notifyError", notifyError, mockNotificationAsync, "error"],
  ] as const)("%s plays the iOS feedback generator", async (_name, play, native, arg) => {
    play();
    await flush();
    expect(native).toHaveBeenCalledTimes(1);
    if (arg) expect(native).toHaveBeenCalledWith(arg);
    expect(mockPerformAndroidHapticsAsync).not.toHaveBeenCalled();
  });

  // expo-haptics' impact, selection and notification calls drive Android's vibration
  // motor with fixed 40-50 ms waveforms; the system constants are the phone's own
  // short ticks and clicks, and follow its touch-feedback setting.
  it.each([
    ["tap", tap, 34, "virtual-key"],
    ["selection", selection, 34, "segment-tick"],
    ["selection before Android 14", selection, 33, "clock-tick"],
    ["impactMedium", impactMedium, 34, "long-press"],
    ["notifySuccess", notifySuccess, 30, "confirm"],
    ["notifySuccess before Android 11", notifySuccess, 29, "virtual-key"],
    ["notifyWarning", notifyWarning, 30, "reject"],
    ["notifyWarning before Android 11", notifyWarning, 29, "long-press"],
    ["notifyError", notifyError, 30, "reject"],
    ["notifyError before Android 11", notifyError, 29, "long-press"],
  ] as const)("%s plays the Android system haptic", async (_name, play, api, constant) => {
    onDevice("android", api);
    play();
    await flush();
    expect(mockPerformAndroidHapticsAsync).toHaveBeenCalledTimes(1);
    expect(mockPerformAndroidHapticsAsync).toHaveBeenCalledWith(constant);
    expect(mockImpactAsync).not.toHaveBeenCalled();
    expect(mockSelectionAsync).not.toHaveBeenCalled();
    expect(mockNotificationAsync).not.toHaveBeenCalled();
    expect(mockVibrate).not.toHaveBeenCalled();
  });

  it("stays silent when Android refuses a haptic, and the next one still asks the system", async () => {
    onDevice("android");
    mockPerformAndroidHapticsAsync.mockRejectedValueOnce(new Error("unsupported"));
    tap();
    await flush();
    tap();
    await flush();
    expect(mockPerformAndroidHapticsAsync).toHaveBeenCalledTimes(2);
    expect(mockVibrate).not.toHaveBeenCalled();
  });

  it("never throws when the native call throws", () => {
    mockImpactAsync.mockImplementationOnce(() => {
      throw new Error("no native module");
    });
    expect(() => tap()).not.toThrow();
  });

  it("emits one warning notification for a confirmed destructive action", async () => {
    notifyDestructive();
    await flush();
    expect(mockNotificationAsync).toHaveBeenCalledTimes(1);
    expect(mockNotificationAsync).toHaveBeenCalledWith("warning");
  });

  it.each(["ios", "android"] as const)("stays silent on %s while Settings → Haptics is off", async (os) => {
    onDevice(os);
    const listener = jest.fn();
    const unsubscribe = subscribeHaptics(listener);
    setHapticsEnabledSnapshot(false);
    expect(hapticsEnabled()).toBe(false);
    expect(listener).toHaveBeenCalledTimes(1);
    tap();
    selection();
    impactMedium();
    notifySuccess();
    notifyDestructive();
    await flush();
    expect(mockImpactAsync).not.toHaveBeenCalled();
    expect(mockSelectionAsync).not.toHaveBeenCalled();
    expect(mockNotificationAsync).not.toHaveBeenCalled();
    expect(mockPerformAndroidHapticsAsync).not.toHaveBeenCalled();
    expect(mockVibrate).not.toHaveBeenCalled();

    setHapticsEnabledSnapshot(true);
    tap();
    await flush();
    expect(os === "ios" ? mockImpactAsync : mockPerformAndroidHapticsAsync).toHaveBeenCalledTimes(1);
    unsubscribe();
  });
});
