/**
 * Theme-aware elevation. Prefer these over ad-hoc `#000` + fixed opacity
 * (which reads muddy on dark surfaces).
 *
 * Uses classic shadow* props only — no import of `withAlpha` from theme
 * (that created a Metro init cycle where ActionBanner crashed with
 * "Property 'withAlpha' doesn't exist").
 */
import type { ViewStyle } from "react-native";

import type { Theme } from "@/lib/theme";

/** Neutral shadow ink. Callers outside this file use the helpers or this constant. */
const SHADOW_COLOR = "#000";

/** Soft raised surface — quota nudge, light cards. */
export function shadowRaised(theme: Theme): ViewStyle {
  return {
    shadowColor: SHADOW_COLOR,
    shadowOpacity: theme.isDark ? 0.4 : 0.08,
    shadowRadius: theme.isDark ? 8 : 6,
    shadowOffset: { width: 0, height: 2 },
    elevation: 2,
  };
}

/** Floating menu / popover panel. */
export function shadowOverlay(theme: Theme): ViewStyle {
  return {
    shadowColor: SHADOW_COLOR,
    shadowOpacity: theme.isDark ? 0.55 : 0.28,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 10 },
    elevation: 20,
  };
}

type ElevatedLevel = "fab" | "toast" | "banner";

/** Stronger float — FAB, toast banner, inline error. */
export function shadowElevated(theme: Theme, level: ElevatedLevel): ViewStyle {
  if (level === "fab") {
    return {
      shadowColor: SHADOW_COLOR,
      shadowOpacity: theme.isDark ? 0.35 : 0.18,
      shadowRadius: 10,
      shadowOffset: { width: 0, height: 2 },
      elevation: 8,
    };
  }
  if (level === "banner") {
    return {
      shadowColor: SHADOW_COLOR,
      shadowOpacity: theme.isDark ? 0.28 : 0.12,
      shadowRadius: 16,
      shadowOffset: { width: 0, height: 4 },
      elevation: 8,
    };
  }
  return {
    shadowColor: SHADOW_COLOR,
    shadowOpacity: theme.isDark ? 0.55 : 0.45,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 8 },
    elevation: 16,
  };
}

/** Branded colored glow — the one logo/card glow tinted with a theme color
 *  (e.g. `theme.primary`). A named decision instead of an inline
 *  `Platform.select` exception; matches the neutral helpers above. */
export function shadowGlow(theme: Theme, color: string): ViewStyle {
  return {
    shadowColor: color,
    shadowOpacity: theme.isDark ? 0.35 : 0.28,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 10 },
    elevation: 8,
  };
}
