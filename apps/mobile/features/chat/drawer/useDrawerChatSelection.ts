import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { Chat } from "@/lib/api";
import { getSessionGeneration } from "@/lib/auth";
import { useViewOwner } from "@/features/chat/hooks/useViewOwner";
import {
  clearChatSelection,
  selectAllChatIds,
  toggleChatSelection,
} from "@/features/chat/drawer/drawerChatSelection";

type Params = {
  token: string | null;
  isDrawerOpen: boolean;
  listedChats: Chat[];
  /** What "Select all" picks: the chats on screen (``selectableChats``). */
  selectableChats: Chat[];
};

export function useDrawerChatSelection({ token, isDrawerOpen, listedChats, selectableChats }: Params) {
  const session = getSessionGeneration();
  const signedIn = Boolean(token);
  const { view, owns } = useViewOwner(`${session}:${signedIn}:${isDrawerOpen}`);
  const currentView = useCallback(
    () => owns() && signedIn && isDrawerOpen && session === getSessionGeneration(),
    [owns, signedIn, isDrawerOpen, session],
  );
  const [selectionMode, setSelectionMode] = useState(false);
  const [requestedIds, setRequestedIds] = useState<Set<string>>(() => new Set());
  // Each enter, exit and new view starts a new selection; a callback from an older one does nothing.
  const selectionVersion = useRef(0);
  const [version, setVersion] = useState(0);
  const nextSelection = useCallback(() => {
    selectionVersion.current += 1;
    setVersion(selectionVersion.current);
  }, []);

  useEffect(() => {
    nextSelection();
    setSelectionMode(false);
    setRequestedIds(clearChatSelection());
  }, [view, nextSelection]);

  // Preserve intent through optimistic removal, so failed rows regain their
  // checkmark on rollback. Missing rows never inflate the actionable count.
  const selectedIds = useMemo(() => new Set(
    listedChats.filter((chat) => requestedIds.has(chat.id)).map((chat) => chat.id),
  ), [listedChats, requestedIds]);

  const enterSelectionMode = useCallback((initialChatId?: string) => {
    if (!currentView()) return;
    nextSelection();
    setSelectionMode(true);
    setRequestedIds(initialChatId ? new Set([initialChatId]) : clearChatSelection());
  }, [currentView, nextSelection]);

  const exitSelectionMode = useCallback(() => {
    if (!currentView() || version !== selectionVersion.current) return;
    nextSelection();
    setSelectionMode(false);
    setRequestedIds(clearChatSelection());
  }, [currentView, version, nextSelection]);

  const toggleSelected = useCallback((chatId: string) => {
    if (!currentView() || !selectionMode || version !== selectionVersion.current) return;
    setRequestedIds((prev) => toggleChatSelection(prev, chatId));
  }, [currentView, selectionMode, version]);

  const selectAllListed = useCallback(() => {
    if (!currentView() || !selectionMode || version !== selectionVersion.current) return;
    setRequestedIds(selectAllChatIds(selectableChats));
  }, [currentView, selectionMode, version, selectableChats]);

  return {
    selectionMode,
    selectedIds,
    selectedCount: selectedIds.size,
    enterSelectionMode,
    exitSelectionMode,
    toggleSelected,
    selectAllListed,
  };
}
