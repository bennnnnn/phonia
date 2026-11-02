import { openAllowedUrl } from "@/lib/linkSchemePolicy";

/**
 * Opens a link from a settings page; throws when it did not open (no mail app for a
 * mailto, a blocked scheme), so the settings action reports it instead of nothing.
 */
export async function openSettingsLink(url: string | null | undefined): Promise<void> {
  if (!(await openAllowedUrl(url))) throw new Error("link_not_opened");
}
