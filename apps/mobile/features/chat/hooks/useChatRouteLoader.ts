import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { AppStateStatus } from "react-native";
import type { FlashListRef } from "@shopify/flash-list";
import type { useRouter } from "expo-router";

import type { IconName } from "@/ui/icons/names";

import { useComposerDraftApiOptional } from "@/features/chat/context/ComposerDraftContext";
import { api, type Chat, type Message } from "@/lib/api";
import { ApiRequestError } from "@/lib/api/client";
import { getSessionGeneration } from "@/lib/auth";
import { reportFailure } from "@/lib/sentry";
import { getCachedChat, getFetchedChat } from "@/features/chat/model/chatListCache";
import { onAppStateChange } from "@/lib/foregroundRefresh";
import { shouldForceForegroundChatRecovery, shouldRefetchChatOnForeground } from "@/features/chat/model/foregroundRefetch";
import {
  cachedChatPageFetchedAt,
  clearCachedChatMessages,
  isCachedChatPageFresh,
  markCachedChatPagesStale,
  peekCachedChatPage,
  readCachedChatMessages,
  shouldSkipChatPageRead,
  type CachedChatPage,
} from "@/features/chat/model/messageCache";
import { mergeLocalAttachmentUris, mergeOpenedPage, paintCachedThread, addedSincePaint } from "@/features/chat/model/messageMerge";
import { MESSAGE_PAGE_SIZE } from "@/features/chat/model/constants";
import { noteChatPageRead } from "@/features/chat/model/pageReads";
import { beginOpenedPageRead, type OpenedPageRead } from "@/features/chat/model/openedPage";
import {
  chatHasThreadContent,
  markChatHasAssistant,
  shouldDiscardOnNewChat,
  shouldProbeEmptyChat,
  shouldProbePreviousChat,
} from "@/features/chat/model/draftLogic";
import { shouldInsertDrawerRowOnLeave } from "@/features/chat/model/titleRefresh";
import { getChatMutationRevision, removeChatGlobal, subscribeChatChanges } from "@/features/chat/drawer/drawer";
import type { useDraftChat } from "@/features/chat/hooks/useDraftChat";
import { useChatHighlightScroll } from "@/features/chat/hooks/useChatHighlightScroll";
import { useChatPaging } from "@/features/chat/hooks/useChatPaging";
import { useChatPageCacheWriter, type ChatPageSync } from "@/features/chat/hooks/useChatPageCacheWriter";
import { useChatPageReconnect } from "@/features/chat/hooks/useChatPageReconnect";
import { useChatTitlePolling } from "@/features/chat/hooks/useChatTitlePolling";
import { useLatestRef } from "@/lib/latestRef";
import { useViewOwner } from "@/features/chat/hooks/useViewOwner";
import type { EditThread } from "@/features/chat/model/threadEdit";

type Router = ReturnType<typeof useRouter>;
type DraftChat = ReturnType<typeof useDraftChat>;

type Options = {
  token: string | null;
  routeChatId: string | undefined;
  routeHighlightMessage: string | undefined;
  router: Router;
  draft: DraftChat;
  chatId: string | null;
  setChatId: React.Dispatch<React.SetStateAction<string | null>>;
  /** Changes the thread on screen; useChat owns it. */
  editThread: EditThread;
  messages: Message[];
  streaming: boolean;
  /** Latest image-gen in-flight flag — AppState/focus closures must not snapshot it. */
  imageGeneratingRef?: React.MutableRefObject<boolean>;
  stopGeneration: () => void;
  listRef: React.RefObject<FlashListRef<Message> | null>;
  showActionBanner: (message: string, icon?: IconName) => void;
  t: (key: string) => string;
};

export function useChatRouteLoader({
  token,
  routeChatId,
  routeHighlightMessage,
  router,
  draft,
  chatId,
  setChatId,
  editThread,
  messages,
  streaming,
  imageGeneratingRef,
  stopGeneration,
  listRef,
  showActionBanner,
  t,
}: Options) {
  const {
    draftChatIdRef,
    skipLoadForChatIdRef,
    creatingRef,
    discardEmptyChat,
    clearDraftChat,
  } = draft;

  const messagesRef = useLatestRef(messages);
  const getFirstUserText = useCallback(() => {
    const user = messagesRef.current.find((m) => m.role === "user");
    if (!user) return undefined;
    if (user.content?.trim()) return user.content;
    if (user.local_image_uri) return "[Image: local]";
    if (user.local_file_name || user.local_file_uri) {
      return `[File: ${user.local_file_name ?? "file"}]`;
    }
    return user.content;
  }, [messagesRef]);
  const [chatTitle, setChatTitle] = useState<string | null>(null);
  const { titleGenerating, pollForTitle, handleFirstReply } = useChatTitlePolling({
    token,
    chatId,
    setChatTitle,
    getFirstUserText,
  });
  const [pinned, setPinned] = useState(false);
  const [archived, setArchived] = useState(false);
  const [chatLoading, setChatLoading] = useState(false);
  const [hasMoreOlder, setHasMoreOlder] = useState(false);
  const [pageSync, setPageSync] = useState<ChatPageSync | null>(null);
  const composer = useComposerDraftApiOptional();
  const session = getSessionGeneration();
  const signedIn = Boolean(token);
  // Bumped by each new route or account, New chat and unmount: a read from before lands nowhere.
  const viewRef = useRef({ version: 0 });
  useLayoutEffect(() => {
    viewRef.current.version += 1;
  }, [session, routeChatId]);
  const { owns } = useViewOwner(`${session}:${routeChatId}`);
  const activeChatRef = useLatestRef(chatId);
  useEffect(() => subscribeChatChanges((id, patch) => {
    if (session !== getSessionGeneration() || id !== activeChatRef.current || !patch) return;
    if (patch.title !== undefined) setChatTitle(patch.title);
    if (patch.pinned !== undefined) setPinned(patch.pinned);
    if (patch.archived !== undefined) setArchived(Boolean(patch.archived));
  }), [session, activeChatRef]);

  const applyMetadata = useCallback((chat: Chat | undefined) => {
    if (!chat) return;
    setChatTitle(chat.title);
    setPinned(chat.pinned);
    setArchived(Boolean(chat.archived));
  }, []);
  const paging = useChatPaging({ token, chatId, chatLoading, messages, editThread, hasMoreOlder, setHasMoreOlder,
    viewRef, activeChatRef, showActionBanner, t });
  const { resetPaging, hasMoreNewer } = paging;
  useEffect(() => () => {
    viewRef.current.version += 1;
  }, []);

  const priorRouteChatIdRef = useRef<string | null>(null);
  const wasStreamingWhenBackgroundedRef = useRef(false);
  // AppState closures must read the latest streaming/loading flags — deps alone
  // would leave a stale "still streaming" view after ws.onclose commits a partial.
  const streamingRef = useLatestRef(streaming);
  const chatLoadingRef = useLatestRef(chatLoading);
  const knownAssistantChatId = chatId ?? (typeof routeChatId === "string" ? routeChatId : null);
  const messagesHadContent = chatHasThreadContent(messages);
  useEffect(() => {
    if (knownAssistantChatId && messagesHadContent) {
      markChatHasAssistant(knownAssistantChatId);
    }
  }, [knownAssistantChatId, messagesHadContent]);

  const turnBusy = useCallback(
    () => streamingRef.current || Boolean(imageGeneratingRef?.current),
    [imageGeneratingRef, streamingRef],
  );

  const leaveOpenChat = useCallback(
    (opts?: { force?: boolean }) => {
      // Stop only when the open chat is being deleted. New chat / Home launch
      // must leave the in-flight reply running so it can finish in the background.
      if (opts?.force && turnBusy()) stopGeneration();
      const leavingMessages = messagesRef.current;
      if (!opts?.force && shouldInsertDrawerRowOnLeave(leavingMessages)) {
        void handleFirstReply();
      }
      if (
        shouldDiscardOnNewChat(routeChatId) &&
        shouldProbeEmptyChat(chatHasThreadContent(leavingMessages))
      ) {
        discardEmptyChat(chatId);
      }
      clearDraftChat();
    },
    [
      stopGeneration,
      turnBusy,
      handleFirstReply,
      routeChatId,
      discardEmptyChat,
      chatId,
      clearDraftChat,
      messagesRef,
    ],
  );

  const startNewChat = useCallback(
    (_opts?: { force?: boolean }) => {
      viewRef.current.version++;
      resetPaging();
      leaveOpenChat(_opts);
      setChatId(null);
      setChatTitle(null);
      setPinned(false);
      setArchived(false);
      editThread([], "view_cleared");
      setHasMoreOlder(false);
      setChatLoading(false);
      if (routeChatId != null) {
        router.setParams({ chatId: undefined });
      }
    },
    [
      leaveOpenChat,
      resetPaging,
      routeChatId,
      router,
      editThread,
      setChatId,
    ],
  );

  const silentRefetchChat = useCallback(
    async (openChatId: string, cancelled: () => boolean, opts?: { force?: boolean }) => {
      if (!token || session !== getSessionGeneration() || !owns() ||
          openChatId !== activeChatRef.current || hasMoreNewer) return;
      const version = viewRef.current.version;
      const ownerSession = getSessionGeneration();
      const previousMessages = messagesRef.current;
      const stale = () =>
        cancelled() || ownerSession !== getSessionGeneration() || version !== viewRef.current.version ||
        turnBusy() || messagesRef.current !== previousMessages;
      if (await shouldSkipChatPageRead(openChatId, opts?.force)) return;
      if (stale()) return;
      try {
        const revision = getChatMutationRevision(openChatId);
        const [chat, page] = await Promise.all([
          getFetchedChat(openChatId) ?? api.getChat(token, openChatId),
          api.listMessages(token, openChatId, { limit: MESSAGE_PAGE_SIZE }),
        ]);
        if (stale()) return;
        setChatId(chat.id);
        applyMetadata(revision === getChatMutationRevision(openChatId) ? chat : getCachedChat(openChatId));
        editThread((prev) => mergeLocalAttachmentUris(prev, page.messages), "page_refresh");
        setHasMoreOlder(page.has_more);
        const fetchedAt = Date.now();
        noteChatPageRead(openChatId, fetchedAt);
        setPageSync({ chatId: openChatId, fetchedAt });
      } catch (error) {
        reportFailure("chat_refresh", error); // The messages on screen stay.
      }
    },
    [token, session, owns, activeChatRef, messagesRef, setChatId, editThread, applyMetadata, turnBusy, hasMoreNewer],
  );

  useEffect(() => {
    let cancelled = false;
    const onAppState = (state: AppStateStatus, returned: boolean) => {
      if (session !== getSessionGeneration()) return;
      if (state === "background" || state === "inactive") {
        // Another device may write to any chat while this one is away.
        if (state === "background") markCachedChatPagesStale();
        if (streamingRef.current || Boolean(imageGeneratingRef?.current)) {
          wasStreamingWhenBackgroundedRef.current = true;
        }
        // An unused draft is dropped by useDraftChat, once, on background.
        return;
      }
      // An iOS "inactive" blip (Control Centre, a prompt) left the socket and the page as they were.
      if (!returned) return;
      // Backgrounding mid-stream kills the socket; onclose commits a truncated
      // bubble. When we return to foreground with streaming finished, pull the
      // server's full reply without requiring the user to leave the chat.
      const openChatId =
        (typeof routeChatId === "string" ? routeChatId : null) ?? chatId;
      if (
        !openChatId ||
        !shouldRefetchChatOnForeground({
          appState: state,
          token,
          chatId: openChatId,
          streaming: streamingRef.current,
          chatLoading: chatLoadingRef.current,
          imageGenerating: Boolean(imageGeneratingRef?.current),
        })
      ) {
        return;
      }
      const force = shouldForceForegroundChatRecovery({
        wasStreamingWhenBackgrounded: wasStreamingWhenBackgroundedRef.current,
      });
      wasStreamingWhenBackgroundedRef.current = false;
      void silentRefetchChat(openChatId, () => cancelled, { force });
    };
    const stopAppState = onAppStateChange(onAppState);
    return () => {
      cancelled = true;
      stopAppState();
    };
  }, [
    messages.length,
    chatId,
    routeChatId,
    token,
    discardEmptyChat,
    clearDraftChat,
    draftChatIdRef,
    silentRefetchChat,
    session,
    imageGeneratingRef,
    chatLoadingRef,
    streamingRef,
  ]);

  useEffect(() => {
    resetPaging();
    setPageSync(null);
    if (!token) {
      setChatLoading(false);
      return;
    }
    const openChatId = typeof routeChatId === "string" ? routeChatId : null;
    const prevOpenChatId = priorRouteChatIdRef.current;
    if (prevOpenChatId && prevOpenChatId !== openChatId) {
      if (
        shouldProbePreviousChat({
          chatId: prevOpenChatId,
          messagesHadAssistant: chatHasThreadContent(messagesRef.current),
        })
      ) {
        discardEmptyChat(prevOpenChatId);
      }
    }
    if (openChatId && draftChatIdRef.current) {
      clearDraftChat();
    }
    priorRouteChatIdRef.current = openChatId;

    let cancelled = false;
    let opened: OpenedPageRead | null = null;
    const version = viewRef.current.version;
    const isCurrent = () => !cancelled && session === getSessionGeneration() && version === viewRef.current.version;
    (async () => {
      if (!openChatId) {
        setChatLoading(false);
        if (!creatingRef.current) {
          setChatId(null);
          setChatTitle(null);
          setPinned(false);
          setArchived(false);
          editThread([], "view_cleared");
          setHasMoreOlder(false);
        }
        return;
      }
      if (skipLoadForChatIdRef.current === openChatId) {
        skipLoadForChatIdRef.current = null;
        setChatId(openChatId);
        setChatLoading(false);
        // The chat this view just created holds nothing but what it shows.
        noteChatPageRead(openChatId);
        setPageSync({ chatId: openChatId, fetchedAt: Date.now() });
        return;
      }
      const showCachedPage = (cached: CachedChatPage | null, listed = getCachedChat(openChatId)) => {
        setChatId(openChatId);
        editThread((prev) => paintCachedThread(prev, cached?.messages ?? []), "cached_paint");
        setChatTitle(null);
        setPinned(false);
        setArchived(false);
        if (cached) {
          setHasMoreOlder(cached.has_more);
          if (listed) applyMetadata(listed);
        }
      };
      const kept = peekCachedChatPage(openChatId);
      const listed = getFetchedChat(openChatId);
      if (kept && listed && isCachedChatPageFresh(openChatId, listed.updated_at)) {
        // This device wrote the page moments ago and nothing suggests the chat moved on.
        showCachedPage(kept, listed);
        const fetchedAt = cachedChatPageFetchedAt(kept) ?? Date.now();
        noteChatPageRead(openChatId, fetchedAt);
        setPageSync({ chatId: openChatId, fetchedAt });
        setChatLoading(false);
        if (!listed.title && kept.messages.length > 0) pollForTitle(token, openChatId);
        return;
      }
      setChatLoading(true);
      setHasMoreOlder(false);
      // Send works once the cached page is painted; a turn sent before the page lands waits for it.
      const read = beginOpenedPageRead(openChatId);
      opened = read;
      try {
        // Stale-while-revalidate: keep the previous thread painted during the
        // (fast) cache read, then swap in one shot — no blank flash on open.
        // The old thread's pending work still cannot paint into this route
        // because every set below is guarded by isCurrent().
        const cached = kept ?? await readCachedChatMessages(openChatId);
        if (!isCurrent()) return;
        showCachedPage(cached);
        const painted = new Set(cached?.messages.map((m) => m.id));
        const revision = getChatMutationRevision(openChatId);
        const [chat, page] = await Promise.all([
          getFetchedChat(openChatId) ?? api.getChat(token, openChatId),
          api.listMessages(token, openChatId, { limit: MESSAGE_PAGE_SIZE }),
        ]);
        if (!isCurrent()) return;
        setChatId(chat.id);
        const currentChat = revision === getChatMutationRevision(openChatId) ? chat : getCachedChat(openChatId);
        applyMetadata(currentChat);
        // A turn that went out before the page may be in it: merge once nothing of it is on screen, else reread later.
        if (read.release() || !addedSincePaint(messagesRef.current, page.messages, painted)) {
          editThread((prev) => mergeOpenedPage(prev, page.messages, painted), "opened_page");
          setHasMoreOlder(page.has_more);
          const fetchedAt = Date.now();
          noteChatPageRead(openChatId, fetchedAt);
          setPageSync({ chatId: openChatId, fetchedAt });
        } else setPageSync({ chatId: openChatId, fetchedAt: null });
        if (currentChat && !currentChat.title && page.messages.length > 0) {
          pollForTitle(token, openChatId);
        }
      } catch (error) {
        if (isCurrent()) {
          if (error instanceof ApiRequestError && error.status === 404) {
            read.chatGone(composer);
            removeChatGlobal(openChatId);
            void clearCachedChatMessages(openChatId);
            startNewChat({ force: true });
          } else reportFailure("chat_load", error);
          showActionBanner(t("common.error"), "alert-circle");
        }
      } finally {
        // A read that failed lets a turn waiting for it go out.
        if (isCurrent()) read.release();
        if (isCurrent()) setChatLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      // Left before the page landed: a turn waiting for it goes back to this chat's composer (not past sign-out).
      opened?.cancel(session === getSessionGeneration() ? composer : null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload for a new route chat or account, not a rotated token or a recreated callback
  }, [signedIn, session, routeChatId]);

  useChatPageCacheWriter({
    chatId, routeChatId, messages, busy: streaming, hasMoreOlder, hasMoreNewer, sync: pageSync,
    resync: silentRefetchChat,
  });
  useChatPageReconnect({ chatId, busy: () => chatLoadingRef.current || turnBusy(), refetch: silentRefetchChat });

  const { highlightedMessageId } = useChatHighlightScroll({
    chatLoading, routeChatId, routeHighlightMessage, router, messages, hasMoreOlder, hasMoreNewer,
    token, chatId, openAround: paging.openAround, listRef,
  });

  return {
    chatTitle,
    setChatTitle,
    titleGenerating,
    pinned,
    setPinned,
    archived,
    setArchived,
    chatLoading,
    // Send waits only while nothing of the routed chat is on screen.
    historyPending: chatLoading && (messages.length === 0 || chatId !== (routeChatId ?? null)),
    hasMoreOlder,
    loadingOlder: paging.loadingOlder,
    loadOlderMessages: paging.loadOlderMessages,
    newerPage: paging.newerPage,
    jumpToLatest: paging.jumpToLatest,
    highlightedMessageId,
    handleFirstReply,
    startNewChat,
    pollForTitle,
  };
}
