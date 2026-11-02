import {
  formatScrollAwayBadge,
  getScrollThresholds,
  opensChat,
  resolveScrollAtBottom,
  resolveListAnchor,
  shouldScrollToEndWhenPinned,
} from "@/features/chat/model/scrollLogic";

describe("chatScrollLogic", () => {
  it("getScrollThresholds scales with viewport and composer pad", () => {
    const small = getScrollThresholds({
      viewportHeight: 400,
      windowHeight: 800,
      listBottomPad: 0,
    });
    expect(small.hideAtBottom).toBe(64);
    expect(small.showWhenAway).toBeGreaterThanOrEqual(280);

    const padded = getScrollThresholds({
      viewportHeight: 400,
      windowHeight: 800,
      listBottomPad: 600,
    });
    expect(padded.showWhenAway).toBeGreaterThan(small.showWhenAway);
  });

  it("resolveScrollAtBottom hysteresis keeps prior state in dead zone", () => {
    expect(
      resolveScrollAtBottom({
        distanceFromBottom: 10,
        hideAtBottom: 64,
        showWhenAway: 280,
        currentlyAtBottom: false,
      }),
    ).toBe(true);
    expect(
      resolveScrollAtBottom({
        distanceFromBottom: 400,
        hideAtBottom: 64,
        showWhenAway: 280,
        currentlyAtBottom: true,
      }),
    ).toBe(false);
    expect(
      resolveScrollAtBottom({
        distanceFromBottom: 150,
        hideAtBottom: 64,
        showWhenAway: 280,
        currentlyAtBottom: true,
      }),
    ).toBe(true);
    expect(
      resolveScrollAtBottom({
        distanceFromBottom: 150,
        hideAtBottom: 64,
        showWhenAway: 280,
        currentlyAtBottom: false,
      }),
    ).toBe(false);
  });

  it("formatScrollAwayBadge caps at 9+", () => {
    expect(formatScrollAwayBadge(0)).toBeNull();
    expect(formatScrollAwayBadge(3)).toBe("3");
    expect(formatScrollAwayBadge(10)).toBe("9+");
  });

  it("shouldScrollToEndWhenPinned skips short threads that still fit", () => {
    expect(shouldScrollToEndWhenPinned(0)).toBe(false);
    expect(shouldScrollToEndWhenPinned(12)).toBe(true);
  });

  it("keeps a short thread at the top and opens a tall thread on the latest message once", () => {
    expect(
      resolveListAnchor({
        contentHeight: 420,
        viewportHeight: 700,
        scrollOffset: 180,
        atBottom: true,
        pinnedOverflow: false,
      }),
    ).toEqual({ action: "top", pinnedOverflow: false });
    expect(
      resolveListAnchor({
        contentHeight: 420,
        viewportHeight: 700,
        scrollOffset: 0,
        atBottom: true,
        pinnedOverflow: false,
      }),
    ).toEqual({ action: "none", pinnedOverflow: false });
    expect(
      resolveListAnchor({
        contentHeight: 1400,
        viewportHeight: 700,
        scrollOffset: 0,
        atBottom: true,
        pinnedOverflow: false,
      }),
    ).toEqual({ action: "end", pinnedOverflow: true });
    expect(
      resolveListAnchor({
        contentHeight: 1600,
        viewportHeight: 700,
        scrollOffset: 700,
        atBottom: true,
        pinnedOverflow: true,
      }),
    ).toEqual({ action: "none", pinnedOverflow: true });
  });

  it.each([
    ["another chat", "chat-a", "chat-b", 6, 9, false, true],
    ["a chat from home", null, "chat-b", 0, 9, false, true],
    ["the open chat's messages after its load", "chat-b", "chat-b", 0, 9, false, true],
    ["a new chat taking its id under its first message", null, "chat-c", 1, 1, false, false],
    ["a new chat's first message", null, null, 0, 1, false, false],
    ["more messages in the open chat", "chat-b", "chat-b", 9, 10, false, false],
    ["another chat while the last one's reply streams", "chat-a", "chat-b", 6, 9, true, true],
    ["the open chat's load while its own reply streams", "chat-b", "chat-b", 0, 9, true, false],
    ["a chat with no messages yet", "chat-a", "chat-b", 6, 0, false, false],
  ] as const)("opensChat: %s", (_case, previousChatId, chatId, previousCount, count, streamActive, expected) => {
    expect(opensChat({ previousChatId, chatId, previousCount, count, streamActive })).toBe(expected);
  });
});
