import { getSessionGeneration } from "@/lib/auth";

/**
 * When this sign-in last had each chat's newest page from the server, by any path: the chat's
 * open, a silent refetch (a return, the API back), the page a dropped turn's reply settled with
 * (useDroppedTurnReconcile), or the page kept for it. The view's own record missed the reply's
 * page: read as the API came back, it was read again once the check saw the API back (a 304).
 */
const pageReads = new Map<string, { session: number; at: number }>();

/** The chat's newest page landed from the server `at` (now). */
export function noteChatPageRead(chatId: string, at = Date.now()): void {
  pageReads.set(chatId, { session: getSessionGeneration(), at });
}

/** When this sign-in last read the chat's newest page, if it did. */
export function chatPageReadAt(chatId: string): number | undefined {
  const read = pageReads.get(chatId);
  return read?.session === getSessionGeneration() ? read.at : undefined;
}
