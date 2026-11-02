/** Composer slot for New Chat (no `chatId` in the route). */
export const COMPOSER_NEW_THREAD_KEY = "new";

export function composerThreadKey(
  routeChatId: string | null | undefined,
): string {
  return typeof routeChatId === "string" && routeChatId.length > 0
    ? routeChatId
    : COMPOSER_NEW_THREAD_KEY;
}

/** Save the leaving thread's text and return the draft for `toKey`. Mutates `drafts`. */
export function takeThreadDraft(
  drafts: Map<string, string>,
  fromKey: string,
  toKey: string,
  currentText: string,
): string {
  if (fromKey === toKey) return currentText;
  drafts.set(fromKey, currentText);
  return drafts.get(toKey) ?? "";
}

/**
 * New Chat just received a real id. Keep the visible composer (usually empty
 * after send, or a follow-up typed while create was in flight). If the user
 * already opened another thread, leave that composer alone.
 */
export function adoptNewComposerThread(
  drafts: Map<string, string>,
  fromKey: string,
  toKey: string,
  currentText: string,
): string {
  if (fromKey === toKey) return toKey;
  if (fromKey !== COMPOSER_NEW_THREAD_KEY) return fromKey;
  drafts.set(COMPOSER_NEW_THREAD_KEY, "");
  drafts.set(toKey, currentText);
  return toKey;
}

/**
 * A failed send may restore into the composer only when it is empty or still
 * holds the sent text (setInput("") may not have flushed). Newer text wins.
 */
export function shouldRestoreFailedSend(
  currentText: string,
  failedText: string,
): boolean {
  const current = currentText.trim();
  return current.length === 0 || current === failedText.trim();
}

/** Stash a failed send onto another thread unless that slot already has newer text. */
export function stashFailedSendDraft(
  drafts: Map<string, string>,
  key: string,
  failedText: string,
): void {
  const stored = drafts.get(key) ?? "";
  if (shouldRestoreFailedSend(stored, failedText)) {
    drafts.set(key, failedText);
  }
}

/** Account change — drop every thread slot so the next sign-in cannot inherit text. */
export function clearAllComposerDrafts(drafts: Map<string, string>): void {
  drafts.clear();
}
