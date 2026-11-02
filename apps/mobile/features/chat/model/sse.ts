import type { ClientGeo } from "@/features/chat/model/clientGeo";
import { clientGeoWsFields } from "@/features/chat/model/clientGeo";
import { markChatTtftTransport } from "@/features/chat/model/latency";
import { getDeviceTimezone } from "@/lib/deviceTimezone";
import { requestSse } from "@/lib/api/client";
import { ApiRequestError } from "@/lib/api/errorBody";
import { responseRequestId } from "@/lib/api/requestId";
import { parseChatWsPayload } from "@/features/chat/model/socketReduce";
import { STREAM_IDLE_TIMEOUT_MS } from "@/features/chat/model/wsConnect";

export type ChatSsePayload = NonNullable<ReturnType<typeof parseChatWsPayload>>;

/** Abort the previous SSE only when replacing a stream in the same chat.
 * New chat / leave must not abort — Stop is the only hard cancel (WS drains
 * on disconnect; SSE Stop is abort, so a chat switch must leave the fetch
 * running). */
export function shouldAbortPriorSse(
  previousChatId: string | null,
  nextChatId: string | null,
): boolean {
  return previousChatId != null && nextChatId != null && previousChatId === nextChatId;
}

type StreamChatSseClient = {
  token: string;
  chatId: string;
  model?: string | null;
  clientGeo?: ClientGeo | null;
  signal?: AbortSignal;
  /** Optimistic user-message id for the send that opened this stream. */
  ttftTurnId?: string | null;
  onEvent: (payload: ChatSsePayload) => void;
};

type StreamChatMessageOptions = StreamChatSseClient & {
  content: string;
  attachmentIds?: string[];
  /** The message's name from its socket send: the server runs one turn per name. */
  clientMessageId?: string;
};

/** The last event of a stream; `duplicate`: an earlier send of the message took the turn. */
const TERMINAL_EVENT_TYPES = new Set(["done", "error", "duplicate"]);

async function streamChatSseRequest(
  path: string,
  options: StreamChatSseClient,
  extraBody: Record<string, unknown> = {},
): Promise<void> {
  // If WS failed over, attribute this send's sample to SSE. A leftover stream
  // from another chat must not stamp the active send; regenerate has no id.
  markChatTtftTransport(options.ttftTurnId, "sse");
  // Route through lib/api's requestSse so this stream shares the REST path's
  // 401→refresh→retry behaviour and the lib/api boundary stays the single
  // network egress point (no bare fetch(getApiUrl()...) here).
  const body = {
    ...extraBody,
    model: options.model ?? null,
    client_timezone: getDeviceTimezone(),
    ...clientGeoWsFields(options.clientGeo),
  };
  // Stop aborts this stream; so does a silence past the idle deadline, which then
  // fails it as a drop (not a Stop) so the caller reloads the chat for the reply.
  const stream = new AbortController();
  const forwardStop = () => stream.abort();
  options.signal?.addEventListener("abort", forwardStop, { once: true });
  if (options.signal?.aborted) stream.abort();
  let idleTimer: ReturnType<typeof setTimeout> | null = null;
  let wentQuiet = false;
  const awaitNextChunk = () => {
    if (idleTimer) clearTimeout(idleTimer);
    idleTimer = setTimeout(() => {
      wentQuiet = true;
      stream.abort();
    }, STREAM_IDLE_TIMEOUT_MS);
  };

  const turn = { ended: false };
  try {
    const response = await requestSse(path, options.token, body, stream.signal);
    await readSseBody(response, options, awaitNextChunk, turn);
  } catch (error) {
    // After `done` or `error` the stream only carries follow-up questions.
    if (wentQuiet && turn.ended) return;
    if (wentQuiet) throw new Error("Chat stream went quiet");
    throw error;
  } finally {
    if (idleTimer) clearTimeout(idleTimer);
    options.signal?.removeEventListener("abort", forwardStop);
  }
}

async function readSseBody(
  response: Response,
  options: StreamChatSseClient,
  awaitNextChunk: () => void,
  turn: { ended: boolean },
): Promise<void> {
  // A refusal keeps its status and code (`unavailable`, `consent_required`): the chat says what
  // the socket's error frame would, not "Couldn't reach the server".
  if (!response.ok) {
    throw new ApiRequestError(response.status, await response.text(), null, responseRequestId(response));
  }

  if (!response.body) {
    throw new Error("SSE response has no body");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const deliver = (events: ChatSsePayload[]) => {
    for (const event of events) {
      if (event.type === "keepalive") continue;
      if (TERMINAL_EVENT_TYPES.has(event.type)) turn.ended = true;
      options.onEvent(event);
    }
  };

  try {
    while (true) {
      awaitNextChunk();
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parsed = parseSseChunk(buffer);
      buffer = parsed.rest;
      deliver(parsed.events);
    }

    buffer += decoder.decode();
    if (buffer.trim()) {
      deliver(parseSseChunk(`${buffer}\n\n`).events);
    }
    // EOF only closes the transport. Without done/error the turn may have
    // been cut off before persistence, and the UI must recover its busy state.
    if (!turn.ended) throw new Error("Chat stream ended before completion");
  } finally {
    reader.releaseLock();
  }
}

export function parseSseChunk(buffer: string): { events: ChatSsePayload[]; rest: string } {
  const events: ChatSsePayload[] = [];
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";
  for (const part of parts) {
    for (const line of part.split("\n")) {
      if (!line.startsWith("data: ")) continue;
      const payload = parseChatWsPayload(line.slice(6));
      if (payload) events.push(payload);
    }
  }
  return { events, rest };
}

export async function streamChatMessageSse(
  options: StreamChatMessageOptions,
): Promise<void> {
  await streamChatSseRequest(`/chats/${options.chatId}/messages/stream`, options, {
    content: options.content,
    attachment_ids: options.attachmentIds ?? [],
    ...(options.clientMessageId ? { client_message_id: options.clientMessageId } : {}),
  });
}

export async function streamChatRegenerateSse(
  options: StreamChatSseClient,
): Promise<void> {
  await streamChatSseRequest(`/chats/${options.chatId}/regenerate/stream`, options);
}
