import { useCallback, useEffect, useState, useSyncExternalStore, type ReactNode } from "react";

import {
  type AppearancePreference,
} from "@/lib/appearance";
import {
  getAppearancePreferenceSnapshot,
  setAppearancePreferenceSnapshot,
  subscribeAppearancePreference,
} from "@/lib/appearanceRuntime";
import {
  getAppearancePreference,
  setAppearancePreference as persistAppearancePreference,
} from "@/lib/appearancePrefs";
import type { AccentPreference } from "@/lib/accent";
import {
  getAccentPreference,
  setAccentPreference as persistAccentPreference,
} from "@/lib/accentPrefs";
import { setAccentSnapshot, useAccentPreference } from "@/lib/accentRuntime";
import { useResolvedColorScheme } from "@/lib/colorScheme";
import { hapticsEnabled, selection, setHapticsEnabledSnapshot, subscribeHaptics } from "@/lib/haptics";
import { getHapticsPreference, setHapticsPreference } from "@/lib/hapticsPrefs";

export function AppearanceProvider({ children }: { children: ReactNode }) {
  useEffect(() => {
    void getAppearancePreference().then(setAppearancePreferenceSnapshot);
    void getAccentPreference().then(setAccentSnapshot);
    void getHapticsPreference().then(setHapticsEnabledSnapshot);
  }, []);

  return children;
}

export function useAppearance() {
  const colorScheme = useResolvedColorScheme();
  const [preference, setPreferenceState] = useState(getAppearancePreferenceSnapshot);

  useEffect(() => {
    return subscribeAppearancePreference(() => {
      setPreferenceState(getAppearancePreferenceSnapshot());
    });
  }, []);

  const setPreference = useCallback(async (next: AppearancePreference) => {
    setAppearancePreferenceSnapshot(next);
    setPreferenceState(next);
    await persistAppearancePreference(next);
  }, []);

  return { preference, setPreference, colorScheme };
}

/** The accent color and a setter that applies it now and saves it. */
export function useAccent() {
  const accent = useAccentPreference();
  const setAccent = useCallback(async (next: AccentPreference) => {
    setAccentSnapshot(next);
    await persistAccentPreference(next);
  }, []);
  return { accent, setAccent };
}

/** Settings → Haptics: whether taps and toggles buzz, saved on this device. */
export function useHaptics() {
  const enabled = useSyncExternalStore(subscribeHaptics, hapticsEnabled, hapticsEnabled);
  const setEnabled = useCallback(async (next: boolean) => {
    setHapticsEnabledSnapshot(next);
    // The switch's own tick played while haptics were still off: turning them on is felt.
    if (next) selection();
    await setHapticsPreference(next);
  }, []);
  return { enabled, setEnabled };
}
