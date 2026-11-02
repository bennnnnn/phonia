import { useCallback, useEffect, useRef, useState, type SetStateAction } from "react";

import {
  discardDraftAttachment,
  uploadChatAttachment,
  type PendingAttachment,
} from "@/features/attachments/model/attachments";
import { useLatestRef } from "@/lib/latestRef";
import { reportFailure } from "@/lib/sentry";

/**
 * The attachment queued in the composer, and the ones waiting on other threads
 * with their text drafts. A send in flight reads the ref, which never lags a render.
 *
 * `setPendingAttachment` hands the attachment on (a send took it) and never
 * cleans up: the sent bubble draws from its copy, which a later launch sweeps
 * (`sweepOldPickerCopies`). `replacePendingAttachment` is for a draft the user
 * dropped or replaced, whose copy and unlinked upload are discarded.
 */
export function useSendAttachment(token: string | null) {
  const [pendingAttachment, setPendingAttachmentState] = useState<PendingAttachment | null>(null);
  const pendingAttachmentRef = useRef<PendingAttachment | null>(null);
  const threadDraftsRef = useRef(new Map<string, PendingAttachment>());
  const tokenRef = useLatestRef(token);

  const setPendingAttachment = useCallback((value: SetStateAction<PendingAttachment | null>) => {
    const next = typeof value === "function" ? value(pendingAttachmentRef.current) : value;
    pendingAttachmentRef.current = next;
    setPendingAttachmentState(next);
  }, []);

  const replacePendingAttachment = useCallback((next: PendingAttachment | null) => {
    const previous = pendingAttachmentRef.current;
    setPendingAttachment(next);
    if (previous && previous !== next) discardDraftAttachment(tokenRef.current, previous);
  }, [setPendingAttachment, tokenRef]);

  /** Leaving a thread keeps its attachment beside its text; arriving brings that thread's back. */
  const switchAttachmentThread = useCallback((fromKey: string, toKey: string) => {
    const drafts = threadDraftsRef.current;
    const leaving = pendingAttachmentRef.current;
    if (leaving) drafts.set(fromKey, leaving);
    else drafts.delete(fromKey);
    const arriving = drafts.get(toKey) ?? null;
    drafts.delete(toKey);
    setPendingAttachment(arriving);
  }, [setPendingAttachment]);

  /**
   * A failed send from a thread the user left waits there with its text, upload
   * id and all, so the next send reuses it. As with text, a newer draft in that
   * slot wins, and the open thread's composer is never written behind its back.
   */
  const stashAttachmentForThread = useCallback(
    (key: string, openKey: string, attachment: PendingAttachment | null) => {
      if (!attachment) return;
      const drafts = threadDraftsRef.current;
      const stored = drafts.get(key);
      if (key === openKey || (stored && stored !== attachment)) {
        discardDraftAttachment(tokenRef.current, attachment);
        return;
      }
      drafts.set(key, attachment);
    },
    [tokenRef],
  );

  /** Account change: nothing carries over. The old token is gone, so only the copies go. */
  const resetAttachmentDrafts = useCallback(() => {
    for (const draft of threadDraftsRef.current.values()) discardDraftAttachment(null, draft);
    threadDraftsRef.current.clear();
    discardDraftAttachment(null, pendingAttachmentRef.current);
    setPendingAttachment(null);
  }, [setPendingAttachment]);

  useEffect(() => {
    const drafts = threadDraftsRef.current;
    return () => {
      for (const draft of drafts.values()) discardDraftAttachment(null, draft);
      drafts.clear();
      discardDraftAttachment(null, pendingAttachmentRef.current);
    };
  }, []);

  return {
    pendingAttachment,
    pendingAttachmentRef,
    setPendingAttachment,
    replacePendingAttachment,
    switchAttachmentThread,
    stashAttachmentForThread,
    resetAttachmentDrafts,
  };
}

/**
 * Uploads once: the copy it returns carries the server id, so a restore or a retry reuses it.
 * A failed upload is reported (metadata only) and thrown on for the caller's toast.
 */
export async function uploadSendAttachment(token: string, attachment: PendingAttachment) {
  const id = await uploadChatAttachment(token, attachment).catch((error: unknown) => {
    reportFailure("attachment_upload", error);
    throw error;
  });
  // A Library pick was already on the server; only a fresh upload is this draft's to cancel.
  const uploadedForDraft = attachment.uploadedForDraft ?? !attachment.existingAttachmentId;
  return { ids: [id], attachment: { ...attachment, existingAttachmentId: id, uploadedForDraft } };
}
