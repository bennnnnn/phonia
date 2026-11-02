import { useEffect, useMemo, useRef, useState } from "react";

import type { Message } from "@/lib/api";
import { warmSvgMath } from "@/lib/math/svgMath";
import { scheduleIdleTask } from "@/lib/scheduleIdle";
import { getStreamingDraft, subscribeStreamingDraft } from "@/features/chat/model/streamingDraftStore";

/** The chat's own first frames and its cold-start work come before the warm-up. */
export const WARM_MATH_AFTER_MS = 2_000;
/** The latest messages are the ones read: older pages do not ask for the renderer. */
const RECENT_MESSAGES = 40;
/** A marker split across two draft flushes is still found. */
const MARKER_OVERLAP = 16;

/**
 * What only the display-maths renderer (MathJax) draws: display maths, an
 * environment, a maths or answer fence, and the heavy operators an answer
 * card sends to it.
 */
export const DISPLAY_MATHS_MARKERS =
  /\$\$|\\\[|\\begin\{|```(?:math|answer)|\\(?:int|sum|lim|binom)(?![a-zA-Z])/;

function threadHasDisplayMaths(messages: readonly Message[]): boolean {
  for (let i = messages.length - 1, seen = 0; i >= 0 && seen < RECENT_MESSAGES; i -= 1, seen += 1) {
    if (DISPLAY_MATHS_MARKERS.test(messages[i]!.content)) return true;
  }
  return false;
}

/**
 * Load the display-maths renderer while the chat is idle, once the open
 * thread or the reply streaming into it holds display maths, so its first
 * formula draws at once instead of waiting for the parser to load. A chat
 * with no such maths never loads it: the load is a long task and megabytes.
 */
export function useWarmMathRenderer(messages: readonly Message[]): void {
  const mountedAt = useRef<number | null>(null);
  const threadNeeds = useMemo(() => threadHasDisplayMaths(messages), [messages]);
  const [draftNeeds, setDraftNeeds] = useState(false);
  const wanted = threadNeeds || draftNeeds;

  useEffect(() => {
    mountedAt.current = Date.now();
  }, []);

  // The draft only grows while a reply streams: read each flush's new text.
  useEffect(() => {
    if (wanted) return;
    let read = 0;
    return subscribeStreamingDraft(() => {
      const text = getStreamingDraft()?.content ?? "";
      if (text.length < read) read = 0;
      const fresh = text.slice(Math.max(0, read - MARKER_OVERLAP));
      read = text.length;
      if (DISPLAY_MATHS_MARKERS.test(fresh)) setDraftNeeds(true);
    });
  }, [wanted]);

  useEffect(() => {
    if (!wanted) return;
    let cancelIdle: (() => void) | null = null;
    const now = Date.now();
    const wait = Math.max(0, (mountedAt.current ?? now) + WARM_MATH_AFTER_MS - now);
    const timer = setTimeout(() => {
      cancelIdle = scheduleIdleTask(warmSvgMath);
    }, wait);
    return () => {
      clearTimeout(timer);
      cancelIdle?.();
    };
  }, [wanted]);
}
