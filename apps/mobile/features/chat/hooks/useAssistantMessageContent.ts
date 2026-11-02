import { useMemo } from "react";

import type { Message } from "@/lib/api";
import {
  deriveAssistantMessageContent,
  type AssistantMessageContent,
} from "@/lib/markdown/assistantMessageContent";
import { isServerPresentedRow } from "@/lib/markdown/presentation";
import { isFreshStreamRenderKey } from "@/lib/messageListLayout";

type Options = {
  message: Pick<Message, "id" | "content" | "search_sources" | "renderKey" | "created_at">;
  liveContent?: string;
  liveSearchSources?: Message["search_sources"];
  priorUserText?: string | null;
  layoutFrozen: boolean;
  isGenerating: boolean;
  isUser: boolean;
};

export function useAssistantMessageContent({
  message,
  liveContent,
  liveSearchSources,
  priorUserText = null,
  layoutFrozen,
  isGenerating,
  isUser,
}: Options): AssistantMessageContent & { content: string; markdownPresented: boolean } {
  const content = liveContent ?? message.content;

  // Streaming input is already throttled once at the draft→UI boundary
  // (useStreamingDraft, ~32ms), so derive runs straight off the incoming
  // content — a second throttle here would only add latency. The expensive
  // fence parsers defer themselves until the stream settles (see
  // deriveAssistantMessageContent).
  const derived = useMemo(
    () =>
      deriveAssistantMessageContent({
        content,
        layoutFrozen,
        isUser,
        priorUserText,
        storedSearchSources: message.search_sources,
        liveSearchSources,
        messageId: message.id,
        isGenerating,
        renderKey: message.renderKey,
      }),
    [
      content,
      layoutFrozen,
      isUser,
      priorUserText,
      message.search_sources,
      liveSearchSources,
      message.id,
      isGenerating,
      message.renderKey,
    ],
  );

  return {
    ...derived,
    content,
    hasContent: content.trim().length > 0,
    // A saved row the server presented is shown as saved; a live draft is the
    // model's own text and the phone presents it. So is the reply that just
    // streamed in here, saved or not: it goes on being drawn as it streamed,
    // and nothing in it moves when the turn ends. The trade-off: after the
    // server cut-over that row shows the phone's presentation of the saved
    // text until the chat is opened again; both follow the one contract
    // (docs/fixtures/presentation_cases.json), so they agree.
    markdownPresented:
      liveContent === undefined &&
      !isUser &&
      !isFreshStreamRenderKey(message.renderKey) &&
      isServerPresentedRow(message),
  };
}
