import { Markdown } from "@/components/Markdown";
import { SourcesList } from "@/components/SourcesList";
import type { Message } from "@/api/types";
import {
  parseSearchSourcesFromMarkdown,
  stripSearchSourcesFromContent,
} from "@/lib/assistantMarkdown";

export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  const isStreaming = message.id === "streaming";
  const sources =
    message.search_sources && message.search_sources.length > 0
      ? message.search_sources
      : parseSearchSourcesFromMarkdown(message.content);
  const display = isUser
    ? message.content
    : stripSearchSourcesFromContent(message.content);

  return (
    <div className={`message ${isUser ? "user" : "assistant"}`}>
      <div className="bubble">
        {isUser ? (
          <p>{message.content}</p>
        ) : (
          <>
            {isStreaming && !display.trim() ? (
              <p className="muted">…</p>
            ) : (
              <Markdown content={display} />
            )}
            <SourcesList sources={sources} />
          </>
        )}
      </div>
    </div>
  );
}
