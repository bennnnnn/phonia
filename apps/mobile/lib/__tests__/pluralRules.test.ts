import {
  AppPluralRules,
  installPluralRules,
  PLURAL_CATEGORIES,
  pluralCategory,
} from "@/lib/i18n/pluralRules";

const COUNTS = [
  ...Array.from({ length: 230 }, (_, n) => n),
  1001, 1011, 1021, 1_000_000, 2_000_000, 1_000_001, 0.5, 1.5, 2.25, 21.5,
];

describe("pluralCategory", () => {
  // Node's ICU is the reference the phone's fallback must agree with.
  for (const language of Object.keys(PLURAL_CATEGORIES)) {
    it(`matches ICU's cardinal rules for ${language}`, () => {
      const icu = new Intl.PluralRules(language);
      const wrong = COUNTS.filter((n) => pluralCategory(language, n) !== icu.select(n));
      expect(wrong).toEqual([]);
    });

    it(`lists ${language}'s categories as ICU does`, () => {
      const icu = new Intl.PluralRules(language).resolvedOptions().pluralCategories;
      expect([...PLURAL_CATEGORIES[language]!].sort()).toEqual([...icu].sort());
    });
  }
});

describe("AppPluralRules", () => {
  it("answers i18next's calls for a regional code", () => {
    const rules = new AppPluralRules("ru-RU", { type: "cardinal" });
    expect(rules.select(3)).toBe("few");
    expect(rules.resolvedOptions().pluralCategories).toEqual(["one", "few", "many", "other"]);
  });
});

describe("installPluralRules", () => {
  const intl = Intl as unknown as { PluralRules?: unknown };
  const native = intl.PluralRules;
  afterEach(() => {
    intl.PluralRules = native;
  });

  it("fills in a runtime without Intl.PluralRules (Hermes)", () => {
    delete intl.PluralRules;
    installPluralRules();
    expect(intl.PluralRules).toBe(AppPluralRules);
  });

  it("keeps a runtime's own rules", () => {
    installPluralRules();
    expect(intl.PluralRules).toBe(native);
  });
});
