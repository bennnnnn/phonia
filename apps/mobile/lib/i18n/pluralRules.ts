/**
 * Plural categories for the app's languages, so counted strings read right
 * ("1 source", "2 источника", "5 источников").
 *
 * i18next picks a `_one` / `_few` / `_many` / `_other` key with
 * `Intl.PluralRules`. Hermes may not ship it, and i18next then falls back to
 * English's one/other for every language, so Russian would say
 * "2 источников". `installPluralRules` fills in the CLDR cardinal rules for
 * these nine languages only where the runtime has none; a runtime that has
 * them keeps its own. The test checks these rules against Node's ICU.
 */

type PluralCategory = "one" | "few" | "many" | "other";

/** The categories each language's strings must provide, in i18next's order. */
export const PLURAL_CATEGORIES: Record<string, readonly PluralCategory[]> = {
  en: ["one", "other"],
  am: ["one", "other"],
  de: ["one", "other"],
  tr: ["one", "other"],
  es: ["one", "many", "other"],
  fr: ["one", "many", "other"],
  it: ["one", "many", "other"],
  pt: ["one", "many", "other"],
  ru: ["one", "few", "many", "other"],
};

/** Exact millions take `many` in the Romance languages ("1 000 000 de sources"). */
function isMillions(i: number, v: number): boolean {
  return v === 0 && i !== 0 && i % 1_000_000 === 0;
}

/** CLDR cardinal plural category of `count` in `language`. */
export function pluralCategory(language: string, count: number): PluralCategory {
  const n = Math.abs(count);
  const i = Math.floor(n);
  // Visible fraction digits, as JS prints the number.
  const v = (String(n).split(".")[1] ?? "").length;
  switch (language.split(/[-_]/)[0]) {
    case "ru": {
      if (v !== 0) return "other";
      const d = i % 10;
      const dd = i % 100;
      if (d === 1 && dd !== 11) return "one";
      if (d >= 2 && d <= 4 && (dd < 12 || dd > 14)) return "few";
      return "many";
    }
    case "fr":
    case "pt":
      if (i === 0 || i === 1) return "one";
      return isMillions(i, v) ? "many" : "other";
    case "es":
      if (n === 1) return "one";
      return isMillions(i, v) ? "many" : "other";
    case "it":
      if (i === 1 && v === 0) return "one";
      return isMillions(i, v) ? "many" : "other";
    case "am":
      return i === 0 || n === 1 ? "one" : "other";
    case "tr":
      return n === 1 ? "one" : "other";
    default:
      // English and German: one only for an integer 1.
      return i === 1 && v === 0 ? "one" : "other";
  }
}

/** The subset of `Intl.PluralRules` i18next calls. */
export class AppPluralRules {
  private readonly language: string;
  private readonly ordinal: boolean;

  constructor(locales?: string | string[], options?: { type?: string }) {
    const first = Array.isArray(locales) ? locales[0] : locales;
    this.language = (first ?? "en").split(/[-_]/)[0] ?? "en";
    this.ordinal = options?.type === "ordinal";
  }

  select(count: number): PluralCategory {
    // No ordinal strings exist; every ordinal reads as `other`.
    return this.ordinal ? "other" : pluralCategory(this.language, count);
  }

  resolvedOptions() {
    return {
      locale: this.language,
      type: this.ordinal ? "ordinal" : "cardinal",
      pluralCategories: this.ordinal ? ["other"] : [...(PLURAL_CATEGORIES[this.language] ?? ["one", "other"])],
    };
  }
}

/** Gives the runtime plural rules when it has none (Hermes). */
export function installPluralRules(): void {
  if (typeof Intl === "undefined") return;
  if (typeof (Intl as { PluralRules?: unknown }).PluralRules === "function") return;
  (Intl as unknown as { PluralRules: unknown }).PluralRules = AppPluralRules;
}
