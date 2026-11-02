import { useCallback, useEffect, useLayoutEffect, useRef, useState, type MutableRefObject } from "react";

import { opensChat, shouldScrollToEndWhenPinned } from "@/features/chat/model/scrollLogic";
import { clearScheduledTimeout, scheduleTimeout } from "@/lib/scheduleTimeout";

/** An opened chat is drawn hidden at most this long while it is put at its end. */
const OPEN_REVEAL_TIMEOUT_MS = 300;
/** Within this of the end, an opened chat is at its end. */
const AT_END_SLACK_PX = 2;

type Metrics = { distanceFromBottom: number; maxOffset: number } | null;

type Options = {
  chatId: string | null;
  messagesLength: number;
  streamActive: boolean;
  /** A search hit is being scrolled to: a chat opened for it is not put at its end. */
  heldRef: MutableRefObject<boolean>;
  scrollToEndNow: () => void;
};

/**
 * A chat the reader opens is drawn at its end on its first frame. FlashList
 * lays a thread out from the top; scrolled to the end after, it showed the top
 * and then jumped. The list is drawn hidden from the frame the chat's messages
 * arrive until a layout commit or scroll finds it at its end (or the thread
 * fits the screen), and at most OPEN_REVEAL_TIMEOUT_MS.
 */
export function useOpenAtEnd({ chatId, messagesLength, streamActive, heldRef, scrollToEndNow }: Options): {
  hidden: boolean;
  openingRef: MutableRefObject<boolean>;
  settleOpening: (metrics: Metrics) => void;
  /** Draw the chat where it is now and stop putting it at its end. */
  endOpening: () => void;
} {
  const [hidden, setHidden] = useState(false);
  const openingRef = useRef(false);
  const revealTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const previousRef = useRef({ chatId, count: messagesLength });

  const reveal = useCallback(() => {
    openingRef.current = false;
    clearScheduledTimeout(revealTimerRef);
    setHidden(false);
  }, []);

  const settleOpening = useCallback(
    (metrics: Metrics) => {
      if (!openingRef.current || !metrics) return;
      if (shouldScrollToEndWhenPinned(metrics.maxOffset) && metrics.distanceFromBottom > AT_END_SLACK_PX) {
        scrollToEndNow();
        return;
      }
      reveal();
    },
    [reveal, scrollToEndNow],
  );

  // Before the frame is drawn: the opened chat's first frame is already hidden.
  useLayoutEffect(() => {
    const previous = previousRef.current;
    previousRef.current = { chatId, count: messagesLength };
    const opened = opensChat({
      previousChatId: previous.chatId,
      chatId,
      previousCount: previous.count,
      count: messagesLength,
      streamActive,
    });
    if (!opened || heldRef.current) return;
    openingRef.current = true;
    setHidden(true);
    scheduleTimeout(revealTimerRef, OPEN_REVEAL_TIMEOUT_MS, reveal);
  }, [chatId, messagesLength, streamActive, heldRef, reveal]);

  useEffect(() => () => clearScheduledTimeout(revealTimerRef), []);

  return { hidden, openingRef, settleOpening, endOpening: reveal };
}
