import { memo, useCallback, useMemo } from "react";

import { useStreamingDraft } from "@/features/chat/context/StreamingDraftContext";
import { MessageBubble } from "@/features/chat/components/MessageBubble";
import { MessageRowErrorBoundary } from "@/features/chat/components/MessageRowErrorBoundary";
import { StreamSilenceHint } from "@/features/chat/components/StreamSilenceHint";
import { placeLiveEmoji } from "@/features/chat/model/emojiPlacement";
import { useStreamSilence } from "@/features/chat/hooks/useStreamSilence";
import type { Message } from "@/lib/api";
import { messageListKey } from "@/lib/messageListLayout";

type Props = {
  item: Message;
  /** Content of the immediately preceding user message, when `item` is the assistant reply to it. */
  priorUserText: string | null;
  /** Content of the user message right after this reply: what answered its clarify card. */
  nextUserText?: string | null;
  /**
   * Whether THIS row's own output depends on the active stream state — see
   * streamVisualActiveForRow. Always the real streaming/finalizing value for
   * user rows and the last-assistant row; a stable `false` for every other
   * assistant row, so this row doesn't re-render when a turn starts/ends.
   */
  streamVisualActive: boolean;
  /**
   * The reply streaming into this row (or the picture being made for it): it
   * draws the live draft. The same row goes on drawing the saved reply when
   * the turn ends, so nothing in it is created again.
   */
  live?: boolean;
  /** The user's emoji setting: the draft streams as the saved reply will read. */
  emojiUse?: string;
  /** When true, show the image-generation status label instead of chat stream draft. */
  imageGenPending?: boolean;
  lastAssistantId: string | null;
  selectedModel: string;
  highlightedMessageId: string | null;
  sendingMessageId: string | null;
  onRegenerate: (model: string) => void;
  regenerating?: boolean;
  onFeedback: (messageId: string, next: "up" | "down" | null) => void;
  onRetryImageGen?: () => void;
};

export const ChatMessageRow = memo(function ChatMessageRow({
  item,
  priorUserText,
  nextUserText = null,
  streamVisualActive,
  live = false,
  emojiUse,
  imageGenPending = false,
  lastAssistantId,
  selectedModel,
  highlightedMessageId,
  sendingMessageId,
  onRegenerate,
  regenerating = false,
  onFeedback,
  onRetryImageGen,
}: Props) {
  // Already throttled once at the store→UI boundary (useStreamingDraft) —
  // read directly; a second throttle here would only add latency.
  const streamingDraft = useStreamingDraft(live);
  // The server keeps the emoji setting on the saved reply; the draft keeps it too, or a
  // "Hey bini 👋" lost its wave when the saved reply replaced it.
  const liveContent = useMemo(
    () => placeLiveEmoji(streamingDraft?.content, emojiUse, priorUserText),
    [emojiUse, priorUserText, streamingDraft?.content],
  );
  const generating = live && streamVisualActive;
  const isLastAssistant = item.role === "assistant" && item.id === lastAssistantId;

  const handleRegenerate = useCallback(() => {
    onRegenerate(selectedModel);
  }, [onRegenerate, selectedModel]);
  const stalled = useStreamSilence(liveContent?.length ?? 0, generating && !imageGenPending);

  return (
    <MessageRowErrorBoundary resetKey={messageListKey(item)}>
      <MessageBubble
        message={item}
        priorUserText={priorUserText}
        nextUserText={nextUserText}
        isGenerating={generating}
        liveContent={liveContent}
        liveSearchSources={streamingDraft?.search_sources}
        streamStatus={imageGenPending ? "image_gen" : streamingDraft?.status}
        streamStatusDetail={imageGenPending ? undefined : streamingDraft?.statusDetail}
        streamStatusStartedAt={imageGenPending ? undefined : streamingDraft?.statusStartedAt}
        isLastAssistant={isLastAssistant}
        onRegenerate={
          isLastAssistant && !streamVisualActive && !item.image_gen_failure
            ? handleRegenerate
            : undefined
        }
        regenerating={isLastAssistant && regenerating}
        onRetryImageGen={
          item.image_gen_failure && !item.image_gen_refused ? onRetryImageGen : undefined
        }
        onFeedback={onFeedback}
        highlighted={item.id === highlightedMessageId}
        isSending={item.id === sendingMessageId}
      />
      {stalled ? <StreamSilenceHint /> : null}
    </MessageRowErrorBoundary>
  );
});
