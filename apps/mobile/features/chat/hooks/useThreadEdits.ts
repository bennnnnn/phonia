import { useCallback, useEffect } from "react";

import { onAppEvent } from "@/lib/appEvents";
import type { ChatTurnEvent, ChatTurnState } from "@/features/chat/model/chatTurnCore";
import { editLands } from "@/features/chat/model/chatTurnState";
import { withoutDeletedAttachment } from "@/features/chat/model/deletedAttachment";
import type { EditThread } from "@/features/chat/model/threadEdit";

type Options = {
  chatId: string | null;
  isCurrentView: () => boolean;
  /** One step of the chat's turn (useChat), which owns the thread. */
  step: (event: ChatTurnEvent) => void;
  /** The turn's state, which says whether an edit for a chat lands now or waits. */
  turn: { readonly current: ChatTurnState };
};

/**
 * The thread's other writers: each change to the list besides the turn's own frames is a
 * `thread_edit` step, so the turn reducer sequences every edit (structure ticket ST-08).
 */
export function useThreadEdits({ chatId, isCurrentView, step, turn }: Options): EditThread {
  const editThread = useCallback<EditThread>((update, source, belongsTo) => {
    const lands = editLands(turn.current, belongsTo);
    step({ type: "thread_edit", source, update, chatId: belongsTo });
    return lands;
  }, [step, turn]);

  // A photo or file deleted from Library leaves the open chat as it left the server's copy.
  useEffect(() => onAppEvent("attachmentDeleted", ({ attachmentId, chatId: holder }) => {
    if (holder !== chatId || !isCurrentView()) return;
    editThread((previous) => withoutDeletedAttachment(previous, attachmentId), "attachment_deleted");
  }), [chatId, isCurrentView, editThread]);

  return editThread;
}
