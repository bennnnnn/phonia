import { isDrawerOpenGlobal } from "@/features/chat/drawer/drawer";
import { chatPageReadAt } from "@/features/chat/model/pageReads";
import { useReconnectRefresh } from "@/hooks/useReconnectRefresh";

type Options = {
  /** The chat on screen; none for a new chat. */
  chatId: string | null;
  /** The page is loading or a turn is under way: that read, or the turn, brings the page. */
  busy: () => boolean;
  /** `silentRefetchChat`: the newest page, unless this chat's was read within the stale window. */
  refetch: (chatId: string, cancelled: () => boolean) => Promise<void>;
};

/**
 * The open chat's page, read again once the API answers after an outage, as a return from
 * the background reads it, when nothing covers it: no screen pushed over the chat, no drawer.
 * A read of it that landed since the connection was lost (a reply's page, read as the API came
 * back, before the check saw it) is that read: the page is not read again.
 */
export function useChatPageReconnect({ chatId, busy, refetch }: Options): void {
  useReconnectRefresh(() => {
    if (chatId && !busy()) void refetch(chatId, () => false);
  }, { onScreen: () => !isDrawerOpenGlobal(), readAt: () => (chatId ? chatPageReadAt(chatId) : undefined) });
}
