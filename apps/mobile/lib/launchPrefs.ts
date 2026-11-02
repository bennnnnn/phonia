/**
 * What the first frame needs from this phone, applied before React renders:
 * the appearance and accent the user picked, and the language of the account
 * signed in last (kept with the cached user). Each is a tiny file read
 * synchronously, so the first frame is already in them and nothing flips.
 */
import { readAccentPreferenceSync } from "@/lib/accentPrefs";
import { setAccentSnapshot } from "@/lib/accentRuntime";
import { getAppearancePreference, readAppearancePreferenceSync } from "@/lib/appearancePrefs";
import { setAppearancePreferenceSnapshot } from "@/lib/appearanceRuntime";
import { readCachedLocaleSync } from "@/lib/cachedUser";
import { startLocale } from "@/lib/i18n";

/**
 * Applies the saved preferences at once. Resolves when they are all in place,
 * which is at once unless the appearance file could not be read synchronously
 * (it is then read the usual way). Never throws: a preference that cannot be
 * applied leaves its default and the launch goes on.
 */
export function restoreLaunchPrefs(): Promise<void> {
  try {
    setAccentSnapshot(readAccentPreferenceSync());
    const locale = readCachedLocaleSync();
    if (locale) startLocale(locale);
    const appearance = readAppearancePreferenceSync();
    if (appearance !== null) {
      setAppearancePreferenceSnapshot(appearance);
      return Promise.resolve();
    }
  } catch {
    console.warn("[launch] saved preferences not applied");
  }
  return getAppearancePreference().then(setAppearancePreferenceSnapshot, () => {});
}
