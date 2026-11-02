import { useEffect, useState } from "react";
import { useColorScheme as useSystemColorScheme } from "react-native";

import { resolveColorScheme } from "@/lib/appearance";
import {
  getAppearancePreferenceSnapshot,
  subscribeAppearancePreference,
} from "@/lib/appearanceRuntime";

/** Resolved light/dark scheme (manual preference + system). */
export function useResolvedColorScheme(): "light" | "dark" {
  const systemScheme = useSystemColorScheme();
  const [preference, setPreference] = useState(getAppearancePreferenceSnapshot);

  useEffect(() => {
    return subscribeAppearancePreference(() => {
      setPreference(getAppearancePreferenceSnapshot());
    });
  }, []);

  return resolveColorScheme(systemScheme, preference);
}
