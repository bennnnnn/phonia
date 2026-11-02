import { parseFenceLang } from "@/lib/codeHighlight";
import {
  collectClosedFenceBodies,
  dropFences,
  mapUnlabeledClosedFences,
} from "@/lib/mdFenceScan";

export type SearchSource = {
  title: string;
  url: string;
  snippet?: string;
};

const SOURCES_LABEL_RE = /(?:\*\*)?sources(?:\*\*)?\s*:?\s*$/i;

function normalizeSourceRows(parsed: unknown): SearchSource[] {
  if (!Array.isArray(parsed)) return [];
  return parsed.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const row = item as Record<string, unknown>;
    const title = String(row.title ?? "").trim();
    const url = String(row.url ?? "").trim();
    if (!title && !url) return [];
    const snippetRaw = String(row.snippet ?? "").trim();
    const source: SearchSource = {
      title: title || url,
      url,
    };
    if (snippetRaw) source.snippet = snippetRaw;
    return [source];
  });
}

export function parseSearchSourcesJson(raw: string): SearchSource[] {
  const text = raw.trim();
  try {
    return normalizeSourceRows(JSON.parse(text));
  } catch {
    return [];
  }
}

/** A `done` event's `search_sources`: JSON text today, an array once the server sends one (ES-45). */
export function searchSourcesFromField(value: unknown): SearchSource[] {
  return typeof value === "string" ? parseSearchSourcesJson(value) : normalizeSourceRows(value);
}

export function parseSearchSources(content: string): SearchSource[] {
  const fromFence = collectClosedFenceBodies(content, "sources").flatMap((body) =>
    parseSearchSourcesJson(body),
  );
  if (fromFence.length > 0) return fromFence;

  const fromBare: SearchSource[] = [];
  mapUnlabeledClosedFences(content, (body, original) => {
    fromBare.push(...parseSearchSourcesJson(body));
    return original;
  });
  return fromBare;
}

export function resolveSearchSources(
  content: string,
  attached?: SearchSource[] | null,
): SearchSource[] {
  if (attached && attached.length > 0) return attached;
  // Sources only ever arrive inside a fence — skip the scan otherwise.
  if (!content.includes("```")) return [];
  return parseSearchSources(content);
}

/** Remove ```sources fences and unlabeled source-JSON fences from visible markdown. */
export function stripSearchSourcesFromContent(content: string): string {
  // One scan: dropping a closed fence leaves how the rest of the text reads unchanged.
  const text = dropFences(
    content,
    (span) =>
      span.closed &&
      (parseFenceLang(span.info) === "sources" ||
        (span.info === "" && parseSearchSourcesJson(span.body).length > 0)),
  );
  return text.replace(SOURCES_LABEL_RE, "").trimEnd();
}

export function hostnameFromUrl(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url.replace(/^https?:\/\//, "").split("/")[0] ?? url;
  }
}

/** First hit per host, then remaining duplicates — compact chips, full sheet. */
export function preferDistinctHostSources(sources: SearchSource[]): SearchSource[] {
  const seen = new Set<string>();
  const unique: SearchSource[] = [];
  const rest: SearchSource[] = [];
  for (const source of sources) {
    const host = hostnameFromUrl(source.url).toLowerCase();
    if (!host || seen.has(host)) {
      rest.push(source);
      continue;
    }
    seen.add(host);
    unique.push(source);
  }
  return [...unique, ...rest];
}

export function faviconHost(url: string): string {
  const host = hostnameFromUrl(url);
  return host || "web";
}

export function faviconUrl(url: string): string {
  const host = hostnameFromUrl(url);
  if (!host) return "";
  return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=64`;
}
