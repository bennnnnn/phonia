// Manual mock for react-i18next in Jest: every test gets this one unless its file
// mocks or unmocks the module itself (code-health audit TEST-07). `t` answers as
// react-i18next does for a key it has no text for: the caller's `defaultValue`,
// else the key. A test checks which string a screen shows without depending on its
// English copy. As in the real hook, `t` and `i18n` keep their identity.
function t(key: string, options?: string | { defaultValue?: unknown }): string {
  if (typeof options === "string") return options;
  if (typeof options?.defaultValue === "string") return options.defaultValue;
  return key;
}

const i18n = { language: "en", resolvedLanguage: "en" };

export function useTranslation() {
  return { t, i18n, ready: true };
}

/** lib/i18n boots the real i18next with this plugin; here it has nothing to bind. */
export const initReactI18next = { type: "3rdParty" as const, init: () => undefined };
