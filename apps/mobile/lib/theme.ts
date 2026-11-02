/**
 * App theme — one palette via `useTheme()`. Neutral surfaces + one accent
 * (indigo by default, or the user's pick in `lib/accent.ts`) for primary
 * actions, selection, progress, links, and focus.
 * Success / goal-met stays green so “done” is not the same hue as brand.
 * Do not hardcode hex in components — add a token here instead.
 *
 * Canonical names used across the app:
 *  `bg` (background), `surface`, `text` (textPrimary), `textSecondary`,
 *  `border`, `primary` / `accent` (same indigo).
 */
import { ACCENTS, DEFAULT_ACCENT, type AccentPreference } from "@/lib/accent";
import { useAccentPreference } from "@/lib/accentRuntime";
import { useResolvedColorScheme } from "@/lib/colorScheme";

export type Theme = {
  scheme: "light" | "dark";
  isDark: boolean;

  // Brand — actions, links, selection, progress, focus
  primary: string;
  primaryLight: string;
  primaryDark: string;

  // Same indigo as primary — reserved name for AI-in-progress moments
  accent: string;
  accentLight: string;
  accentDark: string;

  // Surfaces — `bg` is the page; `surface` / `inputBg` are raised planes.
  // Ladder: bg → surface (cards, fields) → surfaceAlt (pressed / selected
  // wells) → elevated (anything floating: menus, dialogs, sheets).
  // `inputBg`, `contentSurface` and `codeBg` are role names for `surface`.
  bg: string;
  surface: string;
  /** Segmented cards on the Settings overview. */
  settingsSurface: string;
  surfaceAlt: string;
  /** Floating panels — menus, dialogs, sheets, pickers. Lifts off `bg` in dark mode. */
  elevated: string;
  /** Round chrome plates — header buttons, icon wells, picker dial face. */
  control: string;
  border: string;
  /**
   * Hairlines between rows inside one card or menu. Drawn one device pixel
   * wide, so it needs at least 1.25:1 on bg, surface and elevated to show at
   * all; kept quieter than `border`.
   */
  separator: string;
  /** Press feedback wash laid over any surface. */
  pressed: string;

  // Text
  text: string;
  textSecondary: string;
  /** Readable meta/captions — must pass WCAG AA (4.5:1) on `bg` and `surfaceAlt`. */
  textTertiary: string;
  /** Placeholders and non-readable decoration only — not helper or metadata copy. */
  textDisabled: string;

  // Bubbles — user chip is a quiet brand tint, not success-green.
  // Indigo = Recall / interactive; green is reserved for success.
  userBubble: string;
  userText: string;
  assistantBubble: string;
  assistantText: string;

  // Composer
  /** The chat composer's pill: pure white on the light page, the control grey in dark. */
  composerBg: string;
  composerBorder: string;
  inputBg: string;

  // Copyable / content panels
  contentSurface: string;

  // Status
  danger: string;
  /** Readable ink on `danger` fills — destructive badges must pass WCAG AA. */
  onDanger: string;
  dangerLight: string;
  warning: string;
  /** Ink on `warning` — banner labels must pass WCAG AA. */
  onWarning: string;
  /** Goal met / daily complete — one green for bars, labels, and dots. */
  success: string;
  successLight: string;
  onPrimary: string;
  /** Up to four function-graph series (ChatGPT-style overlay). */
  graphSeries: [string, string, string, string];

  // Code blocks
  codeBg: string;
  codeText: string;
  codeLang: string;
  /**
   * The pill behind inline code in prose. A tint of the ink rather than a
   * surface, so it reads on the page, a sent bubble, a callout or a card alike.
   */
  codeInlineBg: string;

  // Overlays
  /** Dims the page under dialogs and sheets. */
  scrim: string;
  /** Light dim under popover menus so a white card stays readable. */
  wash: string;

  // Media surfaces (camera scanner, attachment viewer) — scheme-invariant.
  // Camera chrome must not invert: white ink reads on a live camera feed in
  // both light and dark, and the crop mask is always a dark overlay.
  onMedia: string;
  mediaScrim: string;

  // Brand identity colors (constant across schemes — logos never invert)
  brand: {
    twitter: string;
    linkedin: string;
    /** Google "G" blue — vendor-mandated, same in light & dark. */
    google: string;
    /** The other three Google logo colors (four-color "G", Gmail "M"). */
    googleRed: string;
    googleYellow: string;
    googleGreen: string;
    /** Apple Sign-In button fill (black) and its ink (white) — vendor-mandated. */
    apple: string;
    appleInk: string;
  };
};

export const lightTheme: Theme = {
  scheme: "light",
  isDark: false,

  primary: "#4F56E5",
  primaryLight: "#EAEBFF",
  primaryDark: "#3E45C9",

  accent: "#4F56E5",
  accentLight: "#EAEBFF",
  accentDark: "#3E45C9",

  bg: "#FCFCFC",
  surface: "#F7F7F8",
  settingsSurface: "#F3F3F3",
  surfaceAlt: "#EBEBED",
  elevated: "#FFFFFF",
  control: "#F1F1F3",
  border: "#D9D9DE",
  separator: "#DCDCE0",
  pressed: "rgba(17,17,19,0.06)",

  text: "#111113",
  textSecondary: "#5C5C64",
  textTertiary: "#67676F",
  textDisabled: "#8E8E96",

  userBubble: "#F0F1FF",
  userText: "#111113",
  assistantBubble: "#FCFCFC",
  assistantText: "#111113",

  composerBg: "#FFFFFF",
  composerBorder: "#D9D9DE",
  inputBg: "#F7F7F8",

  contentSurface: "#F7F7F8",

  danger: "#CC291D",
  onDanger: "#FFFFFF",
  dangerLight: "#FFF5F5",
  warning: "#AD4407",
  onWarning: "#FFFFFF",
  success: "#137A54",
  successLight: "#EAF7F3",
  onPrimary: "#FFFFFF",
  graphSeries: ["#4F56E5", "#16845B", "#B54708", "#7C3AED"],

  codeBg: "#F7F7F8",
  codeText: "#111113",
  codeLang: "#5C5C64",
  codeInlineBg: "rgba(17,17,19,0.08)",

  scrim: "rgba(0,0,0,0.40)",
  wash: "rgba(17,17,19,0.20)",

  onMedia: "#FFFFFF",
  mediaScrim: "#000000",

  brand: { twitter: "#1DA1F2", linkedin: "#0A66C2", google: "#4285F4", googleRed: "#EA4335", googleYellow: "#FBBC05", googleGreen: "#34A853", apple: "#000000", appleInk: "#FFFFFF" },
};

export const darkTheme: Theme = {
  scheme: "dark",
  isDark: true,

  primary: "#B4B8FF",
  primaryLight: "#2A2D6A",
  primaryDark: "#9AA0F5",

  accent: "#B4B8FF",
  accentLight: "#2A2D6A",
  accentDark: "#9AA0F5",

  bg: "#0F0F10",
  surface: "#202023",
  settingsSurface: "#202023",
  surfaceAlt: "#171719",
  elevated: "#242428",
  control: "#323238",
  border: "#3A3A42",
  separator: "#38383F",
  pressed: "rgba(255,255,255,0.08)",

  text: "#F5F5F6",
  textSecondary: "#A5A5AC",
  textTertiary: "#8A8A92",
  textDisabled: "#7B7B83",

  userBubble: "#2A2D6A",
  userText: "#F5F5F6",
  assistantBubble: "#0F0F10",
  assistantText: "#F5F5F6",

  composerBg: "#323238",
  composerBorder: "#3A3A42",
  inputBg: "#171719",

  contentSurface: "#202023",

  danger: "#FF6B6B",
  onDanger: "#0F0F10",
  dangerLight: "#3B1513",
  warning: "#F5A524",
  onWarning: "#111113",
  success: "#32C48D",
  successLight: "rgba(50, 196, 141, 0.18)",
  onPrimary: "#0F0F10",
  graphSeries: ["#B4B8FF", "#32C48D", "#F5A524", "#C4B5FD"],

  codeBg: "#171719",
  codeText: "#F5F5F6",
  codeLang: "#8E8E96",
  codeInlineBg: "rgba(245,245,246,0.14)",

  scrim: "rgba(0,0,0,0.60)",
  wash: "rgba(0,0,0,0.45)",

  onMedia: "#FFFFFF",
  mediaScrim: "#000000",

  brand: { twitter: "#1DA1F2", linkedin: "#0A66C2", google: "#4285F4", googleRed: "#EA4335", googleYellow: "#FBBC05", googleGreen: "#34A853", apple: "#000000", appleInk: "#FFFFFF" },
};

/** The theme with one accent's tones in every brand slot. */
export function applyAccent(theme: Theme, accent: AccentPreference): Theme {
  const tones = ACCENTS[accent][theme.scheme];
  return {
    ...theme,
    primary: tones.primary,
    primaryLight: tones.primaryLight,
    primaryDark: tones.primaryDark,
    accent: tones.primary,
    accentLight: tones.primaryLight,
    accentDark: tones.primaryDark,
    userBubble: tones.userBubble,
    onPrimary: tones.onPrimary,
    graphSeries: [
      tones.primary,
      theme.graphSeries[1],
      theme.graphSeries[2],
      "series4" in tones ? tones.series4 : theme.graphSeries[3],
    ],
  };
}

const accented = new Map<string, Theme>();

/**
 * The palette for a scheme with an accent applied. One object per pair, so a
 * screen that caches styles per theme object rebuilds only when either changes.
 */
export function themeFor(scheme: "light" | "dark", accent: AccentPreference): Theme {
  const base = scheme === "dark" ? darkTheme : lightTheme;
  if (accent === DEFAULT_ACCENT) return base;
  const key = `${scheme}:${accent}`;
  let theme = accented.get(key);
  if (theme === undefined) {
    theme = applyAccent(base, accent);
    accented.set(key, theme);
  }
  return theme;
}

/** Active palette: the color scheme (system or user override) and the accent color. */
export function useTheme(): Theme {
  return themeFor(useResolvedColorScheme(), useAccentPreference());
}

const HEX_COLOR_RE = /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;
const RGB_COLOR_RE = /^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*[\d.]+\s*)?\)$/;

/**
 * Apply an alpha channel to any theme color — hex or already-rgba(...) alike
 * — so fades/scrims/tints don't need format-specific handling. Components
 * used to do this by string-concatenating a hex alpha suffix directly onto a
 * token (e.g. `` `${theme.bg}FA` ``), which only works when that token
 * happens to be a 6-digit hex string. It silently produces an invalid color
 * (and a blank/opaque render) the moment it's applied to a token that is
 * already `rgba(...)` — which `theme.scrim` and dark mode's `successLight`
 * already are. `alpha` is 0-1; unrecognized formats are returned unchanged
 * rather than mangled.
 */
export function withAlpha(color: string, alpha: number): string {
  const clamped = Math.max(0, Math.min(1, alpha));
  const hex = color.match(HEX_COLOR_RE)?.[1];
  if (hex) {
    const full = hex.length === 3 ? hex.split("").map((c) => c + c).join("") : hex;
    const r = parseInt(full.slice(0, 2), 16);
    const g = parseInt(full.slice(2, 4), 16);
    const b = parseInt(full.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${clamped})`;
  }
  const rgb = color.match(RGB_COLOR_RE);
  if (rgb) {
    return `rgba(${rgb[1]}, ${rgb[2]}, ${rgb[3]}, ${clamped})`;
  }
  return color;
}
