import { requestRaw } from "@/api/client";
import type { StreamEvent } from "@/api/types";

export type StreamHandlers = {
  onEvent: (event: StreamEvent) => void;
  onError?: (error: Error) => void;
};

// Parse an SSE text stream (`data: {json}\n\n`) into StreamEvent objects.
// The API emits one JSON payload per `data:` line (see chat_stream._sse).
async function* parseSse(
  reader: ReadableStreamDefaultReader<Uint8Array>,
): AsyncGenerator<StreamEvent> {
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE events are separated by a blank line. The API uses `\n\n`.
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const rawEvent = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const line = rawEvent.startsWith("data: ")
        ? rawEvent.slice(6)
        : rawEvent.replace(/^data:\s?/, "");
      if (!line.trim()) continue;
      try {
        yield JSON.parse(line) as StreamEvent;
      } catch {
        // Skip a malformed chunk rather than killing the stream.
      }
    }
  }
}

// Start a chat turn over SSE. Returns a controller so the caller can cancel
// generation (abort the fetch). Mirrors the mobile WS `message` frame.
export async function streamMessage(
  token: string,
  chatId: string,
  body: { content: string; model?: string; client_timezone?: string },
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  await runStream(
    `/chats/${chatId}/messages/stream`,
    token,
    body,
    handlers,
    signal,
  );
}

// Regenerate the last assistant turn over SSE.
export async function streamRegenerate(
  token: string,
  chatId: string,
  body: { model?: string; client_timezone?: string },
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  await runStream(
    `/chats/${chatId}/regenerate/stream`,
    token,
    body,
    handlers,
    signal,
  );
}

async function runStream(
  path: string,
  token: string,
  body: Record<string, unknown>,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await requestRaw(
    path,
    token,
    {
      method: "POST",
      signal,
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify(body),
    },
    true,
    // The stream itself must not be subject to the 30s request timeout —
    // generation can run for minutes. requestRaw applies the timeout to the
    // fetch, but the body stream is read separately below.
    60_000,
  );
  if (!response.ok || !response.body) {
    const text = await response.text().catch(() => "");
    throw new Error(text || `Stream failed: ${response.status}`);
  }
  try {
    for await (const event of parseSse(response.body.getReader())) {
      handlers.onEvent(event);
      if (event.type === "done" || event.type === "error") return;
    }
  } catch (error) {
    if (signal?.aborted) return;
    handlers.onError?.(error instanceof Error ? error : new Error(String(error)));
  }
}
