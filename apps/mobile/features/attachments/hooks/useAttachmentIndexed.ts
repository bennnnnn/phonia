import { useCallback, useSyncExternalStore } from "react";

import { useAuthToken } from "@/contexts/AuthContext";
import {
  INDEX_PENDING,
  INDEX_READY,
  readAttachmentIndexStatus,
  subscribeAttachmentIndexStatus,
  type AttachmentIndexStatus,
} from "@/features/attachments/model/attachmentIndexStatus";

const unsubscribed = () => undefined;

/**
 * Indexed once attachment RAG chunks exist (or indexing does not apply).
 * Every row showing one attachment shares a single status and poller.
 */
export function useAttachmentIndexed(
  attachmentId: string | null | undefined,
): AttachmentIndexStatus {
  const token = useAuthToken();
  const polled = attachmentId && token ? attachmentId : null;
  const subscribe = useCallback(
    (listener: () => void) =>
      polled && token ? subscribeAttachmentIndexStatus(polled, token, listener) : unsubscribed,
    [polled, token],
  );
  const read = useCallback(
    () => (!attachmentId ? INDEX_READY : polled ? readAttachmentIndexStatus(polled) : INDEX_PENDING),
    [attachmentId, polled],
  );
  return useSyncExternalStore(subscribe, read, read);
}
