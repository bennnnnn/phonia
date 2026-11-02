import { createListenerSet } from "@/lib/listenerSet";

const listeners = createListenerSet();

/** Chat registers so sign-out can wipe drafts even if index stays mounted. */
export function subscribeComposerDraftReset(listener: () => void): () => void {
  return listeners.subscribe(listener);
}

/** Drop unsent composer text for the outgoing account. No-op if chat is unmounted. */
export function resetComposerDraftsForAccount(): void {
  listeners.emit();
}

/** Test helper. */
export function resetComposerDraftResetListeners(): void {
  listeners.clear();
}
