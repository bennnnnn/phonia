import { useAccountSession } from "@/contexts/accountSession";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import {
  activeChatsFromGroups,
  ARCHIVED_CHAT_SECTION,
  CHAT_DATE_SECTIONS,
  defaultChatSectionCollapsed,
  isCollapsibleChatSection,
  patchChatListGroups,
  removeChatFromGroups,
  type ChatListSectionKey,
} from "@/features/chat/model/listSections";
import {
  fetchChatList,
  fetchMoreArchivedChats,
  fetchOlderChats,
  getCachedChatList,
  getChatListFetchedAt,
  isChatListFresh,
  regroupCachedChatList,
  restoreChatList,
  updateChatListCache,
} from "@/features/chat/model/chatListCache";
import {
  publishChatChange,
  registerChatInserter,
  registerChatPatcher,
  registerChatRemover,
  subscribeChatTitleGenerating,
} from "@/features/chat/drawer/drawer";
import {
  drawerChatFetchMode,
  emptyChatList,
  insertChatIntoGroups,
  shouldWarmClosedDrawerChatList,
} from "@/features/chat/drawer/drawerChatList";
import { Chat, ChatList } from "@/lib/api";
import { getSessionGeneration } from "@/lib/auth";
import { isExpectedReadFailure } from "@/lib/cache/sessionResource";
import { scheduleIdleTask } from "@/lib/scheduleIdle";
import { useReadFailureReport } from "@/hooks/useReadFailureReport";
import { useReconnectRefresh } from "@/hooks/useReconnectRefresh";
import { useLatestRef } from "@/lib/latestRef";

type Params = { isDrawerOpen: boolean };

function initialCollapsedSections(): Record<string, boolean> {
  return Object.fromEntries([...CHAT_DATE_SECTIONS, ARCHIVED_CHAT_SECTION]
    .map((key) => [key, defaultChatSectionCollapsed(key)]));
}

/** The drawer's chats, kept per account: the hourly token rotation reads nothing (NET-11). */
export function useDrawerChatList({ isDrawerOpen }: Params) {
  const { account, getToken } = useAccountSession();
  const session = getSessionGeneration();
  const [snapshot, setSnapshot] = useState(() => ({ session, groups: emptyChatList() }));
  const groups = useMemo(() => snapshot.session === session && account ? snapshot.groups : emptyChatList(), [snapshot, session, account]);
  const [loading, setLoading] = useState(false);
  const [collapsedSections, setCollapsedSections] = useState(initialCollapsedSections);
  const [error, setError] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const hasLoadedOnceRef = useRef(false);
  const mountedRef = useRef(true);
  const loadIdRef = useRef(0);
  const [, setTitlePendingTick] = useState(0);
  const reportFailure = useReadFailureReport();
  // Another account starts unloaded, and a load the last one started lands nowhere.
  useLayoutEffect(() => {
    hasLoadedOnceRef.current = false;
    loadIdRef.current++;
  }, [session]);
  const current = useCallback(() => mountedRef.current && session === getSessionGeneration(), [session]);
  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);
  useEffect(() => {
    setLoading(false);
    setRefreshing(false);
    setError(false);
    setCollapsedSections(initialCollapsedSections());
  }, [session]);

  const allChats = useMemo(() => activeChatsFromGroups(groups), [groups]);
  const isSectionCollapsed = useCallback((key: ChatListSectionKey) =>
    isCollapsibleChatSection(key) && (collapsedSections[key] ?? defaultChatSectionCollapsed(key)), [collapsedSections]);
  const toggleSectionCollapsed = useCallback((key: ChatListSectionKey) => {
    if (!isCollapsibleChatSection(key)) return;
    setCollapsedSections((prev) => ({ ...prev, [key]: !(prev[key] ?? defaultChatSectionCollapsed(key)) }));
  }, []);

  const applyChatList = useCallback((data: ChatList, fetched = true) => {
    if (!current()) return;
    setSnapshot((prev) => prev.session === session && prev.groups === data ? prev : { session, groups: data });
    if (fetched) hasLoadedOnceRef.current = true;
  }, [current, session]);
  const hydrateFromCache = useCallback(() => {
    if (!account || !current()) return false;
    // Under today's headings: a list from disk or from before midnight moves its chats.
    const cached = regroupCachedChatList();
    if (!cached) return false;
    const fetched = getChatListFetchedAt() != null;
    applyChatList(cached, fetched);
    return fetched;
  }, [account, current, applyChatList]);

  const load = useCallback(async (background = false, force = false) => {
    const token = getToken();
    if (!account || !token || !current()) return;
    if (!force && isChatListFresh() && hydrateFromCache()) return;
    const loadId = ++loadIdRef.current;
    if (!background) setLoading(true);
    setError(false);
    const result = await fetchChatList(token, { force, report: reportFailure });
    if (!current() || loadId !== loadIdRef.current) return;
    // A failed read hands back the list already shown (one restored from disk, say): not loaded yet.
    if (result.data) applyChatList(getCachedChatList() ?? result.data, !result.error);
    if (result.error && !background) setError(true);
    if (!background) setLoading(false);
  }, [account, getToken, current, hydrateFromCache, applyChatList, reportFailure]);

  const olderInFlightRef = useRef(false);
  /** The next page of older dated chats, when the list's end comes into view (CLAR-12). */
  const loadOlderChats = useCallback(async () => {
    const token = getToken();
    if (!account || !token || !current() || olderInFlightRef.current) return;
    olderInFlightRef.current = true;
    try {
      const grown = await fetchOlderChats(token);
      if (grown && current()) applyChatList(grown, false);
    } catch (caught) {
      // The rows shown stay; the next scroll to the end tries again.
      const error = caught instanceof Error ? caught : new Error(String(caught));
      if (current() && !isExpectedReadFailure(error)) reportFailure(error);
    } finally {
      olderInFlightRef.current = false;
    }
  }, [account, getToken, current, applyChatList, reportFailure]);

  const [archivedPaging, setArchivedPaging] = useState<"idle" | "loading" | "failed">("idle");
  /** The next page of archived chats, from the archived section's "Show more" row. */
  const loadMoreArchivedChats = useCallback(async () => {
    const token = getToken();
    if (!account || !token || !current()) return;
    setArchivedPaging("loading");
    try {
      const grown = await fetchMoreArchivedChats(token);
      if (grown && current()) applyChatList(grown, false);
      if (current()) setArchivedPaging("idle");
    } catch (caught) {
      const error = caught instanceof Error ? caught : new Error(String(caught));
      if (!current()) return;
      setArchivedPaging("failed");
      if (!isExpectedReadFailure(error)) reportFailure(error);
    }
  }, [account, getToken, current, applyChatList, reportFailure]);

  const handleRefresh = useCallback(async () => {
    if (!account || !current()) return;
    setRefreshing(true);
    try { await load(false, true); }
    finally { if (current()) setRefreshing(false); }
  }, [account, current, load]);

  // A cold start paints the chats this account had last time while the list is read again.
  useEffect(() => {
    const token = getToken();
    if (!account || !token) return;
    let cancelled = false;
    void restoreChatList(token).then((restored) => {
      if (restored && !cancelled && current()) hydrateFromCache();
    });
    return () => { cancelled = true; };
  }, [account, getToken, current, hydrateFromCache]);

  // Idle warm is only for first paint. Closing the drawer never triggers a read.
  useEffect(() => {
    hydrateFromCache();
    if (!shouldWarmClosedDrawerChatList({ hasToken: Boolean(account), isDrawerOpen, hasLoadedOnce: hasLoadedOnceRef.current })) return;
    const token = getToken();
    if (!token) return;
    let cancelled = false;
    const cancelIdle = scheduleIdleTask(() => {
      if (cancelled || !current()) return;
      void fetchChatList(token).then(({ data, error }) => {
        if (!cancelled && current() && data) applyChatList(getCachedChatList() ?? data, !error);
      });
    });
    return () => { cancelled = true; cancelIdle(); };
  }, [account, getToken, isDrawerOpen, current, hydrateFromCache, applyChatList]);

  useEffect(() => {
    hydrateFromCache();
    if (drawerChatFetchMode({ isDrawerOpen, hasToken: Boolean(account), hasLoadedOnce: hasLoadedOnceRef.current }) !== "skip") void load();
  }, [isDrawerOpen, account, load, hydrateFromCache]);
  // The API back after an outage: the open drawer's chats, read as opening it reads them.
  const openRef = useLatestRef(isDrawerOpen);
  useReconnectRefresh(() => void load(), { onScreen: () => openRef.current, readAt: getChatListFetchedAt });

  const updateGroups = useCallback((chatId: string, patch: Partial<Chat> | null, update: (previous: ChatList) => ChatList) => {
    if (!account || !current()) return;
    applyChatList(updateChatListCache(update), false);
    publishChatChange(chatId, patch);
  }, [account, current, applyChatList]);
  const patchChatInGroups = useCallback((chatId: string, patch: Partial<Chat>) => {
    const normalized = patch.archived === true ? { ...patch, pinned: false } : patch;
    updateGroups(chatId, normalized, (prev) => patchChatListGroups(prev, chatId, normalized));
  }, [updateGroups]);
  const insertChatInGroups = useCallback((chat: Chat) => {
    updateGroups(chat.id, chat, (prev) => insertChatIntoGroups(prev, chat));
  }, [updateGroups]);
  const removeChatFromGroupsById = useCallback((chatId: string) => {
    updateGroups(chatId, null, (prev) => removeChatFromGroups(prev, chatId));
  }, [updateGroups]);
  const moveChatArchiveState = useCallback((chatId: string, archived: boolean) => {
    patchChatInGroups(chatId, archived ? { archived, pinned: false } : { archived });
  }, [patchChatInGroups]);

  useEffect(() => {
    const unregisters = [
      registerChatPatcher(patchChatInGroups),
      registerChatInserter(insertChatInGroups),
      registerChatRemover(removeChatFromGroupsById),
    ];
    return () => unregisters.forEach((unregister) => unregister());
  }, [patchChatInGroups, insertChatInGroups, removeChatFromGroupsById]);
  useEffect(() => subscribeChatTitleGenerating(() => setTitlePendingTick((n) => n + 1)), []);

  return {
    loading, error, refreshing, groups, allChats, load, handleRefresh,
    hasOlderChats: Boolean(groups.next_cursor), loadOlderChats,
    hasMoreArchived: Boolean(groups.archived_next_cursor), loadMoreArchivedChats, archivedPaging,
    patchChatInGroups, insertChatInGroups, isSectionCollapsed, toggleSectionCollapsed,
    moveChatArchiveState, removeChatFromGroupsById,
  };
}
