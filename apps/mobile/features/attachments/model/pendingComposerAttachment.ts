import { getSessionGeneration } from "@/lib/auth";
import { createListenerSet } from "@/lib/listenerSet";
import type { PendingAttachment } from "@/features/attachments/model/attachments";

type Queued = { pending: PendingAttachment; session: number; thread?: string };
let queued: Queued | null = null;
const listeners = createListenerSet();

/** Hand a Library pick to the intended composer in the same account session. */
export function queueComposerAttachment(pending: PendingAttachment, thread?: string): void {
  queued = { pending, thread, session: getSessionGeneration() };
  listeners.emit();
}
export function takeQueuedComposerAttachment(thread?: string): PendingAttachment | null {
  if (queued?.session !== getSessionGeneration()) queued = null;
  if (!queued || (queued.thread && queued.thread !== thread)) return null;
  const next = queued.pending;
  queued = null;
  return next;
}
export function subscribeComposerAttachmentQueue(listener: () => void): () => void {
  return listeners.subscribe(listener);
}
/** Test helper. */
export function resetComposerAttachmentQueue(): void { queued = null; }
