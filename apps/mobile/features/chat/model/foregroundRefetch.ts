import type { AppStateStatus } from "react-native";

import { isContextFresh } from "@/lib/cache/contextRefresh";

/** Gate for silently reloading chat messages when the app returns to foreground. */
export function shouldRefetchChatOnForeground(opts: {
  appState: AppStateStatus;
  token: string | null;
  chatId: string | null;
  streaming: boolean;
  chatLoading: boolean;
  imageGenerating?: boolean;
}): boolean {
  return (
    opts.appState === "active" &&
    Boolean(opts.token) &&
    Boolean(opts.chatId) &&
    !opts.streaming &&
    !opts.chatLoading &&
    !opts.imageGenerating
  );
}

/** Foreground silent refetch — skip when this chat was fetched within the stale window. */
export function shouldSkipSilentChatRefetch(opts: {
  lastFetchedAt: number | undefined;
  force?: boolean;
  now?: number;
}): boolean {
  if (opts.force) return false;
  return isContextFresh(opts.lastFetchedAt, opts.now);
}

/**
 * Resume after backgrounding mid-stream must bypass TTL: the socket is dead and
 * the on-screen bubble may be truncated.
 */
export function shouldForceForegroundChatRecovery(opts: {
  wasStreamingWhenBackgrounded: boolean;
}): boolean {
  return opts.wasStreamingWhenBackgrounded;
}
