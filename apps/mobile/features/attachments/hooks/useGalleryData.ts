import { useCallback, useEffect, useRef, useState } from "react";
import { useFocusEffect } from "expo-router";

import { useAuth } from "@/contexts/AuthContext";
import { useReconnectRefresh } from "@/hooks/useReconnectRefresh";
import { getSessionGeneration } from "@/lib/auth";
import { type AttachmentListItem } from "@/lib/api";
import {
  fetchGalleryNextPage,
  fetchGalleryPage,
  galleryPageReadAt,
  getCachedGalleryPage,
  isGalleryPageFresh,
  removeCachedGalleryItem,
  type GalleryPage,
} from "@/features/attachments/model/galleryListCache";
import {
  GALLERY_SEARCH_DEBOUNCE_MS,
  galleryListCacheKey,
  type GalleryFilter,
} from "@/features/attachments/model/gallery";

function pageFromCache(snapshot: GalleryPage | undefined): {
  items: AttachmentListItem[];
  hasMore: boolean;
  loading: boolean;
} {
  if (!snapshot) return { items: [], hasMore: false, loading: true };
  return { items: snapshot.items, hasMore: snapshot.hasMore, loading: false };
}

export function useGalleryData(filter: GalleryFilter, searchQuery: string) {
  const { token } = useAuth();
  const trimmedQuery = searchQuery.trim();
  const [debouncedQuery, setDebouncedQuery] = useState(trimmedQuery);
  const session = getSessionGeneration();
  const cacheKey = `${session}:${galleryListCacheKey(filter, debouncedQuery)}`;
  const snapshot = getCachedGalleryPage(filter, debouncedQuery);
  const initial = pageFromCache(snapshot);

  const [pageKey, setPageKey] = useState(cacheKey);
  const [items, setItems] = useState<AttachmentListItem[]>(initial.items);
  const [loading, setLoading] = useState(initial.loading);
  const [loadingMore, setLoadingMore] = useState(false);
  const [pageError, setPageError] = useState(false);
  const [error, setError] = useState(false);
  const [hasMore, setHasMore] = useState(initial.hasMore);
  const [pullRefreshing, setPullRefreshing] = useState(false);
  const inFlightRef = useRef(false);
  const genRef = useRef(0);
  const failedResetRef = useRef(true);

  if (pageKey !== cacheKey) {
    genRef.current += 1;
    inFlightRef.current = false;
    const next = pageFromCache(snapshot);
    setPageKey(cacheKey);
    setItems(next.items);
    setHasMore(next.hasMore);
    setLoading(next.loading);
    setError(false);
    setPageError(false);
    setLoadingMore(false);
    setPullRefreshing(false);
  }

  useEffect(() => {
    const handle = setTimeout(() => setDebouncedQuery(trimmedQuery), GALLERY_SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [trimmedQuery]);

  /** Resolves false when the page could not be fetched (stale or skipped loads resolve true). */
  const load = useCallback(
    async (options: { reset?: boolean; silent?: boolean; force?: boolean } = {}): Promise<boolean> => {
      if (!token || session !== getSessionGeneration()) return true;
      const reset = options.reset ?? true;
      if (!reset && inFlightRef.current) return true;

      if (reset) genRef.current += 1;
      if (reset && !options.force && isGalleryPageFresh(filter, debouncedQuery)) {
        const cached = getCachedGalleryPage(filter, debouncedQuery);
        if (cached) {
          setItems(cached.items);
          setHasMore(cached.hasMore);
          setLoading(false);
          setLoadingMore(false);
          setError(false);
          setPageError(false);
          inFlightRef.current = false;
          return true;
        }
      }

      const gen = genRef.current;
      inFlightRef.current = true;
      const cached = getCachedGalleryPage(filter, debouncedQuery);
      if (!options.silent) {
        if (reset && !cached) setLoading(true);
        else if (!reset) setLoadingMore(true);
      }
      try {
        const result = reset
          ? await fetchGalleryPage(token, filter, debouncedQuery, { force: options.force })
          : await fetchGalleryNextPage(token, filter, debouncedQuery);
        if (gen !== genRef.current || session !== getSessionGeneration()) return true;
        if (result.error) {
          failedResetRef.current = reset;
          if (reset && !cached) setError(true);
          else setPageError(true);
          return false;
        }
        setItems(result.data.items);
        setHasMore(result.data.hasMore);
        setError(false);
        setPageError(false);
        return true;
      } finally {
        if (gen === genRef.current) {
          inFlightRef.current = false;
          setLoading(false);
          setLoadingMore(false);
        }
      }
    },
    [debouncedQuery, filter, token, session],
  );

  useFocusEffect(
    useCallback(() => {
      void load({ reset: true });
      return () => { genRef.current += 1; inFlightRef.current = false; };
    }, [load]),
  );
  // The API back after an outage: the page read again, as coming back to the screen reads it.
  useReconnectRefresh(() => void load({ reset: true }), {
    readAt: () => galleryPageReadAt(filter, debouncedQuery),
  });

  /** Pull to refresh. Resolves false when it failed and the list kept older items. */
  const refresh = useCallback(async (): Promise<boolean> => {
    setPullRefreshing(true);
    const pending = load({ reset: true, silent: true, force: true });
    const generation = genRef.current;
    const ok = await pending;
    if (generation !== genRef.current) return true;
    setPullRefreshing(false);
    return ok;
  }, [load]);

  const loadMore = useCallback(() => {
    if (!hasMore || loadingMore || loading || pageError || inFlightRef.current) return;
    void load({ reset: false });
  }, [hasMore, load, loading, loadingMore, pageError]);

  const retryPage = useCallback(() => load({
    reset: failedResetRef.current,
    force: failedResetRef.current,
  }), [load]);

  const removeItem = useCallback((id: string) => {
    removeCachedGalleryItem(id);
    setItems((current) => current.filter((row) => row.id !== id));
  }, []);

  return {
    items,
    loading,
    loadingMore,
    error,
    pageError,
    retryPage,
    pullRefreshing,
    refresh,
    loadMore,
    retry: load,
    removeItem,
  };
}
