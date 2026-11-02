import {
  normalizeAppearancePreference,
  resolveColorScheme,
} from "@/lib/appearance";

describe("appearance", () => {
  it("normalizeAppearancePreference defaults invalid values to system", () => {
    expect(normalizeAppearancePreference(undefined)).toBe("system");
    expect(normalizeAppearancePreference("")).toBe("system");
    expect(normalizeAppearancePreference("auto")).toBe("system");
  });

  it("normalizeAppearancePreference keeps valid values", () => {
    expect(normalizeAppearancePreference("light")).toBe("light");
    expect(normalizeAppearancePreference("dark")).toBe("dark");
    expect(normalizeAppearancePreference("system")).toBe("system");
  });

  it("resolveColorScheme honors manual overrides", () => {
    expect(resolveColorScheme("light", "dark")).toBe("dark");
    expect(resolveColorScheme("dark", "light")).toBe("light");
  });

  it("resolveColorScheme follows system when preference is system", () => {
    expect(resolveColorScheme("dark", "system")).toBe("dark");
    expect(resolveColorScheme("light", "system")).toBe("light");
    expect(resolveColorScheme(null, "system")).toBe("light");
  });
});
