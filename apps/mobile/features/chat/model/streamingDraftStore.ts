import type { SearchSource } from "@/lib/api";
import { createListenerSet } from "@/lib/listenerSet";

export type StreamingDraft = {
  content: string;
  search_sources?: SearchSource[];
  status?: string;
  /** Activity context for the status label (e.g. the web-search query). */
  statusDetail?: string;
  /** When the status's phase began, on this phone's clock (ms): "Thinking… 12s" counts from it. */
  statusStartedAt?: number;
};

let draft: StreamingDraft | null = null;
const listeners = createListenerSet();

export function getStreamingDraft(): StreamingDraft | null {
  return draft;
}

export function publishStreamingDraft(next: StreamingDraft | null): void {
  draft = next;
  listeners.emit();
}

export function subscribeStreamingDraft(listener: () => void): () => void {
  return listeners.subscribe(listener);
}

export function resetStreamingDraftStore(): void {
  draft = null;
  listeners.clear();
}
