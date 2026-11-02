import {
  ACCENT_OPTIONS,
  ACCENTS,
  DEFAULT_ACCENT,
  normalizeAccentPreference,
  type AccentPreference,
} from "@/lib/accent";
import { applyAccent, darkTheme, lightTheme, themeFor } from "@/lib/theme";

/** WCAG 2.1 relative luminance of a #RRGGBB color. */
function luminance(hex: string): number {
  const channels = [1, 3, 5].map((start) => parseInt(hex.slice(start, start + 2), 16) / 255);
  const [r, g, b] = channels.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const SCHEMES = [lightTheme, darkTheme];

describe("accent presets", () => {
  it.each(ACCENT_OPTIONS)("%s keeps links, buttons and the user bubble readable", (accent) => {
    for (const base of SCHEMES) {
      const theme = applyAccent(base, accent);
      // Links and selected text on the page and on cards.
      expect(contrast(theme.primary, theme.bg)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(theme.primary, theme.surface)).toBeGreaterThanOrEqual(4.5);
      // ...in a pressed well, a menu and a Settings group.
      expect(contrast(theme.primary, theme.surfaceAlt)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(theme.primary, theme.elevated)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(theme.primary, theme.settingsSurface)).toBeGreaterThanOrEqual(4.5);
      // Button labels on a primary fill, also when pressed.
      expect(contrast(theme.onPrimary, theme.primary)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(theme.onPrimary, theme.primaryDark)).toBeGreaterThanOrEqual(4.5);
      // The user's own messages.
      expect(contrast(theme.userText, theme.userBubble)).toBeGreaterThanOrEqual(7);
      // Selected text on a soft accent well: plain ink and accent ink (a selected chip).
      expect(contrast(theme.text, theme.primaryLight)).toBeGreaterThanOrEqual(7);
      expect(contrast(theme.primary, theme.primaryLight)).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("indigo is the default and leaves the palette exactly as it was", () => {
    expect(DEFAULT_ACCENT).toBe("indigo");
    expect(themeFor("light", "indigo")).toBe(lightTheme);
    expect(themeFor("dark", "indigo")).toBe(darkTheme);
    for (const base of SCHEMES) {
      expect(applyAccent(base, "indigo")).toEqual(base);
    }
  });

  it("an accent fills every brand slot and nothing else", () => {
    for (const accent of ACCENT_OPTIONS) {
      for (const base of SCHEMES) {
        const theme = applyAccent(base, accent);
        const tones = ACCENTS[accent][base.scheme];
        expect(theme.accent).toBe(tones.primary);
        expect(theme.accentLight).toBe(tones.primaryLight);
        expect(theme.accentDark).toBe(tones.primaryDark);
        expect(theme.graphSeries[0]).toBe(tones.primary);
        expect(theme.success).toBe(base.success);
        expect(theme.danger).toBe(base.danger);
        expect(theme.text).toBe(base.text);
      }
    }
  });

  it("one theme object per scheme and accent, so cached styles stay valid", () => {
    for (const accent of ACCENT_OPTIONS) {
      expect(themeFor("light", accent)).toBe(themeFor("light", accent));
      expect(themeFor("dark", accent)).toBe(themeFor("dark", accent));
    }
  });

  it("an unknown or missing stored value falls back to indigo", () => {
    expect(normalizeAccentPreference(null)).toBe("indigo");
    expect(normalizeAccentPreference("chartreuse")).toBe("indigo");
    expect(normalizeAccentPreference("__proto__")).toBe("indigo");
    for (const accent of ACCENT_OPTIONS) {
      expect(normalizeAccentPreference(accent)).toBe<AccentPreference>(accent);
    }
  });
});
