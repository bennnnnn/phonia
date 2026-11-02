import { useCallback, useEffect, useRef, useState } from "react";
import { chatsApi } from "@/api/chats";
import { streamMessage, streamRegenerate } from "@/api/stream";
import type { Message, StreamEvent } from "@/api/types";
import {
  parseSearchSourcesFromMarkdown,
  parseSearchSourcesJson,
  stripSearchSourcesFromContent,
} from "@/lib/assistantMarkdown";

const STREAMING_ID = "streaming";

type DoneEvent = Extract<StreamEvent, { type: "done" }>;

function settleStreamingMessage(prev: Message[], event: DoneEvent): Message[] {
  return prev.map((m) => {
    if (m.id !== STREAMING_ID) return m;
    const raw = event.final_content ?? m.content;
    const fromEvent = parseSearchSourcesJson(event.search_sources ?? "");
    const sources =
      fromEvent.length > 0
        ? fromEvent
        : parseSearchSourcesFromMarkdown(raw);
    return {
      ...m,
      id: event.message_id ?? `msg-${Date.now()}`,
      content: stripSearchSourcesFromContent(raw),
      search_sources: sources.length > 0 ? sources : undefined,
      model: event.resolved_model ?? null,
    };
  });
}

export function useChat(token: string, chatId: string | null) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [statusPhase, setStatusPhase] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Load messages when the chat changes.
  useEffect(() => {
    if (!chatId || !token) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    chatsApi
      .listMessages(token, chatId, { limit: 100 })
      .then((page) => {
        if (!cancelled) setMessages(page.messages);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load chat");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, chatId]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
    setStatusPhase(null);
  }, []);

  const handleStreamEvent = useCallback((event: StreamEvent) => {
    switch (event.type) {
      case "start":
      case "reasoning":
        // Reasoning is not the answer; the status phase already covers work in progress.
        break;
      case "status":
        setStatusPhase(event.detail ?? event.phase);
        break;
      case "token":
        setMessages((previous) =>
          previous.map((message) =>
            message.id === STREAMING_ID
              ? { ...message, content: message.content + event.content }
              : message,
          ),
        );
        break;
      case "stream_end":
        setStatusPhase(null);
        break;
      case "done":
        setMessages((previous) => settleStreamingMessage(previous, event));
        break;
      case "error":
        setError(event.message);
        setMessages((previous) =>
          previous.filter((message) => message.id !== STREAMING_ID),
        );
        break;
    }
  }, []);

  const handleStreamError = useCallback((streamError: Error) => {
    setError(streamError.message);
  }, []);

  const send = useCallback(
    async (content: string, model = "auto") => {
      if (!chatId || !token || !content.trim() || streaming) return;
      setError(null);
      setStatusPhase(null);
      const userMessage: Message = {
        id: `local-${Date.now()}`,
        role: "user",
        content,
        model: null,
        created_at: new Date().toISOString(),
      };
      const assistantPlaceholder: Message = {
        id: STREAMING_ID,
        role: "assistant",
        content: "",
        model: null,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMessage, assistantPlaceholder]);
      setStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;
      try {
        await streamMessage(
          token,
          chatId,
          { content, model, client_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone },
          {
            onEvent: handleStreamEvent,
            onError: handleStreamError,
          },
          controller.signal,
        );
      } catch (e) {
        if (!controller.signal.aborted) {
          setError(e instanceof Error ? e.message : "Stream failed");
        }
      } finally {
        setStreaming(false);
        setStatusPhase(null);
        abortRef.current = null;
      }
    },
    [token, chatId, streaming, handleStreamEvent, handleStreamError],
  );

  const regenerate = useCallback(
    async (model = "auto") => {
      if (!chatId || !token || streaming) return;
      setError(null);
      setStatusPhase(null);
      // Drop the last assistant turn; the regenerate stream replaces it.
      setMessages((prev) => {
        const next = [...prev];
        // Remove trailing assistant message(s) back to the last user turn.
        while (next.length > 0 && next[next.length - 1].role === "assistant") {
          next.pop();
        }
        next.push({
          id: STREAMING_ID,
          role: "assistant",
          content: "",
          model: null,
          created_at: new Date().toISOString(),
        });
        return next;
      });
      setStreaming(true);
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        await streamRegenerate(
          token,
          chatId,
          { model, client_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone },
          {
            onEvent: handleStreamEvent,
            onError: handleStreamError,
          },
          controller.signal,
        );
      } catch (e) {
        if (!controller.signal.aborted) {
          setError(e instanceof Error ? e.message : "Regenerate failed");
        }
      } finally {
        setStreaming(false);
        setStatusPhase(null);
        abortRef.current = null;
      }
    },
    [token, chatId, streaming, handleStreamEvent, handleStreamError],
  );

  return {
    messages,
    loading,
    streaming,
    statusPhase,
    error,
    send,
    stop,
    regenerate,
  };
}
