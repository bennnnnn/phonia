/**
 * Single source of truth for supported UI languages.
 *
 * To add a language: drop a `<code>.json` next to this file (mirror `en.json`'s
 * keys), add a loader in `index.ts` `LOCALE_LOADERS`, and add one entry here.
 * Missing keys fall back to English automatically.
 */
type LanguageMeta = {
  code: string;
  /** Endonym — shown in its own language. */
  label: string;
  /** BCP-47 tag for speech / TTS. */
  speechLocale: string;
  /** Right-to-left script (needs RTL layout work beyond strings). */
  rtl?: boolean;
};

export const LANGUAGES: LanguageMeta[] = [
  { code: "en", label: "English", speechLocale: "en-US" },
  { code: "es", label: "Español", speechLocale: "es-ES" },
  { code: "fr", label: "Français", speechLocale: "fr-FR" },
  { code: "de", label: "Deutsch", speechLocale: "de-DE" },
  { code: "it", label: "Italiano", speechLocale: "it-IT" },
  { code: "pt", label: "Português", speechLocale: "pt-PT" },
  { code: "ru", label: "Русский", speechLocale: "ru-RU" },
  { code: "tr", label: "Türkçe", speechLocale: "tr-TR" },
  { code: "am", label: "አማርኛ", speechLocale: "am-ET" },
];

export function speechLocale(code?: string | null): string {
  const normalized = (code ?? "en").trim().toLowerCase();
  return LANGUAGES.find((item) => item.code === normalized)?.speechLocale ?? "en-US";
}
