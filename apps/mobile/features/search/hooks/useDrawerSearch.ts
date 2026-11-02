import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import type { TextInput } from "react-native";

import { api, type SearchResult } from "@/lib/api";
import { isAbortError } from "@/lib/api/abort";
import { getSessionGeneration } from "@/lib/auth";
import {
  DRAWER_SEARCH_DEBOUNCE_MS,
  DRAWER_SEARCH_PAGE_SIZE,
  isValidDrawerSearchQuery,
  mergeDrawerSearchResults,
} from "@/features/search/model/drawerSearchLogic";

type Options = { token: string | null; isDrawerOpen: boolean };
type View = { session: number; signedIn: boolean; isDrawerOpen: boolean };
type SearchCycle = {
  view: View;
  open: boolean;
  query: string;
  pending: boolean;
  /** Where the next page starts; the server names it after the last hit read. */
  nextCursor: string | null;
  hasMore: boolean;
  results: SearchResult[];
};
/** One empty list for every keystroke and closed drawer: a fresh `[]` redrew each visible drawer row. */
const NO_RESULTS: SearchResult[] = [];
function emptyCycle(view: View): SearchCycle {
  return { view, open: false, query: "", pending: false, nextCursor: null, hasMore: false, results: [] };
}
function emptySnapshot(cycle: SearchCycle) {
  return { cycle, searchOpen: false, searchQuery: "", searchResults: NO_RESULTS, searchLoading: false, searchError: false, loadingMore: false, loadingMoreError: false, hasMore: false };
}

export function useDrawerSearch({ token, isDrawerOpen }: Options) {
  const session = getSessionGeneration();
  const signedIn = Boolean(token);
  const viewRef = useRef<View>({ session, signedIn, isDrawerOpen });
  if (viewRef.current.session !== session || viewRef.current.signedIn !== signedIn || viewRef.current.isDrawerOpen !== isDrawerOpen) {
    viewRef.current = { session, signedIn, isDrawerOpen };
  }
  const view = viewRef.current;
  const cycleRef = useRef(emptyCycle(view));
  const [snapshot, setSnapshot] = useState(() => emptySnapshot(cycleRef.current));
  const searchInputRef = useRef<TextInput>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const focusFrameRef = useRef<number | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  const tokenRef = useRef(token);
  tokenRef.current = token;

  const currentView = useCallback(() => mountedRef.current && viewRef.current === view && view.session === getSessionGeneration() && view.signedIn && view.isDrawerOpen, [view]);
  const current = useCallback((cycle: SearchCycle) => currentView() && cycleRef.current === cycle && cycle.view === view && cycle.open, [currentView, view]);
  const cancelPending = useCallback(() => {
    if (timerRef.current != null) clearTimeout(timerRef.current);
    timerRef.current = null;
    if (focusFrameRef.current != null) cancelAnimationFrame(focusFrameRef.current);
    focusFrameRef.current = null;
    controllerRef.current?.abort();
    controllerRef.current = null;
  }, []);
  const reset = useCallback(() => {
    cancelPending();
    const cycle = emptyCycle(view);
    cycleRef.current = cycle;
    setSnapshot(emptySnapshot(cycle));
  }, [cancelPending, view]);
  useEffect(() => { reset(); }, [reset]);
  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; cancelPending(); };
  }, [cancelPending]);

  const closeSearch = useCallback(() => {
    if (mountedRef.current && viewRef.current === view && session === getSessionGeneration()) reset();
  }, [view, session, reset]);
  const openSearch = useCallback(() => {
    if (!currentView()) return;
    const cycle = cycleRef.current;
    cycle.open = true;
    setSnapshot((prev) => ({ ...prev, searchOpen: true }));
    if (focusFrameRef.current != null) cancelAnimationFrame(focusFrameRef.current);
    focusFrameRef.current = requestAnimationFrame(() => {
      focusFrameRef.current = null;
      if (current(cycle)) searchInputRef.current?.focus();
    });
  }, [currentView, current]);

  const fetchPage = useCallback(async (cycle: SearchCycle, append: boolean) => {
    const accessToken = tokenRef.current;
    if (!accessToken || !current(cycle) || cycle.pending || !isValidDrawerSearchQuery(cycle.query)) return;
    if (append && !cycle.hasMore) return;
    const cursor = append ? cycle.nextCursor ?? undefined : undefined;
    const controller = new AbortController();
    controllerRef.current = controller;
    cycle.pending = true;
    setSnapshot((prev) => prev.cycle === cycle ? { ...prev, searchLoading: !append, loadingMore: append, searchError: false, loadingMoreError: false } : prev);
    try {
      const data = await api.search(accessToken, cycle.query, DRAWER_SEARCH_PAGE_SIZE, { signal: controller.signal }, cursor);
      if (!current(cycle)) return;
      cycle.results = mergeDrawerSearchResults(append ? cycle.results : [], data.items);
      cycle.nextCursor = data.next_cursor;
      // An empty page or a cursor that did not move ends the list, whatever else it says.
      cycle.hasMore = data.next_cursor !== null && data.items.length > 0 && data.next_cursor !== cursor;
      setSnapshot((prev) => prev.cycle === cycle ? { ...prev, searchResults: cycle.results, hasMore: cycle.hasMore } : prev);
    } catch (error: unknown) {
      if (current(cycle) && !isAbortError(error)) {
        setSnapshot((prev) => prev.cycle === cycle ? { ...prev, searchError: !append, loadingMoreError: append } : prev);
      }
    } finally {
      cycle.pending = false;
      if (current(cycle)) setSnapshot((prev) => prev.cycle === cycle ? { ...prev, searchLoading: false, loadingMore: false } : prev);
      if (controllerRef.current === controller) controllerRef.current = null;
    }
  }, [current]);

  const onSearchChange = useCallback((text: string) => {
    if (!currentView() || !cycleRef.current.open) return;
    cancelPending();
    // Replace ownership now, before debounce, including when the text later repeats.
    const cycle = { ...emptyCycle(view), open: true, query: text.trim() };
    cycleRef.current = cycle;
    const valid = isValidDrawerSearchQuery(cycle.query);
    setSnapshot({ ...emptySnapshot(cycle), searchOpen: true, searchQuery: text, searchLoading: valid });
    if (valid) {
      timerRef.current = setTimeout(() => { timerRef.current = null; void fetchPage(cycle, false); }, DRAWER_SEARCH_DEBOUNCE_MS);
    }
  }, [currentView, cancelPending, view, fetchPage]);

  const renderCycle = snapshot.cycle;
  const isCurrentSearch = useCallback(() => current(renderCycle), [current, renderCycle]);
  const loadMore = useCallback(async () => {
    if (isCurrentSearch()) await fetchPage(renderCycle, true);
  }, [isCurrentSearch, fetchPage, renderCycle]);
  const retrySearch = useCallback(() => {
    if (!isCurrentSearch() || renderCycle.pending || !snapshot.searchError) return;
    cancelPending();
    const cycle = { ...emptyCycle(view), open: true, query: renderCycle.query };
    cycleRef.current = cycle;
    setSnapshot({ ...emptySnapshot(cycle), searchOpen: true, searchQuery: snapshot.searchQuery, searchLoading: true });
    void fetchPage(cycle, false);
  }, [isCurrentSearch, renderCycle, snapshot.searchError, snapshot.searchQuery, cancelPending, view, fetchPage]);

  // A changed account/drawer cannot display its predecessor's snapshot before effects reset it.
  const visible = currentView() && snapshot.cycle.view === view;
  return {
    searchOpen: visible && snapshot.searchOpen,
    searchQuery: visible ? snapshot.searchQuery : "",
    searchResults: visible ? snapshot.searchResults : NO_RESULTS,
    searchLoading: visible && snapshot.searchLoading,
    searchError: visible && snapshot.searchError,
    hasSearchQuery: visible && isValidDrawerSearchQuery(snapshot.searchQuery),
    hasMore: visible && snapshot.hasMore,
    loadingMore: visible && snapshot.loadingMore,
    loadingMoreError: visible && snapshot.loadingMoreError,
    loadMore, retrySearch, isCurrentSearch,
    searchInputRef: searchInputRef as RefObject<TextInput>,
    openSearch, closeSearch, onSearchChange,
  };
}
