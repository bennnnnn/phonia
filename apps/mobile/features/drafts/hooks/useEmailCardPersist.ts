import { useCallback, useEffect, useRef } from "react";

import { useAssistantMessageId, useEmailDraftSave } from "@/features/drafts/context/emailDraftPersist";
import { fullEmailText } from "@/features/drafts/model/emailCompose";
import { registerEmailDraftFlusher } from "@/features/drafts/model/emailDraftFlush";
import type { EmailDraft } from "@/lib/richBlocks";
import { isServerMessageId } from "@/lib/serverMessageId";

const EMAIL_DRAFT_PERSIST_DEBOUNCE_MS = 600;

export function useEmailCardPersist(currentDraft: EmailDraft, editing: boolean) {
  const save = useEmailDraftSave();
  const messageId = useAssistantMessageId();
  const draftRef = useRef(currentDraft);
  draftRef.current = currentDraft;
  const lastSentRef = useRef(fullEmailText(currentDraft));
  const inFlightRef = useRef<Promise<boolean> | null>(null);

  const persistNow = useCallback(
    (draft: EmailDraft): Promise<boolean> => {
      draftRef.current = draft;
      if (!save || !messageId || !isServerMessageId(messageId)) return Promise.resolve(true);
      if (inFlightRef.current) return inFlightRef.current;
      const saving = (async () => {
        // Include edits made while a previous request is pending. Flush must
        // await the server, not merely the debounce timer or a dirty flag.
        while (fullEmailText(draftRef.current) !== lastSentRef.current) {
          const next = draftRef.current;
          const text = fullEmailText(next);
          try {
            if (!await save(messageId, next)) return false;
          } catch {
            return false;
          }
          lastSentRef.current = text;
        }
        return true;
      })();
      inFlightRef.current = saving;
      void saving.then(() => { inFlightRef.current = null; });
      return saving;
    },
    [save, messageId],
  );

  useEffect(() => {
    if (!editing) return;
    const timer = setTimeout(() => {
      void persistNow(draftRef.current);
    }, EMAIL_DRAFT_PERSIST_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [currentDraft.to, currentDraft.subject, currentDraft.body, editing, persistNow]);

  useEffect(
    () =>
      registerEmailDraftFlusher(async () => {
        return persistNow(draftRef.current);
      }),
    [persistNow],
  );

  useEffect(
    () => () => {
      void persistNow(draftRef.current);
    },
    [persistNow],
  );

  return persistNow;
}
