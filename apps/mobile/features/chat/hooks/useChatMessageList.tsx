import { useCallback, useEffect, useMemo } from "react";
import { View } from "react-native";

import { useAuthOptional } from "@/contexts/AuthContext";
import { ChatMessageRow } from "@/features/chat/components/ChatMessageRow";
import { RelatedPromptLines } from "@/features/suggestions/components/RelatedPromptLines";
import { asksWithCard } from "@/lib/clarify/clarifyCard";
import type { Message } from "@/lib/api";
import {
  findLastAssistantId,
  nextUserTextFor,
  priorUserTextFor,
  streamVisualActiveForRow,
} from "@/features/chat/model/messageLogic";
import { useLatestRef } from "@/lib/latestRef";

type Options = {
  messages: Message[];
  streaming: boolean;
  finalizing: boolean;
  highlightedMessageId: string | null;
  sendingMessageId: string | null;
  setMenuVisible: React.Dispatch<React.SetStateAction<boolean>>;
  regenerateResponse: () => void | Promise<void>;
  regenerating?: boolean;
  handleFeedback: (messageId: string, next: "up" | "down" | null) => void;
  onSelectSuggestion?: (prompt: string) => void;
};

export function useChatMessageList({
  messages,
  streaming,
  finalizing,
  highlightedMessageId,
  sendingMessageId,
  setMenuVisible,
  regenerateResponse,
  regenerating = false,
  handleFeedback,
  onSelectSuggestion,
}: Options) {
  useEffect(() => {
    if (messages.length === 0) setMenuVisible(false);
  }, [messages.length, setMenuVisible]);

  const messagesRef = useLatestRef(messages);
  const emojiUse = useAuthOptional()?.user?.emoji_use;

  const lastAssistantId = useMemo(
    () => findLastAssistantId(messages),
    [messages],
  );

  const headerTitleLabel = null;

  // `regenerating` is deliberately NOT here: it flips true→false once per
  // regenerate and would change this object's identity, re-rendering every
  // row. Only the last-assistant row consumes it, so it is passed per-row in
  // renderItem instead.
  const sharedRowProps = useMemo(
    () => ({
      emojiUse,
      lastAssistantId,
      highlightedMessageId,
      sendingMessageId,
      onRegenerate: regenerateResponse,
      onFeedback: handleFeedback,
    }),
    [
      emojiUse,
      lastAssistantId,
      highlightedMessageId,
      sendingMessageId,
      regenerateResponse,
      handleFeedback,
    ],
  );

  // Read messages from a ref so feedback/refetch/done does not change
  // renderItem identity and force FlashList to revisit every visible row.
  const renderItem = useCallback(
    ({ item, index }: { item: Message; index: number }) => {
      const priorUserText = priorUserTextFor(messagesRef.current, index);
      const nextUserText = nextUserTextFor(messagesRef.current, index);
      const live = item.id === "streaming";
      const streamVisualActive = streamVisualActiveForRow(
        item.role,
        item.id,
        lastAssistantId,
        streaming,
        finalizing,
      );
      // The reply streaming in and the reply saved at `done` are one row: the
      // same elements, so the turn ending updates it instead of creating it again.
      const row = (
        <ChatMessageRow
          item={item}
          priorUserText={priorUserText}
          nextUserText={nextUserText}
          streamVisualActive={streamVisualActive}
          live={live}
          regenerating={item.id === lastAssistantId ? regenerating : false}
          {...sharedRowProps}
        />
      );

      // Every row keeps the same root <View> so the follow-up questions appearing
      // after stream end (or lastAssistantId moving to a new reply) never
      // changes the root element type — that would remount the whole bubble.
      const relatedPrompts =
        item.role === "assistant" && item.id === lastAssistantId && !asksWithCard(item.content)
          ? (item.related_prompts ?? [])
          : [];
      const showRelated =
        !streaming &&
        !finalizing &&
        relatedPrompts.length > 0 &&
        Boolean(onSelectSuggestion);
      return (
        <View>
          {row}
          {showRelated && onSelectSuggestion ? (
            <RelatedPromptLines prompts={relatedPrompts} onSelect={onSelectSuggestion} />
          ) : null}
        </View>
      );
    },
    [
      sharedRowProps,
      streaming,
      finalizing,
      lastAssistantId,
      regenerating,
      onSelectSuggestion,
      messagesRef,
    ],
  );

  return { lastAssistantId, headerTitleLabel, renderItem };
}
