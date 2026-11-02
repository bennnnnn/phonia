import { useCallback, useEffect, useMemo, useRef, type RefObject } from "react";

import type { ChatTurnEvent, ChatTurnState } from "@/features/chat/model/chatTurnCore";

/**
 * After `stream_end` a reply's text is all here and only its save is left, which
 * takes a tenth of a second; the server stops waiting on it after 10 s and sends
 * `done` anyway (stream_events.DONE_COMMIT_WAIT_SECONDS). A send still waiting
 * past this leaves that quiet connection and reloads the chat for the saved
 * reply, as after a drop, rather than wait on it.
 */
export const REPLY_SAVE_GRACE_MS = 12_000;

/** Typing dots one send raised with its bubble, before the send went out. */
export type DotsTicket = {
  /** Still this send's: no Stop, other turn or other view has taken them down. */
  current: () => boolean;
  /**
   * Takes these dots down: the send went to image generation, or nowhere. A
   * no-op once they are not this send's, so a late call (say from a chat the
   * user has left) never touches another send's dots.
   */
  cancel: () => void;
};

/** What the composer sees of a turn before it goes out. */
export type SendTurnStart = {
  /**
   * Typing dots under a bubble just painted, in the same frame. Null when they
   * cannot go up yet: no chat is open, or a reply is still streaming or saving.
   */
  beginDots: () => DotsTicket | null;
  /**
   * Resolves once no reply streams or saves: a send made after the last reply's
   * `stream_end` goes out after its `done`, so that `done` never lands on the new
   * turn. `waitingId` is the bubble that waits; it says "Sending" after a beat.
   */
  whenReplySettled: (waitingId?: string) => Promise<void>;
};

type Options = {
  canStart: boolean;
  isCurrentView: () => boolean;
  /** The turn machine (useChat holds it) and one step of it. */
  turn: RefObject<ChatTurnState>;
  step: (event: ChatTurnEvent) => void;
  /** What useChat shows: a reply streams, or only its save is left. */
  streaming: boolean;
  finalizing: boolean;
};

/**
 * How a turn starts on screen before the composer's send goes out: typing dots
 * with the bubble, and the wait for a reply that is only saving, which Send no
 * longer has to sit out.
 */
export function useTurnStart({ canStart, isCurrentView, turn, step, streaming, finalizing }: Options): SendTurnStart {
  const settleWaitersRef = useRef<(() => void)[]>([]);
  const graceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const releaseWaiters = useCallback(() => {
    if (graceTimerRef.current != null) clearTimeout(graceTimerRef.current);
    graceTimerRef.current = null;
    const waiters = settleWaitersRef.current;
    settleWaitersRef.current = [];
    for (const resolve of waiters) resolve();
  }, []);

  // Every way a reply ends (done, an error, a drop, Stop, another view) leaves
  // both false; a waiter then checks for itself whether its send still stands.
  useEffect(() => {
    if (!streaming && !finalizing) releaseWaiters();
  }, [streaming, finalizing, releaseWaiters]);
  useEffect(() => releaseWaiters, [releaseWaiters]);

  const whenReplySettled = useCallback((waitingId?: string) => {
    if (turn.current.phase === "idle") return Promise.resolve();
    if (waitingId) step({ type: "send_waiting", messageId: waitingId });
    graceTimerRef.current ??= setTimeout(() => {
      graceTimerRef.current = null;
      if (isCurrentView()) step({ type: "unconfirmed_reply" });
    }, REPLY_SAVE_GRACE_MS);
    return new Promise<void>((resolve) => {
      settleWaitersRef.current.push(resolve);
    });
  }, [turn, step, isCurrentView]);

  const beginDots = useCallback((): DotsTicket | null => {
    if (!canStart || !isCurrentView() || turn.current.phase !== "idle") return null;
    step({ type: "dots_begin" });
    const attempt = turn.current.attempt;
    const current = () => isCurrentView() && turn.current.attempt === attempt;
    const cancel = () => {
      if (isCurrentView()) step({ type: "dots_cancelled", attempt });
    };
    return { current, cancel };
  }, [canStart, isCurrentView, turn, step]);

  return useMemo(() => ({ beginDots, whenReplySettled }), [beginDots, whenReplySettled]);
}
