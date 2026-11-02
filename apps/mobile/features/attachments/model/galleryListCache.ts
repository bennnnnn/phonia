import { api, type AttachmentListItem, type Page } from "@/lib/api";
import { onAppEvent } from "@/lib/appEvents";
import { CONTEXT_REFRESH_STALE_MS } from "@/lib/cache/contextRefresh";
import { asError, SessionResourceCache, sessionChanged, type ResourceResult } from "@/lib/cache/sessionResource";
import { GALLERY_PAGE_SIZE, galleryListCacheKey, galleryListParams, mergeGalleryItems, type GalleryFilter } from "@/features/attachments/model/gallery";

export type GalleryPage = { items: AttachmentListItem[]; hasMore: boolean };
/** The rows shown, where the next page starts, and which first page they grew from. */
type GalleryEntry = { page: GalleryPage; nextCursor: string | null; lineage: number };
type NextPageRead = { lineage: number; task: Promise<ResourceResult<GalleryPage>> };
type GallerySession = {
  /** Deleted this session; an earlier read must not bring them back. */
  removed: Set<string>;
  next: Map<string, NextPageRead>;
  lineages: number;
};
type ListResponse = Page<AttachmentListItem>;
/** One entry per filter and search; typing a search must not keep every query forever. */
const MAX_GALLERY_QUERIES = 20;

const resource = new SessionResourceCache<string, GalleryEntry, GallerySession>({
  staleMs: CONTEXT_REFRESH_STALE_MS,
  maxEntries: MAX_GALLERY_QUERIES,
  sessionState: () => ({ removed: new Set(), next: new Map(), lineages: 0 }),
});

function firstEntry(page: GalleryPage, nextCursor: string | null): GalleryEntry {
  return { page, nextCursor, lineage: ++resource.state().lineages };
}
function keptRows(response: ListResponse): AttachmentListItem[] {
  const { removed } = resource.state();
  return response.items.filter((row) => !removed.has(row.id));
}
function readRows(token: string, filter: GalleryFilter, query: string, cursor: string | null): Promise<ListResponse> {
  return api.listAttachments(token, {
    ...galleryListParams(filter), ...(query ? { q: query } : {}), limit: GALLERY_PAGE_SIZE, ...(cursor ? { cursor } : {}),
  });
}
function pageResult(result: ResourceResult<GalleryEntry>): ResourceResult<GalleryPage> {
  return result.error
    ? { data: result.data?.page ?? null, error: result.error }
    : { data: result.data.page, error: null };
}
function withoutItem(entry: GalleryEntry, id: string): GalleryEntry {
  const items = entry.page.items.filter((item) => item.id !== id);
  // The cursor names the last row read, so a deleted row cannot shift the next page.
  return items.length === entry.page.items.length ? entry : { ...entry, page: { ...entry.page, items } };
}

export function getCachedGalleryPage(filter: GalleryFilter, query: string): GalleryPage | undefined {
  return resource.get(galleryListCacheKey(filter, query))?.page;
}
export function isGalleryPageFresh(filter: GalleryFilter, query: string): boolean {
  return resource.isFresh(galleryListCacheKey(filter, query));
}
/** When the first page of this filter and search last came from the server this sign-in. */
export function galleryPageReadAt(filter: GalleryFilter, query: string): number | undefined {
  return resource.fetchedAt(galleryListCacheKey(filter, query));
}
export function setGalleryPage(filter: GalleryFilter, query: string, page: GalleryPage, nextCursor: string | null = null): void {
  resource.set(galleryListCacheKey(filter, query), firstEntry(page, nextCursor));
}
export function invalidateGalleryCache(): void {
  resource.invalidate();
}
// Deleted chats take their photos with them; a picture saved into a chat joins the gallery.
onAppEvent("chatsDeleted", invalidateGalleryCache);
onAppEvent("attachmentAdded", invalidateGalleryCache);
export function removeCachedGalleryItem(id: string): void {
  resource.state().removed.add(id);
  resource.updateEach((entry) => withoutItem(entry, id));
}

export async function fetchGalleryPage(
  token: string, filter: GalleryFilter, query: string, opts?: { force?: boolean },
): Promise<ResourceResult<GalleryPage>> {
  const result = await resource.fetch(galleryListCacheKey(filter, query), token, async () => {
    const response = await readRows(token, filter, query, null);
    return firstEntry({ items: keptRows(response), hasMore: response.next_cursor !== null }, response.next_cursor);
  }, opts);
  return pageResult(result);
}

export async function fetchGalleryNextPage(
  token: string, filter: GalleryFilter, query: string,
): Promise<ResourceResult<GalleryPage>> {
  const key = galleryListCacheKey(filter, query);
  const first = resource.inflight(key);
  if (first) return pageResult(await first);
  const entry = resource.get(key);
  if (!entry) return fetchGalleryPage(token, filter, query);
  if (!entry.page.hasMore) return { data: entry.page, error: null };
  const { next } = resource.state();
  const running = next.get(key);
  if (running?.lineage === entry.lineage) return running.task;
  const task = readNextPage(token, filter, query, entry.lineage);
  next.set(key, { lineage: entry.lineage, task });
  try { return await task; }
  finally { if (next.get(key)?.task === task) next.delete(key); }
}

async function readNextPage(
  token: string, filter: GalleryFilter, query: string, lineage: number,
): Promise<ResourceResult<GalleryPage>> {
  const key = galleryListCacheKey(filter, query);
  const isCurrent = resource.lease();
  // A first-page read that started or landed since makes this page's cursor meaningless.
  const replaced = () => resource.inflight(key) !== undefined || resource.get(key)?.lineage !== lineage;
  try {
    const cursor = resource.get(key)?.nextCursor ?? null;
    const response = await readRows(token, filter, query, cursor);
    if (!isCurrent()) return sessionChanged();
    if (replaced()) return currentPage(key);
    const incoming = keptRows(response);
    // A cursor that did not move would read the same page forever.
    const more = response.next_cursor !== null && response.next_cursor !== cursor;
    const grown = resource.update(key, (current) => ({
      ...current,
      page: { items: mergeGalleryItems(current.page.items, incoming, false), hasMore: more },
      nextCursor: more ? response.next_cursor : null,
    }));
    return currentPage(key, grown);
  } catch (caught) {
    if (!isCurrent()) return sessionChanged();
    return { data: resource.get(key)?.page ?? null, error: asError(caught) };
  }
}

async function currentPage(key: string, entry = resource.get(key)): Promise<ResourceResult<GalleryPage>> {
  const first = resource.inflight(key);
  if (first) return pageResult(await first);
  return entry
    ? { data: entry.page, error: null }
    : { data: null, error: new Error("The Library page was replaced.") };
}

/** Warm All so Library can paint without a skeleton. */
export function prefetchGallery(token: string): void {
  void fetchGalleryPage(token, "all", "");
}
