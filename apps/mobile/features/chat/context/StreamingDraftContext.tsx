import React, { useEffect, useRef, useState } from "react";

import {
  getStreamingDraft,
  subscribeStreamingDraft,
  type StreamingDraft,
} from "@/features/chat/model/streamingDraftStore";
import {
  nextStreamUiFlushDelay,
  STREAM_UI_INTERVAL_MS,
} from "@/features/chat/model/streamUiTiming";

/** Optional tree marker; draft state lives in the module store. */
export function StreamingDraftProvider({ children }: { children: React.ReactNode }) {
  return children;
}

/**
 * The single throttle at the draft→UI boundary. The store publishes per rAF
 * (~60fps); consumers re-render at the shared ~30fps stream cadence instead,
 * and downstream (row, markdown) parse immediately off this snapshot. A null
 * draft (stream end/reset) flushes immediately so the tail never lags.
 *
 * Every chat row calls this; only the row a reply streams into is `enabled`,
 * so the others never subscribe and never re-render for the draft.
 */
export function useStreamingDraft(enabled = true): StreamingDraft | null {
  const [snapshot, setSnapshot] = useState<StreamingDraft | null>(() =>
    enabled ? getStreamingDraft() : null,
  );
  // A row that goes live again (a reused list cell, the next turn) starts
  // from the store in the render it goes live, never from the draft it held
  // in an earlier live stretch.
  const [liveAt, setLiveAt] = useState(enabled);
  let current = snapshot;
  if (liveAt !== enabled) {
    current = enabled ? getStreamingDraft() : null;
    setLiveAt(enabled);
    setSnapshot(current);
  }
  const lastFlushRef = useRef(0);

  useEffect(() => {
    if (!enabled) return;
    lastFlushRef.current = 0;
    setSnapshot(getStreamingDraft());
    let timer: ReturnType<typeof setTimeout> | null = null;
    const unsubscribe = subscribeStreamingDraft(() => {
      const next = getStreamingDraft();
      if (next === null) {
        if (timer) {
          clearTimeout(timer);
          timer = null;
        }
        lastFlushRef.current = 0;
        setSnapshot(null);
        return;
      }
      if (timer) return; // one trailing flush already scheduled
      const elapsed = Date.now() - lastFlushRef.current;
      const wait = nextStreamUiFlushDelay(elapsed, STREAM_UI_INTERVAL_MS);
      if (wait === 0) {
        lastFlushRef.current = Date.now();
        setSnapshot(next);
        return;
      }
      timer = setTimeout(() => {
        timer = null;
        lastFlushRef.current = Date.now();
        setSnapshot(getStreamingDraft());
      }, wait);
    });
    return () => {
      unsubscribe();
      if (timer) clearTimeout(timer);
    };
  }, [enabled]);

  return enabled ? current : null;
}
