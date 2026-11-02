export type AppearancePreference = "system" | "light" | "dark";

export const APPEARANCE_OPTIONS: AppearancePreference[] = ["system", "light", "dark"];

export function normalizeAppearancePreference(
  raw: string | null | undefined,
): AppearancePreference {
  if (raw === "light" || raw === "dark" || raw === "system") return raw;
  return "system";
}

/** Map stored preference + OS scheme to the palette key used by `useTheme()`. */
export function resolveColorScheme(
  systemScheme: "light" | "dark" | "unspecified" | null | undefined,
  preference: AppearancePreference,
): "light" | "dark" {
  if (preference === "light") return "light";
  if (preference === "dark") return "dark";
  return systemScheme === "dark" ? "dark" : "light";
}
