import type { Message } from "@/lib/api";
import type { StreamingDraft } from "@/features/chat/model/streamingDraftStore";

/** The thread with the reply's streaming placeholder at its end (only ever one). */
export function withStreamingPlaceholder(messages: Message[], now = Date.now()): Message[] {
  if (messages.some((m) => m.id === "streaming")) return messages;
  return [
    ...messages,
    {
      id: "streaming",
      renderKey: `stream-${now}`,
      role: "assistant" as const,
      content: "",
      model: null,
      created_at: new Date(now).toISOString(),
    },
  ];
}

export function replaceStreamingMessageWithPartial(
  messages: Message[],
  partial: string,
  draft: StreamingDraft | null,
  id: string,
): Message[] {
  return messages.map((message) =>
    message.id === "streaming"
      ? {
          ...message,
          id,
          content: partial,
          search_sources: draft?.search_sources ?? message.search_sources,
          generationStopped: true,
        }
      : message,
  );
}
