import React, { useEffect, useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { SettingsProposalCard } from "@/features/chat/components/SettingsProposalCard";
import { ReminderProposalCard } from "@/features/todos/components/ReminderProposalCard";
import { TodoLinkButton } from "@/features/todos/components/TodoLinkButton";
import { PlacesListBlock } from "@/components/rich/PlacesListBlock";
import { UserMessageContent } from "@/features/chat/components/UserMessageContent";
import { ChatMessageImageStrip } from "@/features/attachments/components/ChatMessageImageStrip";
import { ImageGenPlaceholder } from "@/features/images/components/ImageGenPlaceholder";
import { ActionShimmer } from "@/ui/feedback/ActionShimmer";
import { SearchSourcesStack } from "@/features/chat/components/SearchSourcesStack";
import { LazyCircularClockBlock } from "@/components/rich/LazyHeavyRich";
import { ClarifyMessageScope } from "@/components/rich/clarifyContext";
import { ReplyMarkdown } from "@/components/markdown/ReplyMarkdown";
import { MarkdownErrorBoundary } from "@/features/chat/components/MarkdownErrorBoundary";
import { RecallTypingIndicator } from "@/features/chat/components/RecallTypingIndicator";
import { StreamProgressLabel } from "@/features/chat/components/StreamProgressLabel";
import { AssistantMessageScope } from "@/features/drafts/context/emailDraftPersist";
import {
  AssistantActions,
  MESSAGE_ACTION_ROW_HEIGHT,
  UserActions,
} from "@/features/chat/components/MessageActions";
import { Message } from "@/lib/api";
import { tap } from "@/lib/haptics";
import { SENDING_LABEL_DELAY_MS } from "@/features/chat/model/messageLogic";
import { useAssistantMessageContent } from "@/features/chat/hooks/useAssistantMessageContent";
import { parseUserMessageContent } from "@/lib/messageAttachments";
import { messageListKey } from "@/lib/messageListLayout";
import {
  isProgressStreamPhase,
  shouldShowWaitingIndicator,
  useRotatingStreamStatus,
} from "@/lib/streamStatusLabel";
import { Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";
import { useTranslation } from "react-i18next";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";

type Props = {
  message: Message;
  priorUserText?: string | null;
  /** The user message right after this reply: what answered its clarify card. */
  nextUserText?: string | null;
  isGenerating?: boolean;
  /** Live token stream — avoids mutating the messages array on every token. */
  liveContent?: string;
  liveSearchSources?: Message["search_sources"];
  streamStatus?: string;
  streamStatusDetail?: string;
  /** When `streamStatus`'s phase began (phone clock); its progress label counts from it. */
  streamStatusStartedAt?: number;
  isLastAssistant?: boolean;
  onRegenerate?: () => void;
  regenerating?: boolean;
  onFeedback?: (messageId: string, feedback: "up" | "down" | null) => void;
  highlighted?: boolean;
  isSending?: boolean;
  onRetryImageGen?: () => void;
};

function userMessageCopyText(content: string): string {
  const caption = parseUserMessageContent(content).caption.trim();
  return caption || content.trim();
}

export const MessageBubble = React.memo(function MessageBubble({
  message,
  priorUserText = null,
  nextUserText = null,
  isGenerating = false,
  liveContent,
  liveSearchSources,
  streamStatus,
  streamStatusDetail,
  streamStatusStartedAt,
  isLastAssistant,
  onRegenerate,
  regenerating = false,
  onFeedback,
  highlighted = false,
  isSending = false,
  onRetryImageGen,
}: Props) {
  const theme = useTheme();
  const { t } = useTranslation();
  const b = useMemo(() => makeStyles(theme), [theme]);
  const [showSendingLabel, setShowSendingLabel] = useState(false);
  const [showUserActions, setShowUserActions] = useState(false);
  const isUser = message.role === "user";
  const isStreaming = isGenerating;
  // A reply's chrome (sources, cards, places, pictures) waits for its text to
  // finish. The row is the same one before and after, so it lands in the same
  // frame as the action row, and the list follows the growth in that frame.
  const layoutFrozen = isStreaming;

  const userCopyText = isUser ? userMessageCopyText(message.content) : "";
  const canRevealUserActions = isUser && userCopyText.length > 0;

  useEffect(() => {
    if (!isSending) {
      setShowSendingLabel(false);
      return;
    }
    const timer = setTimeout(() => setShowSendingLabel(true), SENDING_LABEL_DELAY_MS);
    return () => clearTimeout(timer);
  }, [isSending]);

  useEffect(() => {
    setShowUserActions(false);
  }, [message.id]);

  const assistant = useAssistantMessageContent({
    message,
    liveContent,
    liveSearchSources,
    priorUserText,
    layoutFrozen,
    isGenerating,
    isUser,
  });
  const {
    hasContent,
    showActionSlot,
    actionsReady,
    showLiveClock,
    clockTimezone,
    settingsProposals,
    showSettingsProposals,
    reminderProposals,
    showReminderProposals,
    showTodoLink,
    places,
    showPlaces,
    images,
    showImages,
    markdownContent,
    hasMarkdown,
    showSearchSources,
    searchSources,
    markdownStreamMode,
    markdownResetKey,
    markdownPresented,
  } = assistant;

  const imageGenFailure = message.image_gen_failure;
  const showWaitingIndicator = shouldShowWaitingIndicator({ isStreaming, hasContent });
  const statusLabel = useRotatingStreamStatus(
    streamStatus,
    showWaitingIndicator,
    t,
    streamStatusDetail,
  );
  // Generated image with no prose — copy, read aloud and regenerate are noise.
  const imageOnlyActions =
    showImages && !hasMarkdown && !showLiveClock && !showSettingsProposals && !showPlaces;

  return (
    <View style={[b.row, isUser ? b.userRow : b.assistantRow, highlighted && b.rowHighlighted]}>
      {isUser ? (
        <View style={b.userColumn}>
          <Pressable
            onLongPress={() => {
              if (!canRevealUserActions) return;
              tap();
              setShowUserActions(true);
            }}
            onPress={() => {
              if (showUserActions) setShowUserActions(false);
            }}
            delayLongPress={350}
            // Open to a screen reader, so a photo, a file or a link inside stays reachable.
            accessible={false}
          >
            <UserMessageContent
              message={message}
              actionsHint={canRevealUserActions ? t("chat.user_message_actions_hint") : undefined}
            />
          </Pressable>
          {showSendingLabel ? (
            <ActionShimmer
              label={t("chat.sending")}
              compact
              color={theme.primary}
              style={b.sendingStatus}
              textStyle={b.sendingLabel}
              testID={`sending-${message.id}`}
            />
          ) : null}
          {showUserActions ? (
            <UserActions
              content={userCopyText}
              theme={theme}
            />
          ) : null}
        </View>
      ) : (
        <View style={b.assistantBubble}>
          {imageGenFailure ? (
              <View style={b.imageGenWaitingWrap}>
                <ImageGenPlaceholder
                  outcome={imageGenFailure}
                  statusText={
                    imageGenFailure === "canceled"
                      ? t("chat.image_gen_canceled")
                      : message.image_gen_error?.trim() || t("chat.image_gen_failed")
                  }
                  onRetry={onRetryImageGen}
                />
              </View>
            ) : showWaitingIndicator ? (
              streamStatus === "image_gen" ? (
                // The card owns its stage line, timed to its progress estimate.
                <View style={b.imageGenWaitingWrap}>
                  <ImageGenPlaceholder />
                </View>
              ) : (
                <View style={b.waitingWrap}>
                  <RecallTypingIndicator phase={streamStatus} />
                  {streamStatus && isProgressStreamPhase(streamStatus) ? (
                    <StreamProgressLabel
                      phase={streamStatus}
                      startedAt={streamStatusStartedAt}
                      style={b.statusLabel}
                    />
                  ) : statusLabel ? (
                    <Text style={b.statusLabel}>{statusLabel}</Text>
                  ) : null}
                </View>
              )
            ) : null}
            {showImages ? <ChatMessageImageStrip images={images} /> : null}
            {showLiveClock ? (
              <LazyCircularClockBlock content={clockTimezone} />
            ) : null}
            {hasMarkdown ? (
              <AssistantMessageScope messageId={message.id}>
                <ClarifyMessageScope latest={Boolean(isLastAssistant)} nextUserText={nextUserText}>
                  <MarkdownErrorBoundary
                    resetKey={markdownResetKey}
                    content={markdownContent}
                  >
                    {/* A row reused for another message starts afresh; renderKey survives `done`. */}
                    <ReplyMarkdown
                      key={messageListKey(message)}
                      content={markdownContent}
                      streaming={markdownStreamMode}
                      presented={markdownPresented}
                      userText={priorUserText}
                      sources={searchSources}
                    />
                  </MarkdownErrorBoundary>
                </ClarifyMessageScope>
              </AssistantMessageScope>
            ) : null}
            {isStreaming && hasContent && streamStatus ? (
              // Work after the last token (the answer check): the reply looks
              // finished but has not saved yet.
              <StreamProgressLabel
                phase={streamStatus}
                startedAt={streamStatusStartedAt}
                style={b.afterTextStatus}
              />
            ) : null}
            {message.generationStopped || message.completion || message.replyNotSaved ? (
              <Text style={b.stoppedFooter}>
                {t(message.replyNotSaved ? "chat.reply_not_saved" : "chat.generation_stopped")}
              </Text>
            ) : null}
            {showPlaces ? <PlacesListBlock places={places} /> : null}
            {showSettingsProposals
              ? settingsProposals.map((proposal, index) => (
                  <SettingsProposalCard
                    key={`${proposal.proposal_id}-${index}`}
                    proposal={proposal}
                    disabled={!isLastAssistant}
                  />
                ))
              : null}
            {showReminderProposals
              ? reminderProposals.map((proposal) => (
                  <ReminderProposalCard key={proposal.proposalId} proposal={proposal} />
                ))
              : null}
            {showTodoLink ? <TodoLinkButton /> : null}
            {showSearchSources ? <SearchSourcesStack sources={searchSources} /> : null}
        </View>
      )}

      {showActionSlot && actionsReady && !imageGenFailure ? (
        <View style={b.actionRowSlot}>
          <AssistantActions
            messageId={message.id}
            markdown={markdownContent}
            feedback={message.feedback ?? null}
            onFeedback={onFeedback}
            onRegenerate={isLastAssistant ? onRegenerate : undefined}
            regenerating={isLastAssistant && regenerating}
            theme={theme}
            thumbsOnly={imageOnlyActions}
          />
        </View>
      ) : null}
    </View>
  );
});

function makeStyles(t: Theme) {
  return StyleSheet.create({
    row: { marginVertical: Space.xs, paddingHorizontal: Space.md },
    rowHighlighted: {
      backgroundColor: t.primaryLight,
      borderRadius: Radius.md,
      marginHorizontal: Space.xs,
      paddingHorizontal: Space.xs,
    },
    userRow: { alignItems: "flex-end" },
    // The one width cap on a sent message (its content no longer caps again).
    userColumn: { alignItems: "flex-end", maxWidth: "82%" },
    sendingStatus: {
      marginTop: Space.xxs,
      marginRight: Space.xxs,
    },
    sendingLabel: {
      ...Type.compact,
    },
    assistantRow: { alignItems: "stretch" },
    assistantBubble: {
      maxWidth: "100%",
      backgroundColor: "transparent",
      paddingVertical: 2,
    },
    waitingWrap: {
      flexDirection: "row",
      alignItems: "center",
      gap: Space.xs,
      paddingVertical: Space.xxs,
    },
    imageGenWaitingWrap: {
      alignItems: "flex-start",
      paddingVertical: Space.xxs,
    },
    statusLabel: {
      ...Type.secondary,
      color: t.textTertiary,
    },
    afterTextStatus: {
      marginTop: Space.xs,
      ...Type.compact,
      color: t.textTertiary,
    },
    stoppedFooter: {
      marginTop: Space.xs,
      ...Type.compact,
      color: t.textTertiary,
    },
    actionRowSlot: {
      minHeight: MESSAGE_ACTION_ROW_HEIGHT,
      marginTop: 2,
    },
  });
}
