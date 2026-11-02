import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { NativeScrollEvent, NativeSyntheticEvent } from "react-native";
import type { FlashListRef } from "@shopify/flash-list";

import type { Message } from "@/lib/api";
import { useOpenAtEnd } from "@/features/chat/hooks/useOpenAtEnd";
import { useReaderDrag } from "@/features/chat/hooks/useReaderDrag";
import {
  getScrollThresholds,
  resolveListAnchor,
  resolveScrollAtBottom,
  shouldScrollToEndWhenPinned,
} from "@/features/chat/model/scrollLogic";
import { clearScheduledTimeout, scheduleTimeout } from "@/lib/scheduleTimeout";
import type { KeyboardSteps } from "@/hooks/useKeyboardInset";
import { useLatestRef } from "@/lib/latestRef";

/** What the message list wires to the scroll owner. */
export type ChatListScroll = {
  onContentSizeChange: (width: number, height: number) => void;
  onListLayout: (height: number) => void;
  /** FlashList measured and placed the rows: called before that frame is drawn. */
  onLayoutCommit: () => void;
  /** The reader drags the list, or a flick carries on: the pin waits until the scroll ends. */
  onReaderScrollBegin: () => void;
  /** The reader let go: with speed, the flick's momentum follows and the pin keeps waiting. */
  onReaderScrollEndDrag: (event: NativeSyntheticEvent<NativeScrollEvent>) => void;
  /** A chat just opened and is not at its end yet: the list is drawn hidden. */
  hidden: boolean;
};

type Options = {
  chatId: string | null;
  messagesLength: number;
  streamActive: boolean;
  windowHeight: number;
  /** The keyboard's steps while it moves (no React state); the thread follows them at the bottom. */
  keyboardSteps: KeyboardSteps;
};

/**
 * One writer pins the list to the bottom. While the reader is at the bottom
 * and not dragging, every time the rows grow (streamed text, a settling reply's
 * chrome, follow-up questions, an image) the list follows them in the frame
 * they grew, after FlashList measured them. FlashList's own autoscroll is off:
 * two writers fought, and it ran a tick late.
 */
export function useChatScroll({
  chatId,
  messagesLength,
  streamActive,
  windowHeight,
  keyboardSteps,
}: Options) {
  const listRef = useRef<FlashListRef<Message>>(null);
  const atBottomRef = useRef(true);
  const newMessageCountRef = useRef(0);
  const showScrollBtnRef = useRef(false);
  const listBottomPadRef = useRef(0);
  const maxScrollOffsetRef = useRef(0);
  const scrollOffsetRef = useRef(0);
  const viewportHeightRef = useRef(0);
  const keyboardScrollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const contentHeightRef = useRef(0);
  const pinnedOverflowRef = useRef(false);
  /** Heights the pin last followed: FlashList's rows, and the scroll content. */
  const followedRef = useRef({ rows: 0, content: 0 });
  /** A search hit is being shown: the list is the highlight's to scroll, not the pin's. */
  const heldRef = useRef(false);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const [scrollAwayCount, setScrollAwayCount] = useState(0);

  const messagesLenRef = useLatestRef(messagesLength);

  const updateAtBottom = useCallback((atBottom: boolean) => {
    atBottomRef.current = atBottom;
    const shouldShow = !atBottom && messagesLenRef.current > 0;
    if (shouldShow === showScrollBtnRef.current) return;
    showScrollBtnRef.current = shouldShow;
    setShowScrollToBottom(shouldShow);
    if (!shouldShow) setScrollAwayCount(0);
  }, [messagesLenRef]);

  const measureScrollMetrics = useCallback(
    (event?: NativeSyntheticEvent<NativeScrollEvent>) => {
      if (event) {
        const { contentOffset, contentSize, layoutMeasurement } = event.nativeEvent;
        const viewportHeight = layoutMeasurement.height;
        const contentHeight = contentSize.height;
        const scrollY = contentOffset.y;
        scrollOffsetRef.current = scrollY;
        if (viewportHeight > 0) viewportHeightRef.current = viewportHeight;
        if (viewportHeight <= 0 || contentHeight <= 0) return null;
        const maxOffset = Math.max(0, contentHeight - viewportHeight);
        maxScrollOffsetRef.current = maxOffset;
        return { distanceFromBottom: maxOffset - scrollY, maxOffset };
      }

      const list = listRef.current;
      if (!list) return null;
      try {
        const scrollOffset = list.getAbsoluteLastScrollOffset();
        scrollOffsetRef.current = scrollOffset;
        const contentSize = list.getChildContainerDimensions();
        const windowSize = list.getWindowSize();
        const viewportHeight = windowSize.height;
        const contentHeight = contentSize.height;
        if (viewportHeight > 0) viewportHeightRef.current = viewportHeight;
        if (viewportHeight <= 0 || contentHeight <= 0) return null;
        const maxOffset = Math.max(0, contentHeight - viewportHeight);
        maxScrollOffsetRef.current = maxOffset;
        return { distanceFromBottom: maxOffset - scrollOffset, maxOffset };
      } catch {
        return null;
      }
    },
    [],
  );

  const readScrollThresholds = useCallback(() => {
    return getScrollThresholds({
      viewportHeight: viewportHeightRef.current,
      windowHeight,
      listBottomPad: listBottomPadRef.current,
    });
  }, [windowHeight]);

  /** The end, in this frame: FlashList's own scrollToEnd waits a tick and may scroll by index first. */
  const scrollToEndNow = useCallback(() => {
    const list = listRef.current;
    const scroller = list?.getNativeScrollRef();
    if (scroller) scroller.scrollToEnd({ animated: false });
    else list?.scrollToEnd({ animated: false });
  }, []);

  const { hidden, openingRef, settleOpening, endOpening } = useOpenAtEnd({
    chatId,
    messagesLength,
    streamActive,
    heldRef,
    scrollToEndNow,
  });

  /** See useScrollHoldForHighlight. */
  const holdForHighlight = useCallback(
    (held: boolean) => {
      heldRef.current = held;
      if (held && openingRef.current) endOpening();
    },
    [endOpening, openingRef],
  );

  const syncScrollPosition = useCallback(
    (event?: NativeSyntheticEvent<NativeScrollEvent>) => {
      if (messagesLenRef.current === 0) {
        updateAtBottom(true);
        return;
      }
      const metrics = measureScrollMetrics(event);
      if (!metrics) return;
      if (metrics.maxOffset <= 0) {
        updateAtBottom(true);
        return;
      }
      const { hideAtBottom, showWhenAway } = readScrollThresholds();
      const nextAtBottom = resolveScrollAtBottom({
        distanceFromBottom: metrics.distanceFromBottom,
        hideAtBottom,
        showWhenAway,
        currentlyAtBottom: atBottomRef.current,
      });
      updateAtBottom(nextAtBottom);
    },
    [readScrollThresholds, measureScrollMetrics, updateAtBottom, messagesLenRef],
  );

  const drag = useReaderDrag(syncScrollPosition);
  const readerMovingRef = drag.movingRef;

  const scrollToEndIfAtBottom = useCallback((animated: boolean) => {
    if (!atBottomRef.current) return;
    const metrics = measureScrollMetrics();
    if (metrics && !shouldScrollToEndWhenPinned(metrics.maxOffset)) return;
    listRef.current?.scrollToEnd({ animated });
  }, [measureScrollMetrics]);

  /** Follow rows or content that grew, while the reader is at the bottom and not dragging. */
  const followGrowth = useCallback(
    (source: "rows" | "content", height: number) => {
      const grew = height > followedRef.current[source] + 0.5;
      followedRef.current[source] = height;
      const still = !readerMovingRef.current && !openingRef.current && !heldRef.current;
      if (!grew || !atBottomRef.current || !still) return;
      const metrics = measureScrollMetrics();
      if (metrics && !shouldScrollToEndWhenPinned(metrics.maxOffset)) return;
      scrollToEndNow();
    },
    [measureScrollMetrics, scrollToEndNow, openingRef, readerMovingRef],
  );

  useEffect(() => {
    if (messagesLength > 0 && newMessageCountRef.current > 0) {
      const pending = newMessageCountRef.current;
      newMessageCountRef.current = 0;
      if (atBottomRef.current) {
        scrollToEndIfAtBottom(true);
      } else {
        setScrollAwayCount((c) => c + pending);
        showScrollBtnRef.current = true;
        setShowScrollToBottom(true);
      }
    }
  }, [messagesLength, scrollToEndIfAtBottom]);

  useEffect(() => {
    requestAnimationFrame(() => syncScrollPosition());
  }, [messagesLength, syncScrollPosition]);

  useEffect(() => {
    maxScrollOffsetRef.current = 0;
    scrollOffsetRef.current = 0;
    viewportHeightRef.current = 0;
    contentHeightRef.current = 0;
    pinnedOverflowRef.current = false;
    followedRef.current = { rows: 0, content: 0 };
    showScrollBtnRef.current = false;
    setShowScrollToBottom(false);
    setScrollAwayCount(0);
    atBottomRef.current = true;
  }, [chatId]);

  useEffect(() => () => clearScheduledTimeout(keyboardScrollTimerRef), []);

  // No haptic: image generation and live talk call this after every picture and voice
  // turn. The scroll button plays its own on press (ChatScrollFab).
  const scrollToLatest = useCallback(() => {
    listRef.current?.scrollToEnd({ animated: true });
    updateAtBottom(true);
  }, [updateAtBottom]);

  const handleScroll = useCallback(
    (event: NativeSyntheticEvent<NativeScrollEvent>) => {
      syncScrollPosition(event);
      if (openingRef.current) settleOpening(measureScrollMetrics(event));
    },
    [syncScrollPosition, settleOpening, measureScrollMetrics, openingRef],
  );

  const {
    begin: handleReaderScrollBegin,
    endDrag: handleReaderScrollEndDrag,
    end: handleScrollEnd,
  } = drag;

  const alignListToContent = useCallback(() => {
    if (messagesLenRef.current === 0) return;
    const decision = resolveListAnchor({
      contentHeight: contentHeightRef.current,
      viewportHeight: viewportHeightRef.current,
      scrollOffset: scrollOffsetRef.current,
      atBottom: atBottomRef.current,
      pinnedOverflow: pinnedOverflowRef.current,
    });
    pinnedOverflowRef.current = decision.pinnedOverflow;
    if (decision.action === "top") {
      scrollOffsetRef.current = 0;
      listRef.current?.scrollToOffset({ offset: 0, animated: false });
      updateAtBottom(true);
      return;
    }
    if (decision.action === "end" && !heldRef.current) {
      scrollOffsetRef.current = Math.max(
        0,
        contentHeightRef.current - viewportHeightRef.current,
      );
      scrollToEndNow();
    }
  }, [updateAtBottom, scrollToEndNow, messagesLenRef]);

  const handleContentSizeChange = useCallback(
    (_width: number, height: number) => {
      contentHeightRef.current = height;
      alignListToContent();
      followGrowth("content", height);
    },
    [alignListToContent, followGrowth],
  );

  const handleListLayout = useCallback(
    (height: number) => {
      if (height > 0) viewportHeightRef.current = height;
      alignListToContent();
    },
    [alignListToContent],
  );

  // An interactive dismiss is the reader's own drag; an opening or held list is
  // placed by its own rules.
  const keyboardMayMoveList = useCallback(
    () => !readerMovingRef.current && !openingRef.current && !heldRef.current,
    [readerMovingRef, openingRef],
  );

  // Each step restarts the wait, so the thread catches up wherever the keyboard
  // slows between steps, mid-animation, and once more after it stops.
  useEffect(
    () =>
      keyboardSteps.subscribe((height) => {
        if (height <= 0 || !keyboardMayMoveList()) return;
        scheduleTimeout(keyboardScrollTimerRef, 50, () => {
          if (keyboardMayMoveList()) scrollToEndIfAtBottom(true);
        });
      }),
    [keyboardSteps, scrollToEndIfAtBottom, keyboardMayMoveList],
  );

  const handleLayoutCommit = useCallback(() => {
    const list = listRef.current;
    if (!list) return;
    if (openingRef.current) {
      settleOpening(measureScrollMetrics());
      return;
    }
    try {
      followGrowth("rows", list.getChildContainerDimensions().height);
    } catch {
      // FlashList has no layout yet.
    }
  }, [followGrowth, measureScrollMetrics, settleOpening, openingRef]);

  const listScroll: ChatListScroll = useMemo(
    () => ({
      onContentSizeChange: handleContentSizeChange,
      onListLayout: handleListLayout,
      onLayoutCommit: handleLayoutCommit,
      onReaderScrollBegin: handleReaderScrollBegin,
      onReaderScrollEndDrag: handleReaderScrollEndDrag,
      hidden,
    }),
    [
      handleContentSizeChange,
      handleListLayout,
      handleLayoutCommit,
      handleReaderScrollBegin,
      handleReaderScrollEndDrag,
      hidden,
    ],
  );

  return {
    listRef,
    listBottomPadRef,
    newMessageCountRef,
    showScrollToBottom,
    scrollAwayCount,
    scrollToLatest,
    handleScroll,
    handleScrollEnd,
    listScroll,
    holdForHighlight,
  };
}

/**
 * While a search hit is highlighted the list is the highlight's to scroll: an
 * opened chat is not put at its end and the bottom pin stands down, so neither
 * pulls the list back under the hit. A reply streaming takes the list back.
 */
export function useScrollHoldForHighlight(hold: (held: boolean) => void, held: boolean): void {
  useLayoutEffect(() => hold(held), [hold, held]);
}
