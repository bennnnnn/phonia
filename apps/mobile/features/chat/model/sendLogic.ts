import type { Message } from "@/lib/api";
import { messageTextForSend, type PendingAttachment } from "@/features/attachments/model/attachments";

import type { ClientGeo } from "@/features/chat/model/clientGeo";

export type ComposerSendDraft = {
  text: string;
  attachment: PendingAttachment | null;
};

export type SendMessageOptions = {
  skipUserBubble?: boolean;
  trackSendingMessageId?: string;
  attachmentIds?: string[];
  localImageUri?: string | null;
  localFileUri?: string | null;
  localFileName?: string | null;
  localFileContentType?: string | null;
  model?: string | null;
  clientGeo?: ClientGeo | null;
  /** Original composer data, retained only for definitely-unsaved recovery. */
  composerDraft?: ComposerSendDraft;
};

export type PendingSend = {
  content: string;
  options: SendMessageOptions;
  messageId: string | null;
  retryingRejected: boolean;
  dispatched: boolean;
  /** The server sent `start`: it owns this turn, so a dropped connection is never replayed. */
  accepted?: boolean;
  /** The message's name on every send of it (a replay, Retry): the server runs one turn per name. */
  clientMessageId?: string;
  /**
   * Taken back before it went out: by the opened chat's page read (`page`; its chat is gone or the
   * view left, and the read returned the draft) or by Stop (`stop`; its sender returns the draft).
   */
  takenBack?: "page" | "stop";
};

export type RejectedSend = PendingSend & { reason: "send_rejected" | "attachment_rejected" };

export function shouldBlockSend(options: {
  text: string;
  hasAttachment: boolean;
  streaming: boolean;
  token: string | null;
  creating: boolean;
  attachPicking: boolean;
  isOffline: boolean;
}): boolean {
  const trimmed = options.text.trim();
  if (!trimmed && !options.hasAttachment) return true;
  if (options.isOffline) return true;
  if (options.streaming || !options.token || options.creating || options.attachPicking) {
    return true;
  }
  return false;
}

export function buildOptimisticUserMessage(options: {
  text: string;
  attached: PendingAttachment | null;
  optimisticId: string;
  createdAt: string;
}): Message {
  const sendText = messageTextForSend(options.text, options.attached);
  const display =
    options.text.trim() ||
    (options.attached?.kind === "file" ? options.attached.fileName : sendText);
  return {
    id: options.optimisticId,
    role: "user",
    content: display,
    model: null,
    local_image_uri:
      options.attached?.kind === "image" ? options.attached.localUri : null,
    local_file_uri:
      options.attached?.kind === "file" ? options.attached.localUri : null,
    local_file_name:
      options.attached?.kind === "file" ? options.attached.fileName : null,
    local_file_content_type:
      options.attached?.kind === "file" ? options.attached.contentType : null,
    created_at: options.createdAt,
  };
}

export function buildPendingSendAfterCreate(options: {
  text: string;
  composerText?: string;
  attached: PendingAttachment | null;
  attachmentIds?: string[];
  optimisticId: string;
  clientGeo?: ClientGeo | null;
  model: string;
}): {
  text: string;
  composerDraft: ComposerSendDraft;
  skipUserBubble: true;
  trackSendingMessageId: string;
  attachmentIds?: string[];
  localImageUri?: string | null;
  localFileUri?: string | null;
  localFileName?: string | null;
  localFileContentType?: string | null;
  clientGeo?: ClientGeo | null;
  model: string;
} {
  const sendText = messageTextForSend(options.text, options.attached);
  return {
    text: sendText,
    composerDraft: { text: options.composerText ?? options.text, attachment: options.attached ? { ...options.attached } : null },
    skipUserBubble: true,
    trackSendingMessageId: options.optimisticId,
    attachmentIds: options.attachmentIds,
    localImageUri:
      options.attached?.kind === "image" ? options.attached.localUri : null,
    localFileUri:
      options.attached?.kind === "file" ? options.attached.localUri : null,
    localFileName:
      options.attached?.kind === "file" ? options.attached.fileName : null,
    localFileContentType:
      options.attached?.kind === "file" ? options.attached.contentType : null,
    clientGeo: options.clientGeo ?? null,
    model: options.model,
  };
}
