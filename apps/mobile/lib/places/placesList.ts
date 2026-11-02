import {
  collectClosedFenceBodies,
  mapClosedLangFence,
  stripClosedLangFence,
} from "@/lib/mdFenceScan";

export type PlaceItem = {
  name: string;
  url: string;
  note?: string;
  address?: string;
  price?: string;
};

function parseAllPlacesFences(content: string): PlaceItem[] {
  return collectClosedFenceBodies(content, "places").flatMap((body) =>
    parsePlacesJson(body.trim()),
  );
}

/** Unified venue list — ```places fences, or ```json arrays the model mis-tagged. */
export function resolvePlaces(content: string): PlaceItem[] {
  const fromPlaces = parseAllPlacesFences(content);
  if (fromPlaces.length > 0) return fromPlaces;
  return parsePlacesJsonFences(content);
}

/** Remove places/json venue fences from prose (leave markdown body intact). */
export function stripPlacesContent(content: string, places: PlaceItem[]): string {
  if (places.length === 0) return content;
  let stripped = stripClosedLangFence(content, "places");
  if (stripped.toLowerCase().includes("```json")) {
    stripped = mapClosedLangFence(stripped, "json", (body) => {
      try {
        return looksLikePlacesArray(JSON.parse(body.trim()))
          ? ""
          : `\`\`\`json\n${body}\`\`\``;
      } catch {
        return `\`\`\`json\n${body}\`\`\``;
      }
    });
  }
  return stripped.replace(/\n{3,}/g, "\n\n").trimEnd();
}

/** Google Maps search/deep link — opens Maps on iOS and Android. */
export function googleMapsSearchUrl(query: string): string {
  const q = query.trim();
  if (!q) return "";
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(q)}`;
}

export function isGenericSearchUrl(url: string): boolean {
  const trimmed = url.trim();
  if (!trimmed) return true;
  try {
    const u = new URL(trimmed);
    const host = u.hostname.replace(/^www\./, "").toLowerCase();
    const path = u.pathname.toLowerCase();
    if (host === "yelp.com" && path.startsWith("/search")) return true;
    // Require an exact google.com host or a real subdomain (not evilgoogle.com).
    if (
      (host === "google.com" || host.endsWith(".google.com")) &&
      path.includes("/search")
    ) {
      return true;
    }
    if (host === "bing.com" && path.includes("/search")) return true;
    if (host === "duckduckgo.com") return true;
    return false;
  } catch {
    return true;
  }
}

function mapsQueryForPlace(name: string, address: string): string {
  const n = name.trim();
  const a = address.trim();
  if (!a) return n;
  if (!n) return a;
  const nameRe = new RegExp(`\\b${n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "i");
  if (nameRe.test(a)) return a;
  return `${n}, ${a}`;
}

/** Open Maps for the venue — prefer a direct venue URL when present. */
export function resolvePlaceLinkUrl(place: Pick<PlaceItem, "name" | "url" | "address">): string {
  const raw = place.url?.trim() ?? "";
  if (raw && !isGenericSearchUrl(raw)) {
    return raw;
  }
  const name = place.name.trim();
  const address = place.address?.trim() ?? "";
  return googleMapsSearchUrl(mapsQueryForPlace(name, address));
}

function looksLikePlacesArray(parsed: unknown): boolean {
  if (!Array.isArray(parsed) || parsed.length === 0) return false;
  return parsed.every((item) => {
    if (!item || typeof item !== "object") return false;
    const row = item as Record<string, unknown>;
    return typeof row.name === "string" && row.name.trim().length > 0;
  });
}

function parsePlacesJsonFences(content: string): PlaceItem[] {
  const places: PlaceItem[] = [];
  for (const raw of collectClosedFenceBodies(content, "json")) {
    try {
      const parsed: unknown = JSON.parse(raw.trim());
      if (looksLikePlacesArray(parsed)) {
        places.push(...normalizePlaceRows(parsed));
      }
    } catch {
      // ignore non-JSON fences
    }
  }
  return places;
}

function normalizePlaceRows(parsed: unknown): PlaceItem[] {
  if (!Array.isArray(parsed)) return [];
  return parsed.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const row = item as Record<string, unknown>;
    const name = String(row.name ?? "").trim();
    const rawUrl = String(row.url ?? "").trim();
    const note = String(row.note ?? row.snippet ?? "").trim();
    const address = String(row.address ?? row.location ?? "").trim();
    const price = String(row.price ?? row.price_tier ?? "").trim();
    if (!name) return [];

    const place: PlaceItem = {
      name,
      url: resolvePlaceLinkUrl({ name, url: rawUrl, address }),
    };
    if (note) place.note = note;
    if (address) place.address = address;
    if (price) place.price = price;
    return [place];
  });
}

export function parsePlacesJson(raw: string): PlaceItem[] {
  try {
    return normalizePlaceRows(JSON.parse(raw));
  } catch {
    return [];
  }
}

/** Fix model output where markdown links use $url$ instead of (url).
 * Only fires when the delimited content looks like a URL — otherwise adjacent
 * inline math spans merge: `$x \in [0,2]$ \times $y \in [1,3]$` would turn
 * `[0,2]$ \times $` into `[0,2]( \times )`, leaking the `$` delimiters and
 * painting `0,2` as a blue link. */
export function repairBrokenMarkdownLinks(content: string): string {
  return content.replace(
    /\[([^\]\n]+)\]\$([^$\n]+?)\$/g,
    (full, label: string, url: string) =>
      looksLikeUrl(url) ? `[${label}](${url})` : full,
  );
}

function looksLikeUrl(s: string): boolean {
  const t = s.trim();
  if (!t) return false;
  return /:\/\//.test(t) || /^www\./i.test(t) || /^\.{0,2}\//.test(t);
}
