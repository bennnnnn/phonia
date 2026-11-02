import {
  useCallback,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type MutableRefObject,
  type SetStateAction,
} from "react";

import type { IconName } from "@/ui/icons/names";
import { api, type Message } from "@/lib/api";
import { getSessionGeneration } from "@/lib/auth";
import { reportFailure } from "@/lib/sentry";
import { MESSAGE_PAGE_SIZE } from "@/features/chat/model/constants";
import { writeCachedChatMessages } from "@/features/chat/model/messageCache";
import { mergeLocalAttachmentUris } from "@/features/chat/model/messageMerge";
import type { EditThread } from "@/features/chat/model/threadEdit";

const SERVER_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type Options = {
  token: string | null;
  chatId: string | null;
  chatLoading: boolean;
  messages: Message[];
  editThread: EditThread;
  hasMoreOlder: boolean;
  setHasMoreOlder: Dispatch<SetStateAction<boolean>>;
  /** The route loader's view: a read that finishes after it moved on is dropped. */
  viewRef: MutableRefObject<{ version: number }>;
  activeChatRef: MutableRefObject<string | null>;
  showActionBanner: (message: string, icon?: IconName) => void;
  t: (key: string) => string;
};

/** A page that could not be read: Sentry hears of it, and the view that asked, still open, says so. */
function pageReadFailed(error: unknown, shown: boolean, { showActionBanner, t }: Pick<Options, "showActionBanner" | "t">) {
  reportFailure("chat_page", error);
  if (shown) showActionBanner(t("common.error"), "alert-circle");
}

/**
 * Paging within the open chat: older pages above the thread and, after a jump to a
 * search hit deep in it, a window around the hit with newer pages below until the
 * window meets the newest message. A hit a thousand messages back was reached 40
 * messages at a time, 25 requests in a row (code-health audit NET-18). A send from
 * a window first goes back to the newest page (`jumpToLatest`).
 */
export function useChatPaging({
  token, chatId, chatLoading, messages, editThread, hasMoreOlder, setHasMoreOlder,
  viewRef, activeChatRef, showActionBanner, t,
}: Options) {
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [loadingNewer, setLoadingNewer] = useState(false);
  const [hasMoreNewer, setHasMoreNewer] = useState(false);
  const requestRef = useRef<object | null>(null);
  const session = getSessionGeneration();

  /** One paging read at a time, for the view that asked; null when it cannot start. */
  const begin = useCallback(() => {
    if (!token || !chatId || session !== getSessionGeneration() || chatId !== activeChatRef.current ||
        requestRef.current) return null;
    const request = {};
    const version = viewRef.current.version;
    requestRef.current = request;
    const inView = () => session === getSessionGeneration() && version === viewRef.current.version;
    return { token, chatId, inView, isCurrent: () => inView() && requestRef.current === request };
  }, [token, chatId, session, activeChatRef, viewRef]);

  const loadOlderMessages = useCallback(async () => {
    const oldest = messages[0];
    if (chatLoading || !hasMoreOlder || !oldest || !SERVER_ID.test(oldest.id)) return;
    const read = begin();
    if (!read) return;
    setLoadingOlder(true);
    try {
      const page = await api.listMessages(read.token, read.chatId, { limit: MESSAGE_PAGE_SIZE, before: oldest.id });
      if (!read.isCurrent()) return;
      editThread((prev) => {
        if (!read.inView()) return prev;
        const knownIds = new Set(prev.map((message) => message.id));
        return [...page.messages.filter((message) => !knownIds.has(message.id)), ...prev];
      }, "older_page");
      setHasMoreOlder(page.has_more);
    } catch (error) {
      pageReadFailed(error, read.isCurrent(), { showActionBanner, t });
    } finally {
      if (read.isCurrent()) {
        requestRef.current = null;
        setLoadingOlder(false);
      }
    }
  }, [begin, chatLoading, hasMoreOlder, messages, editThread, setHasMoreOlder, showActionBanner, t]);

  const loadNewerMessages = useCallback(async () => {
    const newest = messages.at(-1);
    if (chatLoading || !hasMoreNewer || !newest || !SERVER_ID.test(newest.id)) return;
    const read = begin();
    if (!read) return;
    setLoadingNewer(true);
    try {
      const page = await api.listMessages(read.token, read.chatId, { limit: MESSAGE_PAGE_SIZE, after: newest.id });
      if (!read.isCurrent()) return;
      editThread((prev) => {
        if (!read.inView()) return prev;
        const knownIds = new Set(prev.map((message) => message.id));
        return [...prev, ...page.messages.filter((message) => !knownIds.has(message.id))];
      }, "newer_page");
      setHasMoreNewer(page.has_more_after === true);
    } catch (error) {
      pageReadFailed(error, read.isCurrent(), { showActionBanner, t });
    } finally {
      if (read.isCurrent()) {
        requestRef.current = null;
        setLoadingNewer(false);
      }
    }
  }, [begin, chatLoading, hasMoreNewer, messages, editThread, showActionBanner, t]);

  /** Show the window around `messageId`; false when it could not be read. */
  const openAround = useCallback(async (messageId: string): Promise<boolean> => {
    const read = begin();
    if (!read) return false;
    try {
      const page = await api.listMessages(read.token, read.chatId, { limit: MESSAGE_PAGE_SIZE, around: messageId });
      if (!read.isCurrent() || page.messages.length === 0) return false;
      editThread(page.messages, "window_around");
      setHasMoreOlder(page.has_more);
      setHasMoreNewer(page.has_more_after === true);
      return true;
    } catch (error) {
      pageReadFailed(error, read.isCurrent(), { showActionBanner, t });
      return false;
    } finally {
      if (read.isCurrent()) requestRef.current = null;
    }
  }, [begin, editThread, setHasMoreOlder, showActionBanner, t]);

  /** Back from a window to the newest page (a send goes to the end of the thread). */
  const jumpToLatest = useCallback(async (): Promise<void> => {
    const read = begin();
    if (!read) return;
    try {
      const page = await api.listMessages(read.token, read.chatId, { limit: MESSAGE_PAGE_SIZE });
      if (!read.isCurrent()) return;
      editThread((prev) => mergeLocalAttachmentUris(prev, page.messages), "latest_page");
      setHasMoreOlder(page.has_more);
      setHasMoreNewer(false);
      void writeCachedChatMessages(read.chatId, page.messages, page.has_more);
    } catch (error) {
      pageReadFailed(error, read.isCurrent(), { showActionBanner, t });
    } finally {
      if (read.isCurrent()) requestRef.current = null;
    }
  }, [begin, editThread, setHasMoreOlder, showActionBanner, t]);

  /** A new view (another chat, New chat): nothing in flight belongs to it. */
  const resetPaging = useCallback(() => {
    requestRef.current = null;
    setLoadingOlder(false);
    setLoadingNewer(false);
    setHasMoreNewer(false);
  }, []);

  /** The thread ends before the newest message (a window): its "Load newer" page. */
  const newerPage = useMemo(
    () => (hasMoreNewer ? { loading: loadingNewer, load: loadNewerMessages } : null),
    [hasMoreNewer, loadingNewer, loadNewerMessages],
  );

  return {
    loadingOlder, loadOlderMessages,
    hasMoreNewer, newerPage,
    openAround, jumpToLatest, resetPaging,
  };
}
