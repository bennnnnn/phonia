/**
 * Accent color — the one brand hue on buttons, links, selection, progress,
 * focus, the user's bubble tint and the first graph series. Indigo is the
 * default and keeps the palette in `lib/theme.ts` exactly as it is.
 *
 * Every preset passes, in both schemes (checked in `__tests__/accent.test.tsx`):
 * primary on the page ≥ 4.5:1 (links and selected text), onPrimary on primary
 * ≥ 4.5:1 (button labels), and the bubble text on userBubble ≥ 7:1.
 * No green (reads as success) and no red (reads as danger).
 */

type AccentTones = {
  primary: string;
  /** Selected wells and soft fills. */
  primaryLight: string;
  /** Pressed state of a primary fill. */
  primaryDark: string;
  /** The user's chat bubble — a quiet tint of the accent. */
  userBubble: string;
  /** Ink on a primary fill. */
  onPrimary: string;
  /** The fourth graph series, when the default violet sits too near this hue. */
  series4?: string;
};

type AccentPreset = { light: AccentTones; dark: AccentTones };

export const ACCENTS = {
  indigo: {
    light: {
      primary: "#4F56E5",
      primaryLight: "#EAEBFF",
      primaryDark: "#3E45C9",
      userBubble: "#F0F1FF",
      onPrimary: "#FFFFFF",
    },
    dark: {
      primary: "#B4B8FF",
      primaryLight: "#2A2D6A",
      primaryDark: "#9AA0F5",
      userBubble: "#2A2D6A",
      onPrimary: "#0F0F10",
    },
  },
  sapphire: {
    light: {
      primary: "#1661C3",
      primaryLight: "#E3EFFF",
      primaryDark: "#1352A6",
      userBubble: "#F1F7FF",
      onPrimary: "#FFFFFF",
    },
    dark: {
      primary: "#81B5F8",
      primaryLight: "#284162",
      primaryDark: "#64A4F6",
      userBubble: "#284162",
      onPrimary: "#0F0F10",
    },
  },
  ocean: {
    light: {
      primary: "#086A94",
      primaryLight: "#E3F7FF",
      primaryDark: "#075A7E",
      userBubble: "#F1FBFF",
      onPrimary: "#FFFFFF",
    },
    dark: {
      primary: "#53BEEC",
      primaryLight: "#1C3C4A",
      primaryDark: "#3CB5E9",
      userBubble: "#1C3C4A",
      onPrimary: "#0F0F10",
    },
  },
  violet: {
    light: {
      primary: "#7426D9",
      primaryLight: "#EFE4FE",
      primaryDark: "#6320B8",
      userBubble: "#F7F1FE",
      onPrimary: "#FFFFFF",
      series4: "#0E7490",
    },
    dark: {
      primary: "#CAA1FF",
      primaryLight: "#412862",
      primaryDark: "#B780FF",
      userBubble: "#412862",
      onPrimary: "#0F0F10",
      series4: "#22D3EE",
    },
  },
  orchid: {
    light: {
      primary: "#A02CB1",
      primaryLight: "#F9E6FC",
      primaryDark: "#882596",
      userBubble: "#FCF2FE",
      onPrimary: "#FFFFFF",
      series4: "#0E7490",
    },
    dark: {
      primary: "#E992F6",
      primaryLight: "#5A2862",
      primaryDark: "#E375F4",
      userBubble: "#5A2862",
      onPrimary: "#0F0F10",
      series4: "#22D3EE",
    },
  },
  berry: {
    light: {
      primary: "#B52681",
      primaryLight: "#FDE5F4",
      primaryDark: "#9A206E",
      userBubble: "#FEF2F9",
      onPrimary: "#FFFFFF",
    },
    dark: {
      primary: "#F692D2",
      primaryLight: "#62284D",
      primaryDark: "#F475C6",
      userBubble: "#62284D",
      onPrimary: "#0F0F10",
    },
  },
  graphite: {
    light: {
      primary: "#586479",
      primaryLight: "#ECF0F6",
      primaryDark: "#4B5567",
      userBubble: "#F5F7FA",
      onPrimary: "#FFFFFF",
    },
    dark: {
      primary: "#A9B3C3",
      primaryLight: "#3D434D",
      primaryDark: "#98A4B7",
      userBubble: "#3D434D",
      onPrimary: "#0F0F10",
    },
  },
} as const satisfies Record<string, AccentPreset>;

export type AccentPreference = keyof typeof ACCENTS;

export const DEFAULT_ACCENT: AccentPreference = "indigo";

export const ACCENT_OPTIONS = Object.keys(ACCENTS) as AccentPreference[];

export function normalizeAccentPreference(raw: string | null | undefined): AccentPreference {
  return raw && Object.hasOwn(ACCENTS, raw) ? (raw as AccentPreference) : DEFAULT_ACCENT;
}

/** The swatch a picker shows for a preset in the current scheme. */
export function accentSwatch(accent: AccentPreference, scheme: "light" | "dark"): string {
  return ACCENTS[accent][scheme].primary;
}
