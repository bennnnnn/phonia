import type { SearchResult } from "@/lib/api";

export const DRAWER_SEARCH_DEBOUNCE_MS = 300;
export const DRAWER_SEARCH_PAGE_SIZE = 20;
// The server's minimum: a trigram index cannot narrow a shorter substring.
const DRAWER_SEARCH_MIN_LENGTH = 3;
const DRAWER_SEARCH_MAX_LENGTH = 200;

/** Python's request bounds count Unicode code points, not UTF-16 code units. */
export function isValidDrawerSearchQuery(query: string): boolean {
  const length = Array.from(query.trim()).length;
  return length >= DRAWER_SEARCH_MIN_LENGTH && length <= DRAWER_SEARCH_MAX_LENGTH;
}

/** Stable display identity: a hit already shown keeps its place. */
export function mergeDrawerSearchResults(previous: SearchResult[], incoming: SearchResult[]): SearchResult[] {
  const byId = new Map<string, SearchResult>();
  for (const result of [...previous, ...incoming]) {
    const id = result.message_id ? `message:${result.chat_id}:${result.message_id}` : `title:${result.chat_id}`;
    byId.set(id, result);
  }
  return [...byId.values()];
}
