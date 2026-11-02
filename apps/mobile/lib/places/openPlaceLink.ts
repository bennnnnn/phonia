import { googleMapsSearchUrl, isGenericSearchUrl } from "@/lib/places/placesList";
import { openAllowedUrl } from "@/lib/linkSchemePolicy";

export async function openPlaceLink(url: string, label?: string): Promise<void> {
  const trimmed = url.trim();
  const fallback = label?.trim() ? googleMapsSearchUrl(label.trim()) : "";
  const target =
    trimmed && !isGenericSearchUrl(trimmed)
      ? trimmed
      : fallback || trimmed;

  if (!target) return;

  if (await openAllowedUrl(target)) return;
  if (fallback && fallback !== target) {
    await openAllowedUrl(fallback);
  }
}
