const SCROLL_HIDE_AT_BOTTOM = 64;
const SCROLL_SHOW_MIN_AWAY = 280;
const SCROLL_SHOW_VIEWPORT_RATIO = 0.28;

export function getScrollThresholds(options: {
  viewportHeight: number;
  windowHeight: number;
  listBottomPad: number;
}): { hideAtBottom: number; showWhenAway: number } {
  const viewport = options.viewportHeight || options.windowHeight * 0.55;
  const hideAtBottom = Math.max(
    SCROLL_HIDE_AT_BOTTOM,
    options.listBottomPad * 0.2,
  );
  const showWhenAway = Math.max(
    SCROLL_SHOW_MIN_AWAY,
    viewport * SCROLL_SHOW_VIEWPORT_RATIO,
    options.listBottomPad * 0.55,
  );
  return { hideAtBottom, showWhenAway };
}

export function resolveScrollAtBottom(options: {
  distanceFromBottom: number;
  hideAtBottom: number;
  showWhenAway: number;
  currentlyAtBottom: boolean;
}): boolean {
  if (options.distanceFromBottom <= options.hideAtBottom) return true;
  if (options.distanceFromBottom >= options.showWhenAway) return false;
  return options.currentlyAtBottom;
}

export function formatScrollAwayBadge(count: number): string | null {
  if (count <= 0) return null;
  return count > 9 ? "9+" : String(count);
}

/** Short threads fit the viewport — scrollToEnd would pin them to the composer. */
export function shouldScrollToEndWhenPinned(maxOffset: number): boolean {
  return maxOffset > 0;
}

/**
 * A short thread that was laid out from the bottom stays there with offset 0,
 * because the extra top pad is not scrollable. Once that pad is gone, pull a
 * leftover offset back to the header. A thread taller than the screen opens
 * on the latest message once, then the streaming pin takes over.
 */
export function resolveListAnchor(options: {
  contentHeight: number;
  viewportHeight: number;
  scrollOffset: number;
  atBottom: boolean;
  pinnedOverflow: boolean;
}): { action: "top" | "end" | "none"; pinnedOverflow: boolean } {
  if (options.viewportHeight <= 0 || options.contentHeight <= 0) {
    return { action: "none", pinnedOverflow: options.pinnedOverflow };
  }
  const maxOffset = Math.max(0, options.contentHeight - options.viewportHeight);
  if (!shouldScrollToEndWhenPinned(maxOffset)) {
    return {
      action: options.scrollOffset > 1 ? "top" : "none",
      pinnedOverflow: false,
    };
  }
  if (options.pinnedOverflow || !options.atBottom) {
    return { action: "none", pinnedOverflow: options.pinnedOverflow };
  }
  return { action: "end", pinnedOverflow: true };
}

/**
 * A chat the reader opened has just shown its messages: another chat's, or the
 * open chat's arriving after its load. A new chat taking its id is not one: its
 * first message was already on screen, and the list must not blink under it.
 * Nothing opens while the open chat's own reply streams; a stream on screen
 * when another chat opens belongs to the chat left behind.
 */
export function opensChat(options: {
  previousChatId: string | null;
  chatId: string | null;
  previousCount: number;
  count: number;
  streamActive: boolean;
}): boolean {
  if (options.count === 0 || options.chatId === null) return false;
  if (options.chatId === options.previousChatId) return !options.streamActive && options.previousCount === 0;
  return !(options.previousChatId === null && options.previousCount > 0);
}
