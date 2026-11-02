import {
  DOCUMENT_GROUPS,
  STANDARD_DOCUMENT_KEYS,
} from "@/features/memory/model/memoryDocuments";
import i18n, { ensureLocale, startLocale } from "@/lib/i18n";
import { PLURAL_CATEGORIES } from "@/lib/i18n/pluralRules";
import en from "@/lib/i18n/en.json";
import am from "@/lib/i18n/am.json";
import de from "@/lib/i18n/de.json";
import es from "@/lib/i18n/es.json";
import fr from "@/lib/i18n/fr.json";
import itLocale from "@/lib/i18n/it.json";
import pt from "@/lib/i18n/pt.json";
import ru from "@/lib/i18n/ru.json";
import tr from "@/lib/i18n/tr.json";

const LOCALES = { am, de, es, fr, it: itLocale, pt, ru, tr } as const;
const PLURAL_SUFFIX = /_(one|few|many|other)$/;

/**
 * A counted string's form: `chat.sources_count_one` is `chat.sources_count`
 * in the `one` form. A counted string always has an `_other` form, which
 * keeps out a plain key that merely ends in `_many`.
 */
function pluralForm(bundle: object, key: string): { base: string; form: string } | null {
  const match = PLURAL_SUFFIX.exec(key);
  if (!match) return null;
  const base = key.slice(0, match.index);
  return `${base}_other` in bundle ? { base, form: match[1] ?? "" } : null;
}

/** Keys with one entry per counted string. */
function baseKeys(bundle: object): string[] {
  return [...new Set(Object.keys(bundle).map((key) => pluralForm(bundle, key)?.base ?? key))].sort();
}

/** Each counted string's plural forms, by its base key. */
function pluralForms(bundle: object): Map<string, string[]> {
  const forms = new Map<string, string[]>();
  for (const key of Object.keys(bundle)) {
    const plural = pluralForm(bundle, key);
    if (plural) forms.set(plural.base, [...(forms.get(plural.base) ?? []), plural.form]);
  }
  return forms;
}

const EN_KEYS = baseKeys(en);

describe("i18n locale files", () => {
  for (const [code, bundle] of Object.entries(LOCALES)) {
    it(`${code}.json has every en.json key`, () => {
      const keys = baseKeys(bundle);
      const missing = EN_KEYS.filter((k) => !keys.includes(k));
      const extra = keys.filter((k) => !EN_KEYS.includes(k));
      expect(missing).toEqual([]);
      expect(extra).toEqual([]);
    });
  }

  // A language counts with its own forms: Russian has four, English two.
  for (const [code, bundle] of Object.entries({ en, ...LOCALES })) {
    it(`${code}.json gives each counted string exactly ${code}'s plural forms`, () => {
      const want = [...(PLURAL_CATEGORIES[code] ?? [])].sort();
      const wrong = [...pluralForms(bundle)].filter(([, forms]) => forms.sort().join() !== want.join());
      expect(wrong).toEqual([]);
    });
  }
});

describe("i18n runtime", () => {
  it("boots with English only", () => {
    expect(i18n.hasResourceBundle("en", "translation")).toBe(true);
    expect(i18n.hasResourceBundle("es", "translation")).toBe(false);
  });

  it("resolves every English key to its own text", async () => {
    await ensureLocale("en");
    const wrong = Object.entries(en)
      .filter(([, value]) => typeof value === "string" && !value.includes("{{"))
      .filter(([key, value]) => i18n.t(key) !== value)
      .map(([key]) => key);
    expect(wrong).toEqual([]);
  });

  it("resolves the memory page words the app builds from server keys", async () => {
    await ensureLocale("en");
    const keys = [
      ...STANDARD_DOCUMENT_KEYS.flatMap((key) => [
        `memory.doc.${key}.title`,
        `memory.doc.${key}.summary`,
      ]),
      ...DOCUMENT_GROUPS.map((group) => `memory.group.${group}`),
    ];
    // A key that falls through comes back unchanged.
    expect(keys.filter((key) => i18n.t(key) === key)).toEqual([]);
  });

  it("loads a locale on demand and falls back for unknown codes", async () => {
    await ensureLocale("es");
    expect(i18n.hasResourceBundle("es", "translation")).toBe(true);
    expect(i18n.language).toBe("es");

    await ensureLocale("not-a-locale");
    expect(i18n.language).toBe("en");
  });

  it("switches to the launch language at once, before anything renders", () => {
    startLocale("fr");
    // No await: the first frame reads it synchronously.
    expect(i18n.language).toBe("fr");
    expect(i18n.t("common.retry")).toBe(fr["common.retry"]);

    startLocale("not-a-locale");
    expect(i18n.language).toBe("en");
  });

  it("counts in each language's plural forms", async () => {
    await ensureLocale("en");
    expect(i18n.t("chat.sources_count", { count: 1 })).toBe("1 source");
    expect(i18n.t("chat.sources_count", { count: 3 })).toBe("3 sources");
    await ensureLocale("ru");
    const ruSources = [1, 2, 5, 11, 21, 22, 25].map((count) => i18n.t("chat.sources_count", { count }));
    expect(ruSources).toEqual([
      "1 источник",
      "2 источника",
      "5 источников",
      "11 источников",
      "21 источник",
      "22 источника",
      "25 источников",
    ]);
    await ensureLocale("en");
  });

  it("counts selected chats and to-dos in each language's forms, one included", async () => {
    await ensureLocale("en");
    expect(i18n.t("drawer.bulk_archive_confirm_body", { count: 1 })).toBe("Archive 1 conversation?");
    expect(i18n.t("drawer.bulk_deleted_toast", { count: 3 })).toBe("Deleted 3 conversations");
    expect(i18n.t("todos.delete_selected", { count: 1 })).toBe("Delete 1 to-do?");
    await ensureLocale("ru");
    const ruArchive = [1, 3, 5, 21].map((count) => i18n.t("drawer.bulk_archive_confirm_body", { count }));
    expect(ruArchive).toEqual([
      "Переместить 1 чат в архив?",
      "Переместить 3 чата в архив?",
      "Переместить 5 чатов в архив?",
      "Переместить 21 чат в архив?",
    ]);
    await ensureLocale("en");
  });

  it("does not announce a change to the language already in use", async () => {
    const changed = jest.fn();
    i18n.on("languageChanged", changed);
    await ensureLocale("en");
    expect(changed).not.toHaveBeenCalled();
    await ensureLocale("de");
    expect(changed).toHaveBeenCalledWith("de");
    i18n.off("languageChanged", changed);
    await ensureLocale("en");
  });
});
