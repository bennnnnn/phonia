import {
  useCallback,
  useRef,
  useState,
  type MutableRefObject,
  type SetStateAction,
} from "react";

import { useActionFeedbackOptional } from "@/contexts/actionFeedbackCore";
import { api, type Message } from "@/lib/api";
import { ApiRequestError } from "@/lib/api/client";
import { notifyWarning } from "@/lib/haptics";
import { reportRecoverableError } from "@/lib/reportRecoverableError";
import {
  IMAGE_GEN_FAILED_ASSISTANT_ID,
  IMAGE_GEN_PENDING_ASSISTANT_ID,
} from "@/features/images/model/imageGenMessages";
import {
  applyImageGenFailure,
  applyImageGenSuccess,
  hasImageGenFailedAssistant,
  imageGenUserBubble,
  restoreImageGenPending,
} from "@/features/images/model/imageGenTurn";
import { notifyOfflineSendBlocked } from "@/lib/offlineSendFeedback";
import { emitAppEvent } from "@/lib/appEvents";
import { useLatestRef } from "@/lib/latestRef";
import type { PendingAttachment } from "@/features/attachments/model/attachments";

/**
 * What image generation takes from the chat screen it runs on: the chat a picture lands
 * in, how a reference photo uploads and how a failure reads. Images owns this shape, so
 * it never imports the chat feature (code-health audit ARCH-10).
 */
type Options = {
  token: string | null;
  /** The open chat's id, or a new chat made the open one; throws when none can be made. */
  ensureChatId: () => Promise<string | null>;
  uploadReference: (token: string, attachment: PendingAttachment) => Promise<{ ids: string[] }>;
  /**
   * A failed request in the chat's words (its code, the plan's limits), and whether a
   * retry could go differently: the day's cap or a refused prompt fails again. `error` is
   * what was thrown, for a failure the API did not answer (no connection, the reference
   * photo's upload).
   */
  describeFailure: (message: string, code: string | undefined, error: unknown) => ImageGenFailureText;
  /**
   * Changes the thread on screen, which the chat owns: the picture turn's bubbles, named
   * "image_turn". Once the picture has its chat, each edit names it: a picture that
   * finishes after the user opened another chat waits for its own (the chat answers false).
   */
  editThread: (update: SetStateAction<Message[]>, source: "image_turn", chatId?: string) => boolean | void;
  streaming: boolean;
  isOffline: boolean;
  onOpenUpgrade: () => void;
  onOfflineBlocked?: () => void;
  onScrollToLatest: () => void;
  newMessageCountRef: MutableRefObject<number>;
  t: (key: string) => string;
};

type ImageGenFailureText = { message: string; retryable: boolean };

export type ImageGenSubmit = {
  prompt: string;
  userMessage: string;
  aspectRatio?: string | null;
  referenceAttachmentIds?: string[];
  referenceAttachment?: PendingAttachment;
  /** Already-running persistence gate; optimistic image UI does not wait on it. */
  persistenceReady?: Promise<boolean>;
  /** Restores the composer draft when the persistence gate rejects the turn. */
  onPersistenceFailure?: () => void;
  /**
   * The composer already painted this request's bubble: the picture is drawn
   * under it, and a request that cannot start takes it away and restores the draft.
   */
  userMessageId?: string;
};

/** Pro image generation from composer text — no confirmation sheet. */
export function useImageGeneration({
  token,
  ensureChatId,
  uploadReference,
  describeFailure,
  editThread,
  streaming,
  isOffline,
  onOpenUpgrade,
  onOfflineBlocked,
  onScrollToLatest,
  newMessageCountRef,
  t,
}: Options) {
  const feedback = useActionFeedbackOptional();
  const [generating, setGenerating] = useState(false);
  // Refs so submitPrompt never no-ops on a stale streaming/generating closure
  // from a prior Fast Refresh or a turn that just finished.
  const generatingRef = useRef(false);
  const streamingRef = useRef(streaming);
  const tokenRef = useRef(token);
  const abortRef = useRef<AbortController | null>(null);
  const userCancelRef = useRef(false);
  const lastSubmitRef = useRef<ImageGenSubmit | null>(null);
  const optimisticUserIdRef = useRef<string | null>(null);
  generatingRef.current = generating;
  streamingRef.current = streaming;
  tokenRef.current = token;

  const submitPrompt = useCallback(
    async (input: ImageGenSubmit) => {
      const adoptedId = input.userMessageId;
      /** A painted bubble with nothing to draw under it goes, and its draft comes back. */
      const giveBack = () => {
        if (!adoptedId) return;
        editThread((prev) => prev.filter((row) => row.id !== adoptedId), "image_turn");
        newMessageCountRef.current = Math.max(0, newMessageCountRef.current - 1);
        input.onPersistenceFailure?.();
      };
      const authToken = tokenRef.current;
      if (!authToken || generatingRef.current) return giveBack();
      // The composer hands over its own painted turn only once no reply streams.
      if (streamingRef.current && !adoptedId) {
        reportRecoverableError(feedback, t("chat.busy"));
        return;
      }
      // Don't trust client isPaid alone — try the API; HTTP 403 opens upgrade.
      if (isOffline) {
        notifyOfflineSendBlocked({
          warn: notifyWarning,
          showToast: onOfflineBlocked,
        });
        return giveBack();
      }
      const prompt = input.prompt.trim();
      const userContent = imageGenUserBubble(input.userMessage, prompt);
      if (!prompt || !userContent) return giveBack();

      // A retry draws under the same bubble by its own path (`priorUserId`).
      lastSubmitRef.current = { ...input, prompt, userMessage: userContent, userMessageId: undefined };
      generatingRef.current = true;
      setGenerating(true);
      const abort = new AbortController();
      abortRef.current = abort;
      userCancelRef.current = false;

      const createdAt = new Date().toISOString();
      // React may defer/replay functional updates. Establish request identity
      // before scheduling the render, never from inside its updater.
      const priorUserId = optimisticUserIdRef.current;
      const optimisticUserId = adoptedId ?? priorUserId ?? `local-img-${Date.now()}`;
      optimisticUserIdRef.current = optimisticUserId;
      editThread((prev) => {
        const retrySameTurn =
          !adoptedId &&
          hasImageGenFailedAssistant(prev) &&
          Boolean(priorUserId) &&
          prev.some((row) => row.id === priorUserId && row.content === userContent);
        if (retrySameTurn) {
          return restoreImageGenPending(prev);
        }
        const adopted = adoptedId ? prev.find((row) => row.id === adoptedId) : undefined;
        const without = prev.filter(
          (row) =>
            row.id !== IMAGE_GEN_FAILED_ASSISTANT_ID &&
            row.id !== IMAGE_GEN_PENDING_ASSISTANT_ID &&
            row.id !== priorUserId &&
            row.id !== adoptedId,
        );
        return [
          ...without,
          adopted ? { ...adopted, content: userContent } : {
            id: optimisticUserId,
            role: "user",
            content: userContent,
            model: null,
            created_at: createdAt,
          },
          {
            id: IMAGE_GEN_PENDING_ASSISTANT_ID,
            role: "assistant",
            content: "",
            model: "image-gen-model",
            created_at: createdAt,
          },
        ];
      }, "image_turn");
      // The composer counted its own bubble when it painted it.
      const addedRows = adoptedId ? 1 : priorUserId ? 0 : 2;
      newMessageCountRef.current += addedRows;
      onScrollToLatest();

      // The picture's chat once it has one (until then the one on screen); a picture that waits scrolls nothing.
      let owner: string | undefined;
      const edit = (update: (rows: Message[]) => Message[]) => editThread(update, "image_turn", owner);
      try {
        const persistenceReady = input.persistenceReady
          ? await input.persistenceReady.catch(() => false)
          : true;
        if (!persistenceReady) {
          editThread(
            (prev) => prev.filter((row) => row.id !== optimisticUserId && row.id !== IMAGE_GEN_PENDING_ASSISTANT_ID),
            "image_turn",
          );
          if (adoptedId || !priorUserId) {
            newMessageCountRef.current = Math.max(
              0,
              newMessageCountRef.current - 2,
            );
          }
          optimisticUserIdRef.current = null;
          lastSubmitRef.current = null;
          input.onPersistenceFailure?.();
          return;
        }
        const persistedInput = {
          ...input,
          persistenceReady: undefined,
          onPersistenceFailure: undefined,
          userMessageId: undefined,
        };
        lastSubmitRef.current = persistedInput;

        const activeChatId = await ensureChatId();
        if (!activeChatId) {
          edit((prev) => applyImageGenFailure(prev, "failed", t("chat.error_generic")));
          return;
        }
        owner = activeChatId;
        const referenceIds = input.referenceAttachment
          ? (await uploadReference(authToken, input.referenceAttachment)).ids
          : input.referenceAttachmentIds;
        // Retry the same upload/reference, not whatever image is newest later.
        lastSubmitRef.current = {
          ...persistedInput,
          referenceAttachment: undefined,
          referenceAttachmentIds: referenceIds,
        };
        if (abort.signal.aborted) throw new Error("Image request cancelled");
        const result = await api.generateImage(
          authToken,
          {
            chat_id: activeChatId,
            prompt,
            user_message: userContent,
            aspect_ratio: input.aspectRatio ?? null,
            reference_attachment_ids: referenceIds,
          },
          { signal: abort.signal },
        );
        if (abort.signal.aborted) throw new Error("Image request cancelled");
        const shown = edit((prev) => applyImageGenSuccess(prev, optimisticUserId, [result.user_message, result.assistant_message]));
        emitAppEvent("attachmentAdded", { chatId: activeChatId });
        optimisticUserIdRef.current = null;
        lastSubmitRef.current = null;
        if (shown !== false) onScrollToLatest();
      } catch (error) {
        const canceled = userCancelRef.current;
        userCancelRef.current = false;
        if (canceled) {
          edit((prev) => applyImageGenFailure(prev, "canceled"));
          return;
        }
        if (error instanceof ApiRequestError && error.status === 403) {
          edit((prev) => applyImageGenFailure(prev, "failed"));
          onOpenUpgrade();
          return;
        }
        const message = error instanceof Error ? error.message : t("common.error");
        const code = error instanceof ApiRequestError ? (error.code ?? undefined) : undefined;
        const failure = describeFailure(message, code, error);
        edit((prev) => applyImageGenFailure(prev, "failed", failure.message, !failure.retryable));
      } finally {
        if (abortRef.current === abort) abortRef.current = null;
        generatingRef.current = false;
        setGenerating(false);
      }
    },
    [
      isOffline,
      onOfflineBlocked,
      ensureChatId,
      uploadReference,
      describeFailure,
      editThread,
      newMessageCountRef,
      onScrollToLatest,
      onOpenUpgrade,
      feedback,
      t,
    ],
  );

  const cancel = useCallback(() => {
    if (!generatingRef.current && !abortRef.current) return;
    userCancelRef.current = true;
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  // Every message row takes `retry`: it keeps one identity, or each chat screen render
  // (submitPrompt is rebuilt with its callers' callbacks) redrew every visible row.
  const submitRef = useLatestRef(submitPrompt);
  const retry = useCallback(() => {
    const last = lastSubmitRef.current;
    if (!last || generatingRef.current) return;
    void submitRef.current(last);
  }, [submitRef]);

  return {
    generating,
    submitPrompt,
    cancel,
    retry,
  };
}
