import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FlashListRef } from "@shopify/flash-list";
import { useRouter } from "expo-router";

import type { Message } from "@/lib/api";
import { getSessionGeneration } from "@/lib/auth";
import { useLatestRef } from "@/lib/latestRef";
import { registerChatHighlightClearer } from "@/features/chat/drawer/drawer";

type Router = ReturnType<typeof useRouter>;
type ViewOwner = { session: number; chatId: string | null };
type HighlightRequest = { owner: ViewOwner; id: string; loading?: boolean; windowed?: boolean };
type Options = {
  routeChatId?: string;
  routeHighlightMessage: string | undefined;
  router: Router;
  messages: Message[];
  hasMoreOlder: boolean;
  hasMoreNewer: boolean;
  chatLoading?: boolean;
  token: string | null;
  chatId: string | null;
  /** Show the window of messages around one; false when it could not be read. */
  openAround: (messageId: string) => Promise<boolean>;
  listRef: React.RefObject<FlashListRef<Message> | null>;
};
const HIGHLIGHT_MS = 3500;

/**
 * Bring a selected search hit into view and highlight it. A hit beyond the loaded
 * thread opens the window around it in one read; it was paged toward 40 messages
 * at a time (code-health audit NET-18).
 */
export function useChatHighlightScroll({
  routeChatId, routeHighlightMessage, router, messages, hasMoreOlder, hasMoreNewer, chatLoading = false,
  token, chatId, openAround, listRef,
}: Options) {
  const session = getSessionGeneration();
  const destination = routeChatId ?? chatId;
  // A new owner for each chat and account: a request from another one does nothing.
  const owner = useMemo<ViewOwner>(() => ({ session, chatId: destination }), [session, destination]);
  const ownerRef = useLatestRef(owner);
  const latest = useLatestRef({ messages, chatId, token });
  const mounted = useRef(true);
  const pending = useRef<HighlightRequest | null>(null);
  const [highlight, setHighlight] = useState<HighlightRequest | null>(null);
  const frame = useRef<number | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancelScheduled = useCallback(() => {
    if (frame.current != null) cancelAnimationFrame(frame.current);
    if (timer.current != null) clearTimeout(timer.current);
    frame.current = null;
    timer.current = null;
  }, []);
  const current = useCallback(() => mounted.current && ownerRef.current === owner &&
    session === getSessionGeneration() && Boolean(latest.current.token), [owner, session, ownerRef, latest]);

  const clearHighlight = useCallback(() => {
    pending.current = null;
    cancelScheduled();
    setHighlight(null);
  }, [cancelScheduled]);
  useEffect(() => registerChatHighlightClearer(clearHighlight), [clearHighlight]);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; pending.current = null; cancelScheduled(); };
  }, [cancelScheduled]);
  useEffect(() => {
    clearHighlight();
  }, [owner, clearHighlight]);
  useEffect(() => {
    if (!routeHighlightMessage || !owner.chatId || !current()) return;
    cancelScheduled();
    const request = { owner, id: routeHighlightMessage };
    pending.current = request;
    setHighlight(request);
    router.setParams({ highlightMessage: undefined });
  }, [routeHighlightMessage, owner, current, router, cancelScheduled]);

  useEffect(() => {
    const request = pending.current;
    if (!request || request.owner !== owner || !current() || chatId !== owner.chatId || messages.length === 0) return;
    const index = messages.findIndex((message) => message.id === request.id);
    if (index >= 0) {
      if (frame.current != null) return;
      frame.current = requestAnimationFrame(() => {
        frame.current = null;
        if (!current() || pending.current !== request || latest.current.chatId !== owner.chatId) return;
        // Another page may have prepended rows since this frame was scheduled.
        const latestIndex = latest.current.messages.findIndex((message) => message.id === request.id);
        if (latestIndex < 0) return;
        listRef.current?.scrollToIndex({ index: latestIndex, animated: true, viewPosition: 0.5 });
        pending.current = null;
        timer.current = setTimeout(() => {
          timer.current = null;
          if (current()) setHighlight((value) => value === request ? null : value);
        }, HIGHLIGHT_MS);
      });
      return;
    }
    // Not in the loaded thread: read the window around it, once.
    if (request.loading || chatLoading) return;
    if (request.windowed) {
      pending.current = null;
      return;
    }
    if (!hasMoreOlder && !hasMoreNewer) return;
    request.loading = true;
    void openAround(request.id).then((shown) => {
      request.loading = false;
      request.windowed = true;
      if (shown || pending.current !== request) return;
      pending.current = null;
      if (current()) setHighlight((value) => (value === request ? null : value));
    });
  }, [owner, current, chatId, messages, hasMoreOlder, hasMoreNewer, chatLoading, openAround, listRef, latest]);

  return { highlightedMessageId: highlight?.owner === owner && token ? highlight.id : null };
}
