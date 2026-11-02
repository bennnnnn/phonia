import { Platform } from "react-native";
import * as Haptics from "expo-haptics";

import { createListenerSet } from "@/lib/listenerSet";

/** Settings → Haptics. Loaded from the device at start (lib/hapticsPrefs). */
let enabled = true;
const listeners = createListenerSet();

export function hapticsEnabled(): boolean {
  return enabled;
}

export function setHapticsEnabledSnapshot(next: boolean): void {
  if (next === enabled) return;
  enabled = next;
  listeners.emit();
}

export function subscribeHaptics(listener: () => void): () => void {
  return listeners.subscribe(listener);
}

/**
 * One feel on both platforms. iOS plays its feedback generator. Android plays the
 * system haptic constant closest to it (`performAndroidHapticsAsync`): expo-haptics'
 * impact, selection and notification calls run Android's vibration motor with fixed
 * 40–50 ms waveforms instead, a buzz where iOS gives a tick. A constant also follows
 * the phone's own touch-feedback setting. `api` is the Android API level: CONFIRM and
 * REJECT need 30, SEGMENT_TICK 34; an older phone gets the nearest older constant.
 */
type Feel = {
  ios: () => Promise<void>;
  android: (api: number) => Haptics.AndroidHaptics;
};

function play(feel: Feel): void {
  if (!enabled) return;
  try {
    const pending = Platform.OS === "android"
      ? Haptics.performAndroidHapticsAsync(feel.android(Number(Platform.Version)))
      : feel.ios();
    // A phone without the effect stays silent; feedback never fails an action.
    void Promise.resolve(pending).catch(() => {});
  } catch {
    /* ignore */
  }
}

/** Light tactile feedback for an important press. Never throws. */
export function tap(): void {
  play({
    ios: () => Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light),
    android: () => Haptics.AndroidHaptics.Virtual_Key,
  });
}

/** Picker / toggle feedback. */
export function selection(): void {
  play({
    ios: () => Haptics.selectionAsync(),
    android: (api) => (api >= 34 ? Haptics.AndroidHaptics.Segment_Tick : Haptics.AndroidHaptics.Clock_Tick),
  });
}

/** Camera shutter / other medium impacts. */
export function impactMedium(): void {
  play({
    ios: () => Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium),
    android: () => Haptics.AndroidHaptics.Long_Press,
  });
}

/** One confirmation. Copy, a saved change, or a completed task. */
export function notifySuccess(): void {
  play({
    ios: () => Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success),
    android: (api) => (api >= 30 ? Haptics.AndroidHaptics.Confirm : Haptics.AndroidHaptics.Virtual_Key),
  });
}

/** Validation, a blocked action (offline), or a confirmed destructive action. */
export function notifyWarning(): void {
  play({
    ios: () => Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning),
    android: (api) => (api >= 30 ? Haptics.AndroidHaptics.Reject : Haptics.AndroidHaptics.Long_Press),
  });
}

/** Something failed: a reply, a save, a delete. Not what a confirmed delete feels like. */
export function notifyError(): void {
  play({
    ios: () => Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error),
    android: (api) => (api >= 30 ? Haptics.AndroidHaptics.Reject : Haptics.AndroidHaptics.Long_Press),
  });
}

/**
 * Feedback for a confirmed destructive action. Call once, after the
 * destructive operation succeeds — never when opening or cancelling an alert.
 */
export function notifyDestructive(): void {
  notifyWarning();
}
