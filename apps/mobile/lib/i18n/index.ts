import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import { DATE_FORMAT_CHANGED } from "@/lib/datetime/format";

import en from "./en.json";
import { installPluralRules } from "./pluralRules";

type LocaleBundle = typeof en;

// Each bundle is evaluated only when its language is first used. The require
// is synchronous so the launch language can be in place before the first frame.
const LOCALE_BUNDLES: Record<string, () => LocaleBundle> = {
  es: () => require("./es.json") as LocaleBundle,
  fr: () => require("./fr.json") as LocaleBundle,
  de: () => require("./de.json") as LocaleBundle,
  it: () => require("./it.json") as LocaleBundle,
  pt: () => require("./pt.json") as LocaleBundle,
  ru: () => require("./ru.json") as LocaleBundle,
  tr: () => require("./tr.json") as LocaleBundle,
  am: () => require("./am.json") as LocaleBundle,
};

const loadedLocales = new Set<string>(["en"]);

/** The supported code for a preference ("en" for unknown), its bundle added. */
function addLocale(lng: string): string {
  const code = lng.trim() || "en";
  if (loadedLocales.has(code)) return code;
  const bundle = LOCALE_BUNDLES[code];
  if (!bundle) return "en";
  i18n.addResourceBundle(code, "translation", bundle(), true, true);
  loadedLocales.add(code);
  return code;
}

/** Boot English only. Other locales load when the user preference is not `en`. */
export async function ensureLocale(lng: string): Promise<void> {
  const code = addLocale(lng);
  // Already in it (the launch language, say): a change event would re-render
  // every translated component for the same words.
  if (code === i18n.language) return;
  await i18n.changeLanguage(code);
}

/**
 * Before the first render: the language the cached account last used
 * (`lib/launchPrefs.ts`). The bundle is already in, so the switch takes
 * effect at once and the first frame is drawn in it.
 */
export function startLocale(lng: string): void {
  const code = addLocale(lng);
  if (code !== i18n.language) void i18n.changeLanguage(code);
}

// Before init: i18next reads the plural rules when it first counts.
installPluralRules();

i18n.use(initReactI18next).init({
  resources: { en: { translation: en } },
  lng: "en",
  fallbackLng: {
    de: ["en"],
    es: ["en"],
    fr: ["en"],
    it: ["en"],
    pt: ["en"],
    ru: ["en"],
    tr: ["en"],
    am: ["en"],
    default: ["en"],
  },
  interpolation: { escapeValue: false },
  // A date follows the phone's zone and clock as it follows the language.
  react: { bindI18n: `languageChanged ${DATE_FORMAT_CHANGED}` },
});

export default i18n;
