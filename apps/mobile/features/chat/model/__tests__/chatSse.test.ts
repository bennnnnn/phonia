import { parseSseChunk, shouldAbortPriorSse, streamChatMessageSse } from "@/features/chat/model/sse";
import { notifyUnauthorized, requestSse } from "@/lib/api/client";

jest.mock("@/lib/config", () => ({
  getApiUrl: () => "https://api.test",
}));

jest.mock("@/lib/deviceTimezone", () => ({
  getDeviceTimezone: () => "UTC",
}));

// Mock requestSse (the lib/api boundary helper) so the test verifies chatSse
// routes through it and handles the Response. The 401→refresh→retry behaviour
// lives in requestRaw (tested separately), not in chatSse anymore.
jest.mock("@/lib/api/client", () => ({
  requestSse: jest.fn(),
  notifyUnauthorized: jest.fn(),
  refreshAccessToken: jest.fn(),
}));

describe("parseSseChunk", () => {
  it("parses complete SSE frames and keeps trailing partial buffer", () => {
    const { events, rest } = parseSseChunk(
      'data: {"type":"token","content":"hi"}\n\ndata: {"type":"stream_end"}\n\ndata: {"type":"tok',
    );
    expect(events).toEqual([
      { type: "token", content: "hi" },
      { type: "stream_end" },
    ]);
    expect(rest).toBe('data: {"type":"tok');
  });

  it("reads a done event in today's shape and in the typed one alike", () => {
    // Today's server bytes (pinned by the API's test_stream_event_parity.py).
    const today =
      '{"type":"done","message_id":"m1","todos_sync":"1","search_sources":"[{\\"title\\": \\"Moon\\", \\"url\\": \\"https://example.com\\", \\"snippet\\": \\"Orbit.\\"}]","resolved_model":"smart-chat"}';
    const sources = [{ title: "Moon", url: "https://example.com", snippet: "Orbit." }];
    const typed = JSON.stringify({
      type: "done",
      message_id: "m1",
      todos_changed: true,
      search_sources: sources,
      resolved_model: "smart-chat",
    });
    const { events } = parseSseChunk(`data: ${today}\n\ndata: ${typed}\n\n`);
    const done = {
      type: "done",
      message_id: "m1",
      todos_changed: true,
      search_sources: sources,
      resolved_model: "smart-chat",
    };
    expect(events).toEqual([done, done]);
  });
});

describe("shouldAbortPriorSse", () => {
  it("aborts only when replacing a stream in the same chat", () => {
    expect(shouldAbortPriorSse("chat-a", "chat-a")).toBe(true);
    expect(shouldAbortPriorSse("chat-a", "chat-b")).toBe(false);
    expect(shouldAbortPriorSse(null, "chat-b")).toBe(false);
  });
});

const makeOkStream = (payload: string) =>
  ({
    ok: true,
    status: 200,
    body: {
      getReader: () => ({
        releaseLock: jest.fn(),
        read: jest
          .fn()
          .mockResolvedValueOnce({
            done: false,
            value: new TextEncoder().encode(payload),
          })
          .mockResolvedValueOnce({ done: true, value: undefined }),
      }),
    },
  }) as unknown as Response;

describe("streamChatMessageSse routes through lib/api requestSse", () => {
  const requestSseMock = requestSse as jest.MockedFunction<typeof requestSse>;
  const unauthorizedMock = notifyUnauthorized as jest.MockedFunction<typeof notifyUnauthorized>;

  beforeEach(() => {
    requestSseMock.mockReset();
    unauthorizedMock.mockReset();
  });

  it("calls requestSse with the send path, token, and body", async () => {
    requestSseMock.mockResolvedValueOnce(makeOkStream('data: {"type":"done"}\n\n'));
    const events: unknown[] = [];
    await streamChatMessageSse({
      token: "tok",
      chatId: "chat-1",
      content: "hi",
      onEvent: (e) => events.push(e),
    });

    expect(requestSseMock).toHaveBeenCalledTimes(1);
    const [path, token, body] = requestSseMock.mock.calls[0];
    expect(path).toBe("/chats/chat-1/messages/stream");
    expect(token).toBe("tok");
    expect(body).toMatchObject({ content: "hi", model: null });
    expect(body).not.toHaveProperty("client_message_id");
    expect(events).toEqual([{ type: "done" }]);
  });

  it("names a resent message and settles on the server's duplicate answer", async () => {
    requestSseMock.mockResolvedValueOnce(makeOkStream('data: {"type":"duplicate"}\n\n'));
    const onEvent = jest.fn();
    await streamChatMessageSse({
      token: "tok", chatId: "chat-1", content: "hi", clientMessageId: "name-1", onEvent,
    });
    expect(requestSseMock.mock.calls[0][2]).toMatchObject({ content: "hi", client_message_id: "name-1" });
    expect(onEvent).toHaveBeenCalledWith({ type: "duplicate" });
  });

  it("surfaces401 without duplicating the network boundary sign-out notification", async () => {
    requestSseMock.mockResolvedValueOnce({
      ok: false,
      status: 401,
      text: () => Promise.resolve("unauthorized"),
    } as Response);

    await expect(
      streamChatMessageSse({
        token: "tok",
        chatId: "chat-1",
        content: "hi",
        onEvent: () => {},
      }),
    ).rejects.toThrow();
    expect(unauthorizedMock).not.toHaveBeenCalled();
  });

  it("throws on a non-401 failure without calling notifyUnauthorized", async () => {
    requestSseMock.mockResolvedValueOnce({
      ok: false,
      status: 500,
      text: () => Promise.resolve("server error"),
    } as Response);

    await expect(
      streamChatMessageSse({
        token: "tok",
        chatId: "chat-1",
        content: "hi",
        onEvent: () => {},
      }),
    ).rejects.toThrow();
    expect(unauthorizedMock).not.toHaveBeenCalled();
  });

  it("keeps a refusal's status and code, as the socket's error frame names it", async () => {
    const body = { detail: { code: "unavailable", message: "Service temporarily unavailable." } };
    requestSseMock.mockResolvedValueOnce({
      ok: false,
      status: 503,
      text: () => Promise.resolve(JSON.stringify(body)),
    } as Response);

    await expect(
      streamChatMessageSse({ token: "tok", chatId: "chat-1", content: "hi", onEvent: () => {} }),
    ).rejects.toMatchObject({ status: 503, code: "unavailable", detail: "Service temporarily unavailable." });
  });

  it("throws when the response has no body", async () => {
    requestSseMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      body: null,
    } as unknown as Response);

    await expect(
      streamChatMessageSse({
        token: "tok",
        chatId: "chat-1",
        content: "hi",
        onEvent: () => {},
      }),
    ).rejects.toThrow();
  });

  it("rejects a truncated response after tokens instead of leaving the composer busy", async () => {
    requestSseMock.mockResolvedValueOnce(makeOkStream(
      'data: {"type":"start"}\n\ndata: {"type":"token","content":"partial"}\n\n',
    ));
    const onEvent = jest.fn();
    await expect(streamChatMessageSse({
      token: "tok", chatId: "chat-1", content: "hi", onEvent,
    })).rejects.toThrow("before completion");
    expect(onEvent).toHaveBeenCalledWith({ type: "token", content: "partial" });
  });

  it("requires saved completion even after stream_end", async () => {
    requestSseMock.mockResolvedValueOnce(makeOkStream('data: {"type":"stream_end"}\n\n'));
    await expect(streamChatMessageSse({
      token: "tok", chatId: "chat-1", content: "hi", onEvent: jest.fn(),
    })).rejects.toThrow("before completion");
  });

  it("accepts error completion and CRLF framed streams", async () => {
    requestSseMock.mockResolvedValueOnce(makeOkStream(
      'data: {"type":"start"}\r\n\r\ndata: {"type":"error","message":"busy"}\r\n\r\n',
    ));
    const onEvent = jest.fn();
    await streamChatMessageSse({ token: "tok", chatId: "chat-1", content: "hi", onEvent });
    expect(onEvent.mock.calls.map(([event]) => event.type)).toEqual(["start", "error"]);
  });
});

describe("a stream's idle deadline (NET-17)", () => {
  const requestSseMock = requestSse as jest.MockedFunction<typeof requestSse>;
  const encode = (text: string) => new TextEncoder().encode(text);
  const abortError = () => Object.assign(new Error("Aborted"), { name: "AbortError" });

  /** A body that sends `chunks` at the given times, then ends or (`open`) waits until aborted. */
  function timedStream(chunks: { afterMs: number; text: string }[], { open = false } = {}) {
    requestSseMock.mockImplementationOnce(async (_path, _token, _body, signal) => {
      const queue = [...chunks];
      return {
        ok: true,
        status: 200,
        body: {
          getReader: () => ({
            releaseLock: jest.fn(),
            read: () => new Promise((resolve, reject) => {
              signal?.addEventListener("abort", () => reject(abortError()), { once: true });
              const next = queue.shift();
              if (next) setTimeout(() => resolve({ done: false, value: encode(next.text) }), next.afterMs);
              else if (!open) resolve({ done: true, value: undefined });
            }),
          }),
        },
      } as unknown as Response;
    });
  }

  beforeEach(() => {
    jest.useFakeTimers();
    requestSseMock.mockReset();
  });
  afterEach(() => jest.useRealTimers());

  it("gives up on a stream quiet for 45 s, as a drop rather than a Stop", async () => {
    timedStream([{ afterMs: 10, text: 'data: {"type":"start"}\n\n' }], { open: true });
    const onEvent = jest.fn();
    const outcome = streamChatMessageSse({ token: "tok", chatId: "chat-1", content: "hi", onEvent })
      .catch((error: unknown) => error);
    await jest.advanceTimersByTimeAsync(10 + 44_999);
    expect(onEvent).toHaveBeenCalledWith({ type: "start" });
    await jest.advanceTimersByTimeAsync(1);
    const error = await outcome;
    expect(error).toMatchObject({ message: "Chat stream went quiet" });
    expect((error as Error).name).not.toBe("AbortError");
  });

  it("keeps a quiet turn alive on keepalives, which never reach the caller", async () => {
    timedStream([
      { afterMs: 10, text: 'data: {"type":"start"}\n\n' },
      { afterMs: 40_000, text: 'data: {"type":"keepalive"}\n\n' },
      { afterMs: 40_000, text: 'data: {"type":"keepalive"}\n\n' },
      { afterMs: 40_000, text: 'data: {"type":"done","message_id":"m1"}\n\n' },
    ]);
    const onEvent = jest.fn();
    const outcome = streamChatMessageSse({ token: "tok", chatId: "chat-1", content: "hi", onEvent });
    await jest.advanceTimersByTimeAsync(120_010);
    await expect(outcome).resolves.toBeUndefined();
    expect(onEvent.mock.calls.map(([event]) => event.type)).toEqual(["start", "done"]);
  });

  it("ends quietly when only the follow-ups are late after done", async () => {
    timedStream([
      { afterMs: 10, text: 'data: {"type":"start"}\n\n' },
      { afterMs: 10, text: 'data: {"type":"done","message_id":"m1"}\n\n' },
    ], { open: true });
    const outcome = streamChatMessageSse({ token: "tok", chatId: "chat-1", content: "hi", onEvent: jest.fn() });
    await jest.advanceTimersByTimeAsync(45_100);
    await expect(outcome).resolves.toBeUndefined();
  });

  it("still reads a Stop as a cancel", async () => {
    timedStream([{ afterMs: 10, text: 'data: {"type":"start"}\n\n' }], { open: true });
    const stop = new AbortController();
    const outcome = streamChatMessageSse({
      token: "tok", chatId: "chat-1", content: "hi", onEvent: jest.fn(), signal: stop.signal,
    }).catch((error: unknown) => error);
    await jest.advanceTimersByTimeAsync(1_000);
    stop.abort();
    await expect(outcome).resolves.toMatchObject({ name: "AbortError" });
  });
});
