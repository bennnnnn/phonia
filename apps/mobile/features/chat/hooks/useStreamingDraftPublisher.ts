import { useCallback, useEffect, useRef } from "react";

import { publishStreamingDraft, type StreamingDraft } from "@/features/chat/model/streamingDraftStore";

/**
 * Publishes the streaming bubble's draft at most once a frame, so a burst of tokens
 * paints once; null clears it at once, and so does unmounting.
 */
export function useStreamingDraftPublisher(): (draft: StreamingDraft | null) => void {
  const frame = useRef<{ id: number | null; draft: StreamingDraft | null }>({ id: null, draft: null });
  const publish = useCallback((draft: StreamingDraft | null) => {
    const next = frame.current;
    next.draft = draft;
    if (draft === null) {
      if (next.id != null) cancelAnimationFrame(next.id);
      next.id = null;
      publishStreamingDraft(null);
      return;
    }
    if (next.id == null) {
      next.id = requestAnimationFrame(() => {
        next.id = null;
        publishStreamingDraft(next.draft);
      });
    }
  }, []);
  useEffect(() => () => publish(null), [publish]);
  return publish;
}
