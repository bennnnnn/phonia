import React from "react";
import { AccessibilityInfo, AppState } from "react-native";
import { act, cleanup, render } from "@testing-library/react-native";
import { useChat } from "@/features/chat/hooks/useChat";
import { streamChatMessageSse, streamChatRegenerateSse } from "@/features/chat/model/sse";
import { MESSAGE_PAGE_SIZE } from "@/features/chat/model/constants";
import {
  DROPPED_TURN_MAX_WAIT_MS,
  DROPPED_TURN_POLLS,
  DROPPED_TURN_PROBE_ROWS,
  DUPLICATE_TURN_POLLS,
  duplicateTurnPollMs,
  SSE_DROPPED_TURN_POLLS,
} from "@/features/chat/model/turnReconcile";
import { WS_RETRY_BASE_MS } from "@/features/chat/model/wsBackoff";
import {
  STREAM_IDLE_TIMEOUT_MS,
  WS_ACK_PROBE_MS,
  WS_CONNECT_TIMEOUT_MS,
  WS_FIRST_EVENT_TIMEOUT_MS,
  WS_FOLLOW_UPS_WAIT_MS,
  WS_PROBE_TIMEOUT_MS,
} from "@/features/chat/model/wsConnect";
import { REPLY_SAVE_GRACE_MS, type DotsTicket } from "@/features/chat/hooks/useTurnStart";
import { getStreamingDraft, resetStreamingDraftStore } from "@/features/chat/model/streamingDraftStore";
import { beginOpenedPageRead, OPENED_PAGE_WAIT_MS } from "@/features/chat/model/openedPage";
import { emitAppEvent } from "@/lib/appEvents";
import { useImageGeneration } from "@/features/images/hooks/useImageGeneration";
import { mergeOpenedPage } from "@/features/chat/model/messageMerge";

const SERVER_USER_ID = "0190a000-0000-7000-8000-000000000001";
const SERVER_REPLY_ID = "0190a000-0000-7000-8000-000000000002";

/** Let a dropped turn's reloads run out (each waits at most DROPPED_TURN_MAX_WAIT_MS). */
async function waitOutReconcile(polls = DROPPED_TURN_POLLS) {
  for (let poll = 0; poll < polls; poll += 1) {
    await act(async () => { await jest.advanceTimersByTimeAsync(DROPPED_TURN_MAX_WAIT_MS); });
  }
}

// Each poll's wait is spread at random (`droppedTurnWaitMs`); the middle of the spread
// keeps every wait at its base, so a test's clock lands where it expects.
beforeEach(() => {
  jest.spyOn(Math, "random").mockReturnValue(0.5);
  mockToken = "token";
  mockZone = "UTC";
});
afterEach(() => { jest.mocked(Math.random).mockRestore(); });

jest.mock("@/lib/api", () => ({
  chatWebSocketUrl: (id: string) => `wss://test/${id}`,
  api: { listMessages: jest.fn(), generateImage: jest.fn() },
}));
const listMessages = jest.requireMock("@/lib/api").api.listMessages as jest.Mock;
const generateImage = jest.requireMock("@/lib/api").api.generateImage as jest.Mock;
/** The phone's zone now: it moves on a flight, or in Settings, while a chat is open. */
let mockZone = "UTC";
jest.mock("@/lib/deviceTimezone", () => ({ getDeviceTimezone: () => mockZone }));
let mockClientMessageIds = 0;
jest.mock("expo-crypto", () => ({ randomUUID: () => `name-${++mockClientMessageIds}` }));
const mockNetInfoListeners = new Set<(state: object) => void>();
jest.mock("@react-native-community/netinfo", () => ({
  __esModule: true,
  default: {
    addEventListener: (listener: (state: object) => void) => {
      mockNetInfoListeners.add(listener);
      return () => mockNetInfoListeners.delete(listener);
    },
  },
}));
jest.mock("@/features/chat/model/sse", () => ({
  streamChatMessageSse: jest.fn(),
  streamChatRegenerateSse: jest.fn(),
  shouldAbortPriorSse: (previous: string, next: string) => previous === next,
}));

class FakeSocket {
  static OPEN = 1;
  static instances: FakeSocket[] = [];
  readyState = 0;
  onopen = () => {};
  onclose = () => {};
  onerror = () => {};
  onmessage = (_event: { data: string }) => {};
  send = jest.fn();
  close = jest.fn(() => { this.readyState = 3; });
  constructor(readonly url: string) { FakeSocket.instances.push(this); }
  open() { this.readyState = FakeSocket.OPEN; this.onopen(); }
  emit(payload: object) { this.onmessage({ data: JSON.stringify(payload) }); }
}

let current: ReturnType<typeof useChat>;
const onError = jest.fn();
let mockSessionGeneration = 0;
jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => mockSessionGeneration }));
// One object, as the provider keeps it.
/** The newest access token; it rotates without a render (code-health audit NET-11). */
let mockToken = "token";
const mockAccountSession = { account: "user-1:0", getToken: () => mockToken };
jest.mock("@/contexts/accountSession", () => ({
  useAccountSession: () => mockAccountSession,
}));
function Probe({ chatId, token = "token" }: { chatId: string; token?: string }) {
  const chat = useChat(token, chatId, { onError });
  React.useLayoutEffect(() => { current = chat; });
  return null;
}

async function openSocket() {
  let socket!: FakeSocket;
  await act(async () => {
    const pending = current.connect();
    socket = FakeSocket.instances[FakeSocket.instances.length - 1];
    socket.open();
    await pending;
  });
  return socket;
}

async function sendAndStream(socket: FakeSocket, text = "reply") {
  await act(async () => {
    await current.sendMessage("question");
    socket.emit({ type: "start" });
    socket.emit({ type: "token", content: text });
    jest.advanceTimersByTime(20);
  });
}

describe("useChat transport lifecycle", () => {
  const originalSocket = globalThis.WebSocket;
  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    listMessages.mockReset();
    FakeSocket.instances = [];
    mockSessionGeneration = 0;
    globalThis.WebSocket = FakeSocket as unknown as typeof WebSocket;
    resetStreamingDraftStore();
  });
  afterEach(async () => {
    await cleanup();
    jest.clearAllTimers();
    jest.useRealTimers();
    globalThis.WebSocket = originalSocket;
  });

  it("surfaces an SSE transport AbortError without replaying uncertain delivery", async () => {
    const timeout = Object.assign(new Error("request timeout"), { name: "AbortError" });
    (streamChatMessageSse as jest.Mock).mockRejectedValueOnce(timeout);
    await render(<Probe chatId="a" />);
    await act(async () => {
      const sending = current.sendMessage("possibly received");
      FakeSocket.instances[0].onerror();
      await sending;
    });
    const options = (streamChatMessageSse as jest.Mock).mock.calls[0][0];
    expect(options.signal.aborted).toBe(false);
    expect(current.streaming).toBe(false);
    expect(current.finalizing).toBe(false);
    expect(current.messages.map((message) => message.content)).toEqual(["possibly received"]);
    expect(current.rejectedSend).toBeNull();
    expect(await current.retryRejectedSend()).toBe(false);
    expect(onError).toHaveBeenCalledWith("chat.error_unreachable", undefined);
    // Even a misbehaving transport cannot revive the failed stream.
    await act(async () => {
      options.onEvent({ type: "start" });
      options.onEvent({ type: "done", message_id: "late", final_content: "late answer" });
      jest.advanceTimersByTime(5 * 60_000);
    });
    expect(current.messages.map((message) => message.content)).toEqual(["possibly received"]);
    expect(streamChatMessageSse).toHaveBeenCalledTimes(1);
  });

  it("restores the previous answer after an SSE regeneration transport AbortError", async () => {
    (streamChatRegenerateSse as jest.Mock).mockRejectedValueOnce(
      Object.assign(new Error("request timeout"), { name: "AbortError" }),
    );
    await render(<Probe chatId="a" />);
    const previous = { id: "saved", role: "assistant" as const, content: "previous answer", model: null, created_at: "now" };
    await act(async () => { current.editThread([previous], "page_refresh"); });
    await act(async () => {
      const sending = current.regenerateResponse();
      FakeSocket.instances[0].onerror();
      await sending;
    });
    expect(current.streaming).toBe(false);
    expect(current.finalizing).toBe(false);
    expect(current.messages).toEqual([previous]);
    expect(current.rejectedSend).toBeNull();
    expect(onError).toHaveBeenCalledWith("chat.error_unreachable", undefined);
    const options = (streamChatRegenerateSse as jest.Mock).mock.calls[0][0];
    await act(async () => { options.onEvent({ type: "token", content: "late answer" }); });
    expect(current.messages).toEqual([previous]);
  });

  it.each(["send", "regenerate"] as const)("keeps a real SSE Stop silent for %s", async (kind) => {
    const stream = kind === "send" ? streamChatMessageSse : streamChatRegenerateSse;
    (stream as jest.Mock).mockImplementationOnce(({ signal }) => new Promise((_resolve, reject) => {
      signal.addEventListener("abort", () => reject(Object.assign(new Error("stopped"), { name: "AbortError" })));
    }));
    await render(<Probe chatId="a" />);
    let sending!: Promise<unknown>;
    await act(async () => {
      sending = kind === "send" ? current.sendMessage("question") : current.regenerateResponse();
      FakeSocket.instances[0].onerror();
    });
    const options = (stream as jest.Mock).mock.calls[0][0];
    await act(async () => { current.stopGeneration(); await sending; });
    expect(options.signal.aborted).toBe(true);
    expect(current.streaming).toBe(false);
    expect(current.rejectedSend).toBeNull();
    expect(onError).not.toHaveBeenCalled();
  });

  it("bounds an OPEN silent socket without replaying or deleting an uncertain send", async () => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await act(async () => {
      await current.sendMessage("possibly received");
      jest.advanceTimersByTime(WS_FIRST_EVENT_TIMEOUT_MS - 1);
    });
    expect(current.streaming).toBe(true);
    await act(async () => { jest.advanceTimersByTime(1); });
    expect(current.streaming).toBe(false);
    expect(current.finalizing).toBe(false);
    expect(current.messages.map((message) => message.content)).toEqual(["possibly received"]);
    expect(current.rejectedSend).toBeNull();
    expect(await current.retryRejectedSend()).toBe(false);
    expect(socket.close).toHaveBeenCalledTimes(1);
    expect(streamChatMessageSse).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError).toHaveBeenCalledWith("chat.error_unreachable", undefined);
    await act(async () => {
      socket.emit({ type: "start" });
      socket.emit({ type: "token", content: "late" });
      socket.emit({ type: "done", message_id: "late", final_content: "late" });
      socket.onerror();
      socket.onclose();
    });
    expect(current.messages.map((message) => message.content)).toEqual(["possibly received"]);
    expect(current.streaming).toBe(false);
    expect(onError).toHaveBeenCalledTimes(1);
  });

  it("restores the old answer when regeneration's OPEN socket stays silent", async () => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    const previous = { id: "saved", role: "assistant" as const, content: "previous answer", model: null, created_at: "now" };
    await act(async () => { current.editThread([previous], "page_refresh"); });
    await act(async () => {
      await current.regenerateResponse();
      jest.advanceTimersByTime(WS_FIRST_EVENT_TIMEOUT_MS);
    });
    expect(current.messages).toEqual([previous]);
    expect(current.streaming).toBe(false);
    expect(current.rejectedSend).toBeNull();
    expect(streamChatRegenerateSse).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledWith("chat.error_unreachable", undefined);
    await act(async () => { socket.emit({ type: "done", message_id: "late", final_content: "late" }); });
    expect(current.messages).toEqual([previous]);
  });

  it.each(["start", "status"] as const)("allows slow acknowledged work after the first %s event", async (type) => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await act(async () => {
      await current.sendMessage("slow math");
      socket.emit(type === "status" ? { type, phase: "solving_math" } : { type });
      // Five quiet minutes, with the server's keepalive every 15 s.
      for (let tick = 0; tick < 20; tick += 1) {
        jest.advanceTimersByTime(15_000);
        socket.emit({ type: "keepalive" });
      }
    });
    expect(current.streaming).toBe(true);
    expect(socket.close).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
    await act(async () => { socket.emit({ type: "done", message_id: "saved", final_content: "complete" }); });
    expect(current.streaming).toBe(false);
    expect(current.messages.some((message) => message.content === "complete")).toBe(true);
  });

  it.each(["not-json", "{}", '{"type":"ping"}'])("ignores a non-turn socket frame %s while awaiting acknowledgment", async (data) => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await act(async () => {
      await current.sendMessage("question");
      socket.onmessage({ data });
      jest.advanceTimersByTime(WS_FIRST_EVENT_TIMEOUT_MS);
    });
    expect(current.streaming).toBe(false);
    expect(onError).toHaveBeenCalledTimes(1);
  });

  it("cancels the first-event deadline when a WS turn is stopped", async () => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await act(async () => {
      await current.sendMessage("question");
      current.stopGeneration();
      jest.advanceTimersByTime(5 * 60_000);
    });
    expect(current.streaming).toBe(false);
    expect(onError).not.toHaveBeenCalled();
    expect(socket.send.mock.calls.map(([data]) => JSON.parse(data).type)).toContain("cancel");
  });

  it.each(["navigate", "signout", "unmount"] as const)("detaches a waiting socket deadline on %s", async (change) => {
    const view = await render(<Probe chatId="a" />);
    const old = await openSocket();
    await act(async () => { await current.sendMessage("old question"); });
    if (change === "unmount") await view.unmount();
    else {
      if (change === "signout") mockSessionGeneration++;
      await view.rerender(<Probe chatId={change === "navigate" ? "b" : "a"} />);
      const active = await openSocket();
      await sendAndStream(active, "active answer");
    }
    await act(async () => {
      jest.advanceTimersByTime(WS_FIRST_EVENT_TIMEOUT_MS);
      old.onclose();
      old.emit({ type: "done", message_id: "old", final_content: "old answer" });
    });
    expect(onError).not.toHaveBeenCalled();
    if (change !== "unmount") {
      expect(current.streaming).toBe(true);
      expect(getStreamingDraft()?.content).toBe("active answer");
    }
  });

  it("ignores a departed chat's late socket failure while the next chat streams", async () => {
    const view = await render(<Probe chatId="a" />);
    const old = await openSocket();
    await sendAndStream(old, "old reply");
    await view.rerender(<Probe chatId="b" />);
    const active = await openSocket();
    await sendAndStream(active, "current reply");
    await act(async () => { old.onerror(); old.onclose(); });
    expect(current.streaming).toBe(true);
    expect(getStreamingDraft()?.content).toBe("current reply");
    expect(onError).not.toHaveBeenCalled();
  });

  it("never dispatches an old pending send through the next chat's socket", async () => {
    const view = await render(<Probe chatId="a" />);
    let sending!: Promise<unknown>;
    await act(async () => { sending = current.sendMessage("belongs to a"); });
    const old = FakeSocket.instances[0];
    await view.rerender(<Probe chatId="b" />);
    const active = await openSocket();
    await act(async () => { old.open(); await sending; });
    expect(active.send.mock.calls.map(([data]) => JSON.parse(data))).toEqual([
      { token: "token", client_timezone: "UTC" },
      { type: "ping" },
    ]);
    expect(streamChatMessageSse).not.toHaveBeenCalled();
  });

  it("settles connection waiters when the socket closes before opening", async () => {
    await render(<Probe chatId="a" />);
    let settled = false;
    await act(async () => {
      void current.connect().then(() => { settled = true; });
      FakeSocket.instances[0].onclose();
    });
    expect(settled).toBe(true);
  });

  it("takes back a turn stopped during the handshake: nothing goes out, and its sender returns the draft", async () => {
    await render(<Probe chatId="a" />);
    let sending!: Promise<boolean>;
    await act(async () => { sending = current.sendMessage("cancel before sending"); });
    const socket = FakeSocket.instances[0];
    await act(async () => { current.stopGeneration(); });
    expect(current.messages).toEqual([]);
    let sent: boolean | undefined;
    await act(async () => { socket.open(); sent = await sending; });
    expect(sent).toBe(false);
    expect(socket.send.mock.calls.map(([data]) => JSON.parse(data).type)).not.toContain("message");
    expect(streamChatMessageSse).not.toHaveBeenCalled();
    expect(current.streaming).toBe(false);
  });

  it("preserves partial content when a dropped socket's reply never lands", async () => {
    listMessages.mockRejectedValue(new Error("offline"));
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await sendAndStream(socket, "partial reply");
    await act(async () => { socket.onerror(); socket.onclose(); });
    // The server keeps the turn: wait for its saved reply first.
    expect(current.streaming).toBe(true);
    await waitOutReconcile();
    expect(listMessages).toHaveBeenCalledTimes(DROPPED_TURN_POLLS);
    expect(current.streaming).toBe(false);
    expect(current.messages).toEqual(expect.arrayContaining([
      expect.objectContaining({ content: "partial reply", generationStopped: true }),
    ]));
    expect(current.messages.some((message) => message.id === "streaming")).toBe(false);
    expect(onError).toHaveBeenCalledWith("chat.error_connection_lost", undefined);
  });

  it("swaps a dropped socket's bubbles for the reply the server saved", async () => {
    const saved = [
      { id: SERVER_USER_ID, role: "user" as const, content: "question", model: null, created_at: "t1" },
      { id: SERVER_REPLY_ID, role: "assistant" as const, content: "whole reply", model: "free-chat", created_at: "t2" },
    ];
    listMessages.mockResolvedValue({ messages: saved, has_more: false });
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await sendAndStream(socket, "partial");
    await act(async () => { socket.onclose(); });
    await act(async () => { await jest.advanceTimersByTimeAsync(DROPPED_TURN_MAX_WAIT_MS); });
    expect(current.streaming).toBe(false);
    expect(current.messages).toEqual(saved);
    // A few rows per poll; the whole page once, to settle.
    expect(listMessages.mock.calls.map(([, , opts]) => opts.limit)).toEqual([
      DROPPED_TURN_PROBE_ROWS, MESSAGE_PAGE_SIZE,
    ]);
    expect(current.rejectedSend).toBeNull();
    expect(onError).not.toHaveBeenCalled();
  });

  it("reloads the chat for the saved reply when a turn goes quiet past the idle deadline", async () => {
    const saved = [
      { id: SERVER_USER_ID, role: "user" as const, content: "question", model: null, created_at: "t1" },
      { id: SERVER_REPLY_ID, role: "assistant" as const, content: "whole reply", model: "free-chat", created_at: "t2" },
    ];
    listMessages.mockResolvedValue({ messages: saved, has_more: false });
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await sendAndStream(socket, "partial");
    await act(async () => { await jest.advanceTimersByTimeAsync(STREAM_IDLE_TIMEOUT_MS); });
    expect(socket.close).toHaveBeenCalled();
    await act(async () => { await jest.advanceTimersByTimeAsync(DROPPED_TURN_MAX_WAIT_MS); });
    expect(current.streaming).toBe(false);
    expect(current.messages).toEqual(saved);
    expect(onError).not.toHaveBeenCalled();
  });

  it("never replays a send the server took when its socket drops before a token", async () => {
    // Regression: start, then a drop, used to queue the send as unsaved and offer
    // Retry while the server kept going: two identical turns, charged twice.
    listMessages.mockResolvedValue({
      messages: [{ id: SERVER_USER_ID, role: "user", content: "question", model: null, created_at: "t1" }],
      has_more: false,
    });
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await act(async () => {
      await current.sendMessage("question");
      socket.emit({ type: "start" });
    });
    await act(async () => { socket.onclose(); });
    expect(current.streaming).toBe(true);
    expect(current.messages.some((m) => m.role === "user" && m.content === "question")).toBe(true);
    await waitOutReconcile();
    expect(current.rejectedSend).toBeNull();
    expect(streamChatMessageSse).not.toHaveBeenCalled();
    expect(current.messages.some((m) => m.role === "user" && m.content === "question")).toBe(true);
    expect(onError).toHaveBeenCalledWith("chat.error_connection_lost", undefined);
  });

  it("offers Retry for a taken send only when a reload shows it is not in the chat", async () => {
    listMessages.mockResolvedValue({ messages: [], has_more: false });
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await act(async () => {
      await current.sendMessage("question");
      socket.emit({ type: "start" });
    });
    await act(async () => { socket.onclose(); });
    await waitOutReconcile();
    expect(current.rejectedSend?.content).toBe("question");
    expect(onError).toHaveBeenCalledWith("chat.error_unreachable", "send_rejected");
  });

  it("replays a send the server closed unread (over the socket cap) over SSE, silently", async () => {
    (streamChatMessageSse as jest.Mock).mockResolvedValueOnce(undefined);
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await act(async () => { await current.sendMessage("first words"); });
    await act(async () => { (socket.onclose as (event: { code: number }) => void)({ code: 4429 }); });
    expect(streamChatMessageSse).toHaveBeenCalledWith(expect.objectContaining({ content: "first words" }));
    expect(current.rejectedSend).toBeNull();
    expect(onError).not.toHaveBeenCalled();
  });

  it("reconnects a socket the server closed for idling, with no error", async () => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await act(async () => { (socket.onclose as (event: { code: number }) => void)({ code: 4408 }); });
    expect(onError).not.toHaveBeenCalled();
    await act(async () => {
      const sending = current.sendMessage("after a quiet while");
      FakeSocket.instances[FakeSocket.instances.length - 1].open();
      await sending;
    });
    expect(FakeSocket.instances).toHaveLength(2);
    expect(streamChatMessageSse).not.toHaveBeenCalled();
    const frames = FakeSocket.instances[1].send.mock.calls.map(([data]) => JSON.parse(data).type);
    expect(frames).toContain("message");
  });

  it("ignores a previous view's SSE rejection after navigating away and back", async () => {
    let rejectStream!: (error: Error) => void;
    (streamChatMessageSse as jest.Mock).mockImplementationOnce(() =>
      new Promise<void>((_resolve, reject) => { rejectStream = reject; }),
    );
    const view = await render(<Probe chatId="a" />);
    let sending!: Promise<unknown>;
    await act(async () => {
      sending = current.sendMessage("old question");
      FakeSocket.instances[0].onerror();
    });
    await view.rerender(<Probe chatId="b" />);
    await view.rerender(<Probe chatId="a" />);
    const active = await openSocket();
    await sendAndStream(active, "new reply");
    await act(async () => { rejectStream(new Error("old request failed")); await sending; });
    expect(current.streaming).toBe(true);
    expect(getStreamingDraft()?.content).toBe("new reply");
    expect(onError).not.toHaveBeenCalled();
  });

  it("does not restart a stopped turn when its server start arrives late", async () => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await act(async () => {
      await current.sendMessage("question");
      current.stopGeneration();
      socket.emit({ type: "start" });
      socket.emit({ type: "token", content: "late" });
    });
    expect(current.streaming).toBe(false);
    expect(current.messages.some((message) => message.id === "streaming")).toBe(false);
  });

  it("isolates a new send from the stopped turn's late done frame", async () => {
    await render(<Probe chatId="a" />);
    const old = await openSocket();
    await sendAndStream(old, "partial old reply");
    await act(async () => { current.stopGeneration(); });
    let sending!: Promise<unknown>;
    await act(async () => { sending = current.sendMessage("next question"); });
    const next = FakeSocket.instances[1];
    await act(async () => {
      next.open();
      await sending;
      next.emit({ type: "start" });
      next.emit({ type: "token", content: "next reply" });
      old.emit({ type: "done", message_id: "old-id", final_content: "partial old reply" });
      jest.advanceTimersByTime(20);
    });
    expect(current.streaming).toBe(true);
    expect(getStreamingDraft()?.content).toBe("next reply");
  });

  // S7.11: a stopped answer never changes past what the user saw.
  it("tells the server how much it drew on Stop, and keeps that text when done lands", async () => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await sendAndStream(socket, "Partial 😀 reply");
    await act(async () => { current.stopGeneration(); });
    const cancel = socket.send.mock.calls
      .map(([data]) => JSON.parse(data))
      .find((frame) => frame.type === "cancel");
    expect(cancel).toEqual({ type: "cancel", shown_chars: "Partial 😀 reply".length });

    await act(async () => {
      // Tokens in flight when the user tapped Stop are dropped, and a done for a
      // reply the server finished anyway does not swap its text in.
      socket.emit({ type: "token", content: " that kept going" });
      socket.emit({
        type: "done",
        message_id: SERVER_REPLY_ID,
        final_content: "Partial 😀 reply that kept going\n\n```answer\nx = 4\n```",
      });
    });
    const reply = current.messages.find((message) => message.id === SERVER_REPLY_ID);
    expect(reply?.content).toBe("Partial 😀 reply");
    expect(reply?.generationStopped).toBe(true);
  });

  it("restores the old answer when regeneration is stopped before replacement tokens", async () => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await sendAndStream(socket);
    await act(async () => {
      socket.emit({ type: "done", message_id: "saved", final_content: "saved answer" });
    });
    await act(async () => {
      current.beginRegenerateUi();
    });
    await act(async () => { current.stopGeneration(); });
    expect(current.messages).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: "saved", content: "saved answer" }),
    ]));
  });

  it("ignores cancellation from regeneration preparation in a previous view", async () => {
    const view = await render(<Probe chatId="a" />);
    const cancelPrevious = current.cancelRegenerateUi;
    await view.rerender(<Probe chatId="b" />);
    const socket = await openSocket();
    await sendAndStream(socket, "current answer");
    await act(async () => { cancelPrevious(); });
    expect(current.streaming).toBe(true);
    expect(getStreamingDraft()?.content).toBe("current answer");
  });

  it("invalidates regeneration preparation when Stop is pressed", async () => {
    await render(<Probe chatId="a" />);
    let isCurrentAttempt: (() => boolean) | void;
    await act(async () => { isCurrentAttempt = current.beginRegenerateUi(); });
    expect(isCurrentAttempt!()).toBe(true);
    await act(async () => { current.stopGeneration(); });
    expect(isCurrentAttempt!()).toBe(false);
  });

  it("dispatches direct regeneration and preserves its backup before the UI rerenders", async () => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await sendAndStream(socket);
    await act(async () => {
      socket.emit({ type: "done", message_id: "saved", final_content: "original" });
    });
    await act(async () => {
      current.beginRegenerateUi();
      await current.regenerateResponse();
      socket.emit({ type: "error", message: "busy", code: "busy" });
    });
    expect(socket.send.mock.calls.map(([data]) => JSON.parse(data).type)).toContain("regenerate");
    expect(current.messages).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: "saved", content: "original" }),
    ]));
  });

  it("replays an auth-rejected turn through SSE without duplicating the user message", async () => {
    (streamChatMessageSse as jest.Mock).mockImplementationOnce(async ({ onEvent }) => {
      onEvent({ type: "start" });
      onEvent({ type: "token", content: "recovered" });
      onEvent({ type: "done", message_id: "saved", final_content: "recovered" });
    });
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await act(async () => {
      await current.sendMessage("first question");
      socket.emit({ type: "error", message: "Unauthorized" });
      socket.onclose();
    });
    expect(streamChatMessageSse).toHaveBeenCalledWith(expect.objectContaining({
      chatId: "a", content: "first question",
    }));
    expect(current.messages.filter((message) => message.role === "user")).toHaveLength(1);
    expect(current.messages).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: "saved", content: "recovered" }),
    ]));
    expect(onError).not.toHaveBeenCalled();
  });

  it("never replays an already accepted stream after an authentication-like error", async () => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await sendAndStream(socket);
    await act(async () => {
      socket.emit({ type: "error", message: "Unauthorized" });
    });
    expect(streamChatMessageSse).not.toHaveBeenCalled();
    expect(current.streaming).toBe(false);
  });
  it("retries the exact unsaved busy turn after start without regenerating prior history", async () => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await sendAndStream(socket, "previous answer");
    await act(async () => {
      socket.emit({ type: "done", message_id: "previous-answer", final_content: "previous answer" });
      await current.sendMessage("unsaved follow-up", {
        model: "smart-chat", attachmentIds: ["file-id"],
        clientGeo: { label: "Here", latitude: 1, longitude: 2 },
      });
      socket.emit({ type: "start" });
      socket.emit({ type: "error", code: "busy", message: "Still finishing" });
    });
    expect(current.streaming).toBe(false);
    expect(current.messages.map((message) => message.content)).toEqual(["question", "previous answer"]);
    expect(onError).toHaveBeenLastCalledWith("Still finishing", "send_rejected");
    expect(current.rejectedSend?.content).toBe("unsaved follow-up");
    await act(async () => { expect(await current.retryRejectedSend()).toBe(true); });
    const turns = socket.send.mock.calls.map(([data]) => JSON.parse(data)).filter((frame) => frame.type === "message");
    expect(turns).toHaveLength(3);
    expect(turns[2]).toEqual(turns[1]);
    expect(current.messages.filter((message) => message.content === "unsaved follow-up")).toHaveLength(1);
  });

  it("offers exact-message retry for an SSE busy rejection even after start", async () => {
    (streamChatMessageSse as jest.Mock).mockImplementationOnce(async ({ onEvent }) => {
      onEvent({ type: "start" });
      onEvent({ type: "error", code: "busy", message: "Still finishing" });
    });
    await render(<Probe chatId="a" />);
    let pending!: Promise<unknown>;
    await act(async () => {
      pending = current.sendMessage("SSE follow-up", { attachmentIds: ["a1"], model: "smart-chat" });
      FakeSocket.instances[0].onerror();
      await pending;
    });
    expect(current.messages).toEqual([]);
    expect(current.rejectedSend?.content).toBe("SSE follow-up");
    await act(async () => { await current.retryRejectedSend(); });
    expect(streamChatMessageSse).toHaveBeenLastCalledWith(expect.objectContaining({
      content: "SSE follow-up", attachmentIds: ["a1"], model: "smart-chat",
    }));
  });

  it("treats an SSE transport failure as an unsaved send, not a regenerate", async () => {
    (streamChatMessageSse as jest.Mock).mockRejectedValueOnce(new Error("offline"));
    await render(<Probe chatId="a" />);
    await act(async () => {
      const pending = current.sendMessage("never arrived");
      FakeSocket.instances[0].onerror();
      await pending;
    });
    expect(current.messages.filter((message) => message.role === "user")).toHaveLength(0);
    expect(current.rejectedSend?.content).toBe("never arrived");
    expect(onError).toHaveBeenCalledWith("chat.error_unreachable", "send_rejected");
    (streamChatMessageSse as jest.Mock).mockResolvedValueOnce(undefined);
    await act(async () => { expect(await current.retryRejectedSend()).toBe(true); });
    expect(streamChatMessageSse).toHaveBeenLastCalledWith(expect.objectContaining({
      content: "never arrived",
    }));
  });

  it("does not treat a partial SSE stream as an unsaved send", async () => {
    listMessages.mockRejectedValue(new Error("offline"));
    (streamChatMessageSse as jest.Mock).mockImplementationOnce(async ({ onEvent }) => {
      onEvent({ type: "start" });
      onEvent({ type: "token", content: "partial reply" });
      jest.advanceTimersByTime(20);
      throw new Error("offline");
    });
    await render(<Probe chatId="a" />);
    await act(async () => {
      const pending = current.sendMessage("question");
      FakeSocket.instances[0].onerror();
      await pending;
    });
    await waitOutReconcile(SSE_DROPPED_TURN_POLLS);
    expect(listMessages).toHaveBeenCalledTimes(SSE_DROPPED_TURN_POLLS);
    expect(current.rejectedSend).toBeNull();
    expect(current.messages).toEqual(expect.arrayContaining([
      expect.objectContaining({ content: "question", role: "user" }),
      expect.objectContaining({ content: "partial reply", generationStopped: true }),
    ]));
    expect(onError).toHaveBeenCalledWith("chat.error_unreachable", undefined);
  });

  it("does not offer new-send retry for an error that may follow persistence", async () => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await act(async () => {
      await current.sendMessage("possibly saved");
      socket.emit({ type: "start" });
      socket.emit({ type: "error", code: "internal_error", message: "Failed" });
      expect(await current.retryRejectedSend()).toBe(false);
    });
    expect(current.rejectedSend).toBeNull();
    expect(current.messages.some((message) => message.content === "possibly saved")).toBe(true);
  });

  it("keeps a rejected turn on view reopen but blocks stale and cross-account retries", async () => {
    const view = await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await act(async () => {
      await current.sendMessage("belongs to a");
      socket.emit({ type: "error", code: "busy" });
    });
    const retryOldChat = current.retryRejectedSend;
    await view.rerender(<Probe chatId="b" />);
    await act(async () => { expect(await retryOldChat()).toBe(false); });
    expect(current.rejectedSend).toBeNull();
    await view.rerender(<Probe chatId="a" />);
    expect(current.rejectedSend?.content).toBe("belongs to a");
    await act(async () => { expect(await retryOldChat()).toBe(false); });
    mockSessionGeneration++;
    await view.rerender(<Probe chatId="a" token="other-account" />);
    await act(async () => { expect(await current.retryRejectedSend()).toBe(false); });
    expect(current.rejectedSend).toBeNull();
  });

  it("invalidates rejected-send retry on Stop and ignores a later busy frame", async () => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await act(async () => {
      await current.sendMessage("stopped");
      current.stopGeneration();
      socket.emit({ type: "error", code: "busy" });
      expect(await current.retryRejectedSend()).toBe(false);
    });
    expect(current.rejectedSend).toBeNull();
  });

  it("preserves rejected sends through newer successful turns and retries the FIFO without duplicates", async () => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await act(async () => {
      await current.sendMessage("first rejected");
      socket.emit({ type: "error", code: "busy" });
      await current.sendMessage("new successful turn");
      socket.emit({ type: "done", message_id: "saved-new", final_content: "new answer" });
    });
    expect(current.rejectedSend?.content).toBe("first rejected");
    await act(async () => {
      await current.sendMessage("second rejected");
      socket.emit({ type: "error", code: "busy" });
      await current.retryRejectedSend();
      socket.emit({ type: "error", code: "busy" });
    });
    expect(current.rejectedSend?.content).toBe("first rejected");
    await act(async () => {
      await current.retryRejectedSend();
      socket.emit({ type: "done", message_id: "saved-first", final_content: "first answer" });
    });
    expect(current.rejectedSend?.content).toBe("second rejected");
    await act(async () => {
      await current.retryRejectedSend();
      socket.emit({ type: "done", message_id: "saved-second", final_content: "second answer" });
      expect(await current.retryRejectedSend()).toBe(false);
    });
    expect(current.rejectedSend).toBeNull();
    const users = current.messages.filter((message) => message.role === "user");
    expect(users.map((message) => message.content)).toEqual([
      "new successful turn", "first rejected", "second rejected",
    ]);
  });

  it("permits a fresh explicit retry after reopening its conversation", async () => {
    const view = await render(<Probe chatId="a" />);
    const original = await openSocket();
    await act(async () => {
      await current.sendMessage("retained on reopen");
      original.emit({ type: "error", code: "busy" });
    });
    await view.rerender(<Probe chatId="b" />);
    await view.rerender(<Probe chatId="a" />);
    const reopened = await openSocket();
    await act(async () => { expect(await current.retryRejectedSend()).toBe(true); });
    expect(reopened.send).toHaveBeenLastCalledWith(expect.stringContaining('"content":"retained on reopen"'));
  });

  it("clears a queued rejection explicitly on Stop", async () => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await act(async () => {
      await current.sendMessage("discarded retry");
      socket.emit({ type: "error", code: "busy" });
    });
    expect(current.rejectedSend?.content).toBe("discarded retry");
    await act(async () => { current.stopGeneration(); });
    await act(async () => { expect(await current.retryRejectedSend()).toBe(false); });
    expect(current.rejectedSend).toBeNull();
  });

  it("retains uploaded attachment metadata when removing an externally created optimistic bubble", async () => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    const attachmentIds = ["uploaded-id"];
    const clientGeo = { label: "Original location", latitude: 1, longitude: 2 };
    await act(async () => {
      current.editThread([{
        id: "composer-optimistic", role: "user", content: "attachment question",
        model: null, created_at: new Date().toISOString(),
      }], "page_refresh");
      await current.sendMessage("attachment question", {
        skipUserBubble: true, trackSendingMessageId: "composer-optimistic",
        attachmentIds, clientGeo, localFileUri: "file:///original.pdf",
        localFileName: "original.pdf", localFileContentType: "application/pdf",
      });
      socket.emit({ type: "start" });
      socket.emit({ type: "error", code: "busy" });
    });
    expect(current.messages).toEqual([]);
    attachmentIds[0] = "different-upload";
    clientGeo.label = "Different location";
    await act(async () => { await current.retryRejectedSend(); });
    expect(socket.send).toHaveBeenLastCalledWith(expect.stringContaining('"attachment_ids":["uploaded-id"]'));
    expect(socket.send).toHaveBeenLastCalledWith(expect.stringContaining('"client_location":"Original location"'));
    expect(current.messages.filter((message) => message.role === "user")).toEqual([
      expect.objectContaining({ content: "attachment question", local_file_uri: "file:///original.pdf" }),
    ]);
  });

  it("does not turn an interrupted SSE response into an automatic duplicate send", async () => {
    (streamChatMessageSse as jest.Mock).mockRejectedValueOnce(new Error("EOF before terminal event"));
    await render(<Probe chatId="a" />);
    await act(async () => {
      const pending = current.sendMessage("possibly persisted");
      FakeSocket.instances[0].onerror();
      await pending;
    });
    // Client never saw tokens, so treat as unsaved: drop the optimistic bubble
    // and keep Retry. A later user tap may duplicate if the server did persist;
    // leaving it looking sent is worse.
    expect(current.messages.filter((message) => message.role === "user")).toHaveLength(0);
    expect(current.rejectedSend?.content).toBe("possibly persisted");
    expect(onError).toHaveBeenCalledWith("chat.error_unreachable", "send_rejected");
    expect(streamChatMessageSse).toHaveBeenCalledTimes(1);
  });

  it.each(["token", "stream_end"])("never requeues an accepted turn when busy arrives after %s", async (type) => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await act(async () => {
      await current.sendMessage("already accepted");
      socket.emit({ type: "start" });
      socket.emit({ type, content: "partial answer" });
      socket.emit({ type: "error", code: "busy", message: "Another action was rejected" });
      expect(await current.retryRejectedSend()).toBe(false);
    });
    expect(current.rejectedSend).toBeNull();
    expect(current.messages.some((message) => message.content === "already accepted")).toBe(true);
    expect(onError).toHaveBeenLastCalledWith("Another action was rejected", "busy");
  });

  it("retains recovery if navigation prevents a retry from finishing its handshake", async () => {
    const view = await render(<Probe chatId="a" />);
    const original = await openSocket();
    await act(async () => {
      await current.sendMessage("retry not dispatched");
      original.emit({ type: "error", code: "busy" });
    });
    await view.rerender(<Probe chatId="b" />);
    await view.rerender(<Probe chatId="a" />);
    let retrying!: Promise<boolean>;
    await act(async () => { retrying = current.retryRejectedSend(); });
    const waiting = FakeSocket.instances[FakeSocket.instances.length - 1];
    await view.rerender(<Probe chatId="b" />);
    await act(async () => { waiting.open(); expect(await retrying).toBe(false); });
    expect(waiting.send.mock.calls.map(([data]) => JSON.parse(data).type)).not.toContain("message");
    await view.rerender(<Probe chatId="a" />);
    expect(current.rejectedSend?.content).toBe("retry not dispatched");
    const reopened = await openSocket();
    await act(async () => { expect(await current.retryRejectedSend()).toBe(true); });
    expect(reopened.send).toHaveBeenLastCalledWith(expect.stringContaining('"content":"retry not dispatched"'));
    expect(current.messages.filter((message) => message.content === "retry not dispatched")).toHaveLength(1);
  });

  it.each(["ws", "sse"])("recovers a definitely unsaved attachment rejection over %s without resending its invalid id", async (transport) => {
    const originalDraft = { text: "  My exact question\n", attachment: {
      kind: "file" as const, localUri: "file:///original.pdf", fileName: "original.pdf",
      contentType: "application/pdf", existingAttachmentId: "rejected-id",
    } };
    const error = { type: "error", code: "attachment_rejected", message: "File unavailable" };
    // Queued only when SSE will take it: a leftover would answer a later test's send.
    if (transport === "sse") {
      (streamChatMessageSse as jest.Mock).mockImplementationOnce(async ({ onEvent }) => {
        onEvent({ type: "start" }); onEvent(error);
      });
    }
    await render(<Probe chatId="a" />);
    const socket = transport === "ws" ? await openSocket() : null;
    await act(async () => {
      const sending = current.sendMessage("My exact question", {
        attachmentIds: ["rejected-id"], composerDraft: originalDraft,
      });
      if (socket) { await sending; socket.emit({ type: "start" }); socket.emit(error); }
      else { FakeSocket.instances[0].onerror(); await sending; }
    });
    expect(current.messages).toEqual([]);
    expect(onError).toHaveBeenLastCalledWith("File unavailable", "attachment_rejected");
    expect(current.rejectedSend?.reason).toBe("attachment_rejected");
    originalDraft.text = "mutated later";
    originalDraft.attachment.localUri = "file:///replacement.pdf";
    await act(async () => { expect(await current.retryRejectedSend()).toBe(false); });
    const restore = jest.fn(() => false);
    await act(async () => { expect(current.restoreRejectedAttachmentDraft(restore)).toBe(false); });
    expect(current.rejectedSend).not.toBeNull();
    expect(restore).toHaveBeenLastCalledWith({ text: "  My exact question\n", attachment: {
      kind: "file", localUri: "file:///original.pdf", fileName: "original.pdf", contentType: "application/pdf",
    } });
    restore.mockReturnValue(true);
    await act(async () => { expect(current.restoreRejectedAttachmentDraft(restore)).toBe(true); });
    expect(current.rejectedSend).toBeNull();
    await act(async () => { expect(current.restoreRejectedAttachmentDraft(restore)).toBe(false); });
    expect(restore).toHaveBeenCalledTimes(2);
    if (socket) expect(socket.send.mock.calls.map(([data]) => JSON.parse(data).type)).toEqual([undefined, "ping", "message"]);
    else expect(streamChatMessageSse).toHaveBeenCalledTimes(1);
  });

  it("retains rejected attachment recovery for its chat and refuses stale or cross-account callbacks", async () => {
    const view = await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await act(async () => {
      await current.sendMessage("unsaved file", { attachmentIds: ["bad-id"] });
      socket.emit({ type: "error", code: "attachment_rejected" });
    });
    const oldRestore = current.restoreRejectedAttachmentDraft;
    const restore = jest.fn(() => true);
    await view.rerender(<Probe chatId="b" />);
    await act(async () => { expect(oldRestore(restore)).toBe(false); });
    expect(current.rejectedSend).toBeNull();
    await view.rerender(<Probe chatId="a" />);
    expect(current.rejectedSend?.reason).toBe("attachment_rejected");
    await act(async () => { expect(oldRestore(restore)).toBe(false); });
    const beforeSignout = current.restoreRejectedAttachmentDraft;
    mockSessionGeneration++;
    await act(async () => { expect(beforeSignout(restore)).toBe(false); });
    await view.rerender(<Probe chatId="a" token="other-account" />);
    await act(async () => { expect(current.restoreRejectedAttachmentDraft(restore)).toBe(false); });
    expect(current.rejectedSend).toBeNull();
    expect(restore).not.toHaveBeenCalled();
  });

  it.each(["token", "stream_end", "done"])("never restores an accepted attachment turn after %s", async (type) => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    const restore = jest.fn(() => true);
    await act(async () => {
      await current.sendMessage("already saved", { attachmentIds: ["saved-id"] });
      socket.emit({ type: "start" });
      socket.emit({ type, content: "answer", message_id: "saved", final_content: "answer" });
      socket.emit({ type: "error", code: "attachment_rejected" });
      expect(await current.retryRejectedSend()).toBe(false);
      expect(current.restoreRejectedAttachmentDraft(restore)).toBe(false);
    });
    expect(current.rejectedSend).toBeNull();
    expect(current.messages.some((message) => message.content === "already saved")).toBe(true);
    expect(restore).not.toHaveBeenCalled();
  });

  it("keeps the visible recovery action aligned with mixed rejection reasons in FIFO order", async () => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await act(async () => {
      await current.sendMessage("busy first");
      socket.emit({ type: "error", code: "busy" });
      await current.sendMessage("attachment second", { attachmentIds: ["bad-id"] });
      socket.emit({ type: "error", code: "attachment_rejected" });
    });
    expect(onError).toHaveBeenLastCalledWith("chat.error_generic", "send_rejected");
    const restore = jest.fn(() => true);
    await act(async () => {
      expect(current.restoreRejectedAttachmentDraft(restore)).toBe(false);
      await current.retryRejectedSend();
      socket.emit({ type: "done", message_id: "first-saved", final_content: "answer" });
    });
    expect(current.rejectedSend?.reason).toBe("attachment_rejected");
    await act(async () => {
      expect(await current.retryRejectedSend()).toBe(false);
      expect(current.restoreRejectedAttachmentDraft(restore)).toBe(true);
    });
    expect(restore).toHaveBeenCalledWith({ text: "attachment second", attachment: null });
    expect(current.rejectedSend).toBeNull();
  });

  describe("typing dots before a send goes out", () => {
    const bubble = { id: "local-1", role: "user" as const, content: "question", model: null, created_at: "now" };
    // Turn frames only: the auth frame has no type, and the connect ping is the socket's own.
    const sentTypes = (socket: FakeSocket) =>
      socket.send.mock.calls
        .map(([data]) => JSON.parse(data).type)
        .filter((type) => Boolean(type) && type !== "ping");

    async function paint(row = bubble) {
      let dots: DotsTicket | null = null;
      await act(async () => {
        current.editThread([row], "page_refresh");
        dots = current.sendStart.beginDots();
      });
      return dots as DotsTicket | null;
    }

    it("go up under the painted bubble and stay for its send", async () => {
      await render(<Probe chatId="a" />);
      const socket = await openSocket();
      const dots = await paint();
      expect(dots?.current()).toBe(true);
      expect(current.streaming).toBe(true);
      expect(current.messages.map((message) => message.id)).toEqual(["local-1", "streaming"]);
      expect(sentTypes(socket)).toEqual([]);

      await act(async () => {
        await current.sendMessage("question", { skipUserBubble: true, trackSendingMessageId: "local-1" });
      });
      expect(sentTypes(socket)).toEqual(["message"]);
      expect(current.messages.map((message) => message.id)).toEqual(["local-1", "streaming"]);
      await act(async () => {
        socket.emit({ type: "start" });
        socket.emit({ type: "token", content: "answer" });
        socket.emit({ type: "stream_end" });
        socket.emit({ type: "done", message_id: "saved", final_content: "answer" });
      });
      expect(current.messages.map((message) => message.id)).toEqual(["local-1", "saved"]);
      expect(current.streaming).toBe(false);
    });

    it("do not go up while a reply streams or saves", async () => {
      await render(<Probe chatId="a" />);
      const socket = await openSocket();
      await sendAndStream(socket);
      expect(current.sendStart.beginDots()).toBeNull();
      await act(async () => { socket.emit({ type: "stream_end" }); });
      expect(current.sendStart.beginDots()).toBeNull();
      await act(async () => { socket.emit({ type: "done", message_id: "saved", final_content: "reply" }); });
      let dots: DotsTicket | null = null;
      await act(async () => { dots = current.sendStart.beginDots(); });
      expect(dots).not.toBeNull();
    });

    it("come down when the send goes elsewhere, and a later send raises its own", async () => {
      await render(<Probe chatId="a" />);
      const socket = await openSocket();
      const dots = await paint();
      await act(async () => { dots?.cancel(); });
      expect(dots?.current()).toBe(false);
      expect(current.streaming).toBe(false);
      expect(current.messages.map((message) => message.id)).toEqual(["local-1"]);
      await act(async () => { await current.sendMessage("next"); });
      expect(current.messages.filter((message) => message.id === "streaming")).toHaveLength(1);
      expect(sentTypes(socket)).toEqual(["message"]);
    });

    it("come down on Stop, which the send that raised them sees", async () => {
      await render(<Probe chatId="a" />);
      await openSocket();
      const dots = await paint();
      await act(async () => { current.stopGeneration(); });
      expect(dots?.current()).toBe(false);
      expect(current.streaming).toBe(false);
      expect(current.messages.map((message) => message.id)).toEqual(["local-1"]);
    });

    it("taken down late from a chat left behind, leave the next chat's dots and send alone", async () => {
      // A's send waits on a slow upload; the user opens B and sends there first.
      const view = await render(<Probe chatId="a" />);
      await openSocket();
      const inA = await paint({ ...bubble, id: "local-a" });
      await act(async () => { view.rerender(<Probe chatId="b" />); });
      const socketB = await openSocket();
      const inB = await paint({ ...bubble, id: "local-b", content: "question in b" });
      await act(async () => { inA?.cancel(); });
      expect(inB?.current()).toBe(true);
      expect(current.streaming).toBe(true);
      let sent: boolean | undefined;
      await act(async () => {
        sent = await current.sendMessage("question in b", { skipUserBubble: true, trackSendingMessageId: "local-b" });
      });
      expect(sent).toBe(true);
      expect(sentTypes(socketB)).toEqual(["message"]);
      expect(current.messages.map((message) => message.id)).toEqual(["local-b", "streaming"]);
    });

    it("are not borrowed: a send with none of its own is refused while another turn runs, and says so", async () => {
      await render(<Probe chatId="a" />);
      const socket = await openSocket();
      await sendAndStream(socket);
      await act(async () => {
        socket.emit({ type: "stream_end" });
        socket.emit({ type: "done", message_id: "saved", final_content: "reply" });
      });
      // A waiting send's upload ends after Regenerate was tapped.
      await act(async () => { current.beginRegenerateUi(); });
      let sent: boolean | undefined;
      await act(async () => {
        sent = await current.sendMessage("next", { skipUserBubble: true, trackSendingMessageId: "local-2" });
      });
      expect(sent).toBe(false);
      expect(sentTypes(socket)).toEqual(["message"]);
      expect(current.messages.some((message) => message.id === "local-2")).toBe(false);
    });

    it("go up with a painted bubble put back when a reload took it away", async () => {
      await render(<Probe chatId="a" />);
      const socket = await openSocket();
      await act(async () => {
        await current.sendMessage("question", { skipUserBubble: true, trackSendingMessageId: "local-1" });
      });
      expect(current.messages.map((message) => message.id)).toEqual(["local-1", "streaming"]);
      expect(current.messages[0]).toMatchObject({ role: "user", content: "question" });
      expect(sentTypes(socket)).toEqual(["message"]);
    });

    it("leave a stopped turn's socket first, so its late frames reach nothing", async () => {
      await render(<Probe chatId="a" />);
      const old = await openSocket();
      await sendAndStream(old, "partial");
      await act(async () => { current.stopGeneration(); });
      await act(async () => {
        current.sendStart.beginDots();
        old.emit({ type: "token", content: " late" });
        old.emit({ type: "done", message_id: "old-id", final_content: "partial late" });
        jest.advanceTimersByTime(20);
      });
      expect(old.close).toHaveBeenCalled();
      expect(current.streaming).toBe(true);
      expect(getStreamingDraft()?.content).toBe("");
      expect(current.messages.at(-1)?.id).toBe("streaming");
    });
  });

  describe("a send made while the last reply saves", () => {
    const next = { id: "local-2", role: "user" as const, content: "next", model: null, created_at: "later" };
    const savedTurn = [
      { id: SERVER_USER_ID, role: "user" as const, content: "question", model: null, created_at: "t1" },
      { id: SERVER_REPLY_ID, role: "assistant" as const, content: "reply, checked", model: null, created_at: "t2" },
    ];
    const messageFrames = (socket: FakeSocket) =>
      socket.send.mock.calls.map(([data]) => JSON.parse(data)).filter((frame) => frame.type === "message");

    /** The reply's text is all in (`stream_end`); the next bubble is painted and waits. */
    async function paintWhileSaving(socket: FakeSocket) {
      await sendAndStream(socket, "reply");
      await act(async () => { socket.emit({ type: "stream_end" }); });
      expect(current.finalizing).toBe(true);
      let settled = false;
      let waiting!: Promise<void>;
      await act(async () => {
        current.editThread((rows) => [...rows, next], "page_refresh");
        expect(current.sendStart.beginDots()).toBeNull();
        waiting = current.sendStart.whenReplySettled("local-2").then(() => { settled = true; });
      });
      return { waiting, settled: () => settled };
    }

    async function sendNext() {
      await act(async () => {
        await current.sendMessage("next", { skipUserBubble: true, trackSendingMessageId: "local-2" });
      });
    }

    it("waits for the reply's done, which lands on that reply, then goes out", async () => {
      await render(<Probe chatId="a" />);
      const socket = await openSocket();
      const queued = await paintWhileSaving(socket);
      expect(queued.settled()).toBe(false);
      expect(current.sendingMessageId).toBe("local-2");
      expect(messageFrames(socket)).toHaveLength(1);

      // The wait ends once React has rendered the settled reply.
      await act(async () => {
        socket.emit({ type: "done", message_id: "saved-1", final_content: "reply, checked" });
      });
      await act(async () => { await queued.waiting; });
      expect(current.messages.map((message) => message.id)).toEqual([
        expect.stringMatching(/^local-/), "saved-1", "local-2",
      ]);
      expect(current.messages[1].content).toBe("reply, checked");
      expect(current.sendingMessageId).toBeNull();

      await sendNext();
      expect(messageFrames(socket).map((frame) => frame.content)).toEqual(["question", "next"]);
      expect(current.messages.map((message) => message.id).slice(1)).toEqual(["saved-1", "local-2", "streaming"]);
      await act(async () => {
        socket.emit({ type: "start" });
        socket.emit({ type: "token", content: "second answer" });
        jest.advanceTimersByTime(20);
      });
      expect(getStreamingDraft()?.content).toBe("second answer");
    });

    it("goes out after a done that has no id yet (the save outlived the server's wait)", async () => {
      await render(<Probe chatId="a" />);
      const socket = await openSocket();
      const queued = await paintWhileSaving(socket);
      await act(async () => { socket.emit({ type: "done", persisting: true }); });
      await act(async () => { await queued.waiting; });
      expect(current.messages.map((message) => message.id)).toEqual([
        expect.stringMatching(/^local-/), expect.stringMatching(/^streamed-/), "local-2",
      ]);
      expect(current.messages[1].content).toBe("reply");
      await sendNext();
      expect(messageFrames(socket)).toHaveLength(2);
    });

    it("goes out after a save that failed (an error after stream_end), keeping what was shown", async () => {
      await render(<Probe chatId="a" />);
      const socket = await openSocket();
      const queued = await paintWhileSaving(socket);
      await act(async () => {
        socket.emit({ type: "error", message: "Failed to save the response. Please retry.", user_message_saved: true });
      });
      await act(async () => { await queued.waiting; });
      expect(onError).toHaveBeenCalledWith("Failed to save the response. Please retry.", undefined);
      // The reply says so itself: the banner goes when the next turn starts.
      expect(current.messages[1]).toMatchObject({ content: "reply", replyNotSaved: true });
      expect(current.messages[1].generationStopped).toBeUndefined();
      expect(current.messages[2].id).toBe("local-2");
      // As after any reply kept partial, the next turn takes a new socket.
      let sending!: Promise<boolean>;
      await act(async () => {
        sending = current.sendMessage("next", { skipUserBubble: true, trackSendingMessageId: "local-2" });
      });
      const fresh = FakeSocket.instances.at(-1)!;
      await act(async () => { fresh.open(); await sending; });
      expect(fresh).not.toBe(socket);
      expect(messageFrames(fresh).map((frame) => frame.content)).toEqual(["next"]);
      expect(current.streaming).toBe(true);
    });

    it("reloads a reply whose done never comes after the grace, then goes out on a new socket", async () => {
      listMessages.mockResolvedValue({ messages: savedTurn, has_more: false });
      await render(<Probe chatId="a" />);
      const old = await openSocket();
      const queued = await paintWhileSaving(old);
      await act(async () => { jest.advanceTimersByTime(REPLY_SAVE_GRACE_MS - 1); });
      expect(queued.settled()).toBe(false);
      await act(async () => { jest.advanceTimersByTime(1); });
      // The quiet connection is left, and the chat reloads until the saved reply is in.
      expect(old.close).toHaveBeenCalled();
      expect(queued.settled()).toBe(false);
      await act(async () => { await jest.advanceTimersByTimeAsync(DROPPED_TURN_MAX_WAIT_MS); });
      await act(async () => { await queued.waiting; });
      // A few rows find the saved reply; the whole page once, to settle.
      expect(listMessages.mock.calls.map(([, , opts]) => opts.limit)).toEqual([
        DROPPED_TURN_PROBE_ROWS, MESSAGE_PAGE_SIZE,
      ]);
      expect(current.finalizing).toBe(false);
      // The saved reply (its checked text, not the raw stream) above the waiting bubble.
      expect(current.messages.map((message) => message.id)).toEqual([SERVER_USER_ID, SERVER_REPLY_ID, "local-2"]);
      expect(current.messages[1].content).toBe("reply, checked");
      expect(onError).not.toHaveBeenCalled();

      let sending!: Promise<boolean>;
      await act(async () => {
        sending = current.sendMessage("next", { skipUserBubble: true, trackSendingMessageId: "local-2" });
      });
      const fresh = FakeSocket.instances.at(-1)!;
      expect(fresh).not.toBe(old);
      await act(async () => {
        fresh.open();
        await sending;
        // The old turn's done turns up after all: it reaches nothing.
        old.emit({ type: "done", message_id: "saved-1", final_content: "reply" });
      });
      expect(messageFrames(fresh).map((frame) => frame.content)).toEqual(["next"]);
      expect(current.streaming).toBe(true);
      expect(current.messages.some((message) => message.id === "saved-1")).toBe(false);
    });

    it("reloads a reply that streamed no text (a photo answer) rather than dropping it", async () => {
      listMessages.mockResolvedValue({ messages: savedTurn, has_more: false });
      await render(<Probe chatId="a" />);
      const socket = await openSocket();
      await act(async () => {
        await current.sendMessage("question");
        socket.emit({ type: "start" });
        jest.advanceTimersByTime(20);
      });
      await act(async () => { socket.emit({ type: "stream_end" }); });
      let waiting!: Promise<void>;
      await act(async () => {
        current.editThread((rows) => [...rows, next], "page_refresh");
        waiting = current.sendStart.whenReplySettled("local-2");
      });
      await act(async () => { jest.advanceTimersByTime(REPLY_SAVE_GRACE_MS); });
      await act(async () => { await jest.advanceTimersByTimeAsync(DROPPED_TURN_MAX_WAIT_MS); });
      await act(async () => { await waiting; });
      expect(current.messages.map((message) => message.id)).toEqual([SERVER_USER_ID, SERVER_REPLY_ID, "local-2"]);
    });

    it("keeps the waiting bubble when the connection drops while the reply saves", async () => {
      listMessages.mockResolvedValue({ messages: savedTurn, has_more: false });
      await render(<Probe chatId="a" />);
      const socket = await openSocket();
      const queued = await paintWhileSaving(socket);
      await act(async () => { socket.onclose(); });
      await act(async () => { await jest.advanceTimersByTimeAsync(DROPPED_TURN_MAX_WAIT_MS); });
      await act(async () => { await queued.waiting; });
      expect(queued.settled()).toBe(true);
      expect(current.messages.map((message) => message.id)).toEqual([SERVER_USER_ID, SERVER_REPLY_ID, "local-2"]);

      // A dropped socket sends the next turn over SSE, under the bubble it kept.
      (streamChatMessageSse as jest.Mock).mockResolvedValueOnce(undefined);
      await sendNext();
      expect(streamChatMessageSse).toHaveBeenCalledWith(expect.objectContaining({ content: "next" }));
      expect(current.messages.map((message) => message.id)).toEqual([
        SERVER_USER_ID, SERVER_REPLY_ID, "local-2", "streaming",
      ]);
    });

    it("waits for a regenerated reply's done the same way", async () => {
      await render(<Probe chatId="a" />);
      const socket = await openSocket();
      await sendAndStream(socket);
      await act(async () => {
        socket.emit({ type: "stream_end" });
        socket.emit({ type: "done", message_id: "saved", final_content: "first answer" });
      });
      await act(async () => {
        current.beginRegenerateUi();
        await current.regenerateResponse();
        socket.emit({ type: "start" });
        socket.emit({ type: "token", content: "better answer" });
        socket.emit({ type: "stream_end" });
      });
      let settled = false;
      let waiting!: Promise<void>;
      await act(async () => {
        waiting = current.sendStart.whenReplySettled().then(() => { settled = true; });
      });
      expect(settled).toBe(false);
      await act(async () => {
        socket.emit({ type: "done", message_id: "saved-again", final_content: "better answer" });
      });
      await act(async () => { await waiting; });
      expect(current.messages.map((message) => message.id)).toEqual([expect.stringMatching(/^local-/), "saved-again"]);
      expect(current.messages[1].content).toBe("better answer");
    });

    it("puts a regenerated reply's old answer back above the waiting bubble when its save fails", async () => {
      await render(<Probe chatId="a" />);
      const socket = await openSocket();
      await act(async () => {
        current.editThread([
          { id: "u1", role: "user", content: "q1", model: null, created_at: "t1" },
          { id: "r1", role: "assistant", content: "old answer", model: null, created_at: "t2" },
        ], "page_refresh");
      });
      await act(async () => {
        current.beginRegenerateUi();
        await current.regenerateResponse();
        socket.emit({ type: "start" });
        socket.emit({ type: "token", content: "new answer" });
        jest.advanceTimersByTime(20);
        socket.emit({ type: "stream_end" });
      });
      let waiting!: Promise<void>;
      await act(async () => {
        current.editThread((rows) => [...rows, next], "page_refresh");
        waiting = current.sendStart.whenReplySettled("local-2");
      });
      await act(async () => {
        socket.emit({ type: "error", message: "Failed to save the response. Please retry.", user_message_saved: true });
      });
      await act(async () => { await waiting; });
      expect(current.messages.map((message) => `${message.id}:${message.content}`)).toEqual([
        "u1:q1", "r1:old answer", "local-2:next",
      ]);
    });

    it("waits for nothing after Stop", async () => {
      await render(<Probe chatId="a" />);
      const socket = await openSocket();
      await sendAndStream(socket);
      await act(async () => { current.stopGeneration(); });
      let settled = false;
      await act(async () => {
        await current.sendStart.whenReplySettled().then(() => { settled = true; });
      });
      expect(settled).toBe(true);
    });
  });

  it("announces a finished reply once, not per token", async () => {
    const announce = jest.spyOn(AccessibilityInfo, "announceForAccessibility").mockImplementation(() => {});
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await act(async () => {
      await current.sendMessage("question");
      socket.emit({ type: "start" });
      socket.emit({ type: "token", content: "hello" });
      socket.emit({ type: "token", content: " there" });
    });
    expect(announce).not.toHaveBeenCalled();
    await act(async () => {
      socket.emit({ type: "done", message_id: "saved", final_content: "hello there" });
    });
    expect(announce).toHaveBeenCalledTimes(1);
    expect(announce).toHaveBeenCalledWith("chat.reply_ready");
  });

});

describe("useChat socket while the app is in the background", () => {
  const originalSocket = globalThis.WebSocket;
  const addListener = AppState.addEventListener as unknown as jest.Mock;
  const defaultAddListener = addListener.getMockImplementation();
  const appStateHandlers = new Set<(state: string) => void>();
  const setAppState = async (state: string) => {
    await act(async () => {
      for (const handler of [...appStateHandlers]) handler(state);
    });
  };

  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    listMessages.mockReset();
    FakeSocket.instances = [];
    mockSessionGeneration = 0;
    globalThis.WebSocket = FakeSocket as unknown as typeof WebSocket;
    resetStreamingDraftStore();
    appStateHandlers.clear();
    addListener.mockImplementation((event: string, handler: (state: string) => void) => {
      if (event !== "change") return { remove: jest.fn() };
      appStateHandlers.add(handler);
      return { remove: () => appStateHandlers.delete(handler) };
    });
  });
  afterEach(async () => {
    await cleanup();
    jest.clearAllTimers();
    jest.useRealTimers();
    globalThis.WebSocket = originalSocket;
    addListener.mockImplementation(defaultAddListener);
  });

  it("closes an idle chat socket in the background and reopens it on return", async () => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    // An idle socket left open only answers the server's keepalive pings,
    // which wakes the radio every 20 seconds for as long as the app lives.
    await setAppState("inactive");
    expect(socket.close).not.toHaveBeenCalled();
    await setAppState("background");
    expect(socket.close).toHaveBeenCalledTimes(1);
    expect(FakeSocket.instances).toHaveLength(1);

    await setAppState("active");
    expect(FakeSocket.instances).toHaveLength(2);
    const reopened = FakeSocket.instances[1];
    expect(reopened.url).toMatch(/^wss:\/\/test\/a\?request_id=[\w-]+$/);
    await act(async () => { reopened.open(); });
    await sendAndStream(reopened, "after resume");
    expect(reopened.send).toHaveBeenCalledWith(expect.stringContaining("\"type\":\"message\""));
    expect(streamChatMessageSse).not.toHaveBeenCalled();
  });

  it("lets a reply in flight finish before releasing the socket", async () => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await sendAndStream(socket, "partial");
    await setAppState("background");
    expect(socket.close).not.toHaveBeenCalled();
    await act(async () => {
      socket.emit({ type: "token", content: " more" });
      socket.emit({ type: "done", message_id: "saved", final_content: "partial more" });
    });
    expect(current.streaming).toBe(false);
    expect(current.messages.some((message) => message.content === "partial more")).toBe(true);
    expect(socket.close).toHaveBeenCalledTimes(1);
    expect(onError).not.toHaveBeenCalled();
  });

  it("probes the socket a turn kept through the background when the app returns", async () => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await act(async () => { socket.emit({ type: "pong" }); });
    await sendAndStream(socket, "partial");
    await setAppState("background");
    await setAppState("active");
    expect(JSON.parse(socket.send.mock.calls.at(-1)?.[0])).toEqual({ type: "ping" });
    expect(FakeSocket.instances).toHaveLength(1);
  });

  it("does not open a second socket when the first was never released", async () => {
    await render(<Probe chatId="a" />);
    await openSocket();
    await setAppState("active");
    expect(FakeSocket.instances).toHaveLength(1);
  });
});

describe("useChat socket recovery", () => {
  const originalSocket = globalThis.WebSocket;
  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    listMessages.mockReset();
    FakeSocket.instances = [];
    mockSessionGeneration = 0;
    mockNetInfoListeners.clear();
    // Earlier tests can leave a queued one-off stream behind.
    (streamChatMessageSse as jest.Mock).mockReset();
    (streamChatRegenerateSse as jest.Mock).mockReset();
    globalThis.WebSocket = FakeSocket as unknown as typeof WebSocket;
    resetStreamingDraftStore();
  });
  afterEach(async () => {
    await cleanup();
    jest.clearAllTimers();
    jest.useRealTimers();
    globalThis.WebSocket = originalSocket;
  });

  const frames = (socket: FakeSocket) =>
    socket.send.mock.calls.map(([data]) => JSON.parse(data) as Record<string, unknown>);
  const latestSocket = () => FakeSocket.instances[FakeSocket.instances.length - 1];
  const network = async (state: object) => {
    await act(async () => { for (const listener of [...mockNetInfoListeners]) listener(state); });
  };
  const WIFI = { type: "wifi", isConnected: true, isInternetReachable: true, details: { ipAddress: "192.168.1.5" } };
  const CELLULAR = { type: "cellular", isConnected: true, isInternetReachable: true, details: {} };
  const answeredSse = (reply: string) => async ({ onEvent }: { onEvent: (payload: object) => void }) => {
    onEvent({ type: "start" });
    onEvent({ type: "token", content: reply });
    onEvent({ type: "done", message_id: `saved-${reply}`, final_content: reply });
  };

  /** A socket whose server answers pings, as every server with resend dedupe does. */
  async function openProbedSocket() {
    const socket = await openSocket();
    await act(async () => { socket.emit({ type: "pong" }); });
    return socket;
  }

  it("tells the server the phone's zone of the moment: on each turn, and on each socket it opens", async () => {
    mockZone = "America/New_York";
    await render(<Probe chatId="a" />);
    const first = await openSocket();
    expect(frames(first)[0]).toEqual({ token: "token", client_timezone: "America/New_York" });

    // The phone lands in another zone; the socket stays open.
    mockZone = "Europe/London";
    await act(async () => {
      await current.sendMessage("what time is it?");
      first.emit({ type: "start" });
      first.emit({ type: "done", message_id: "saved", final_content: "Noon." });
    });
    expect(frames(first).find((frame) => frame.type === "message")).toMatchObject({ client_timezone: "Europe/London" });
    mockZone = "Asia/Tokyo";
    await act(async () => {
      current.beginRegenerateUi();
      await current.regenerateResponse();
      first.emit({ type: "done", message_id: "saved-again", final_content: "Still noon." });
    });
    expect(frames(first).find((frame) => frame.type === "regenerate")).toMatchObject({ client_timezone: "Asia/Tokyo" });

    // The server closes it for idling; the next send's socket opens in the zone of then.
    mockZone = "Australia/Sydney";
    await act(async () => { (first.onclose as (event: { code: number }) => void)({ code: 4408 }); });
    await act(async () => {
      const sending = current.sendMessage("and now?");
      latestSocket().open();
      await sending;
    });
    const second = latestSocket();
    expect(second).not.toBe(first);
    expect(frames(second)[0]).toEqual({ token: "token", client_timezone: "Australia/Sydney" });
    expect(frames(second).find((frame) => frame.type === "message")).toMatchObject({ client_timezone: "Australia/Sydney" });
  });

  it("names each message, and Retry sends the same name again", async () => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await act(async () => {
      await current.sendMessage("first");
      socket.emit({ type: "error", code: "busy" });
    });
    await act(async () => {
      await current.retryRejectedSend();
      socket.emit({ type: "done", message_id: "saved-first", final_content: "answer" });
    });
    await act(async () => { await current.sendMessage("second"); });
    const names = frames(socket).filter((frame) => frame.type === "message").map((frame) => frame.client_message_id);
    expect(names).toHaveLength(3);
    expect(typeof names[0]).toBe("string");
    expect(names[1]).toBe(names[0]);
    expect(names[2]).not.toBe(names[0]);
  });

  it("replays a send its dead socket never acknowledged over SSE, under the same name", async () => {
    (streamChatMessageSse as jest.Mock).mockImplementationOnce(answeredSse("recovered"));
    await render(<Probe chatId="a" />);
    const socket = await openProbedSocket();
    await act(async () => { await current.sendMessage("question"); });
    const name = frames(socket).find((frame) => frame.type === "message")?.client_message_id;
    await act(async () => { jest.advanceTimersByTime(WS_ACK_PROBE_MS); });
    expect(frames(socket).at(-1)).toEqual({ type: "ping" });
    expect(streamChatMessageSse).not.toHaveBeenCalled();

    await act(async () => { jest.advanceTimersByTime(WS_PROBE_TIMEOUT_MS); });
    expect(socket.close).toHaveBeenCalledTimes(1);
    expect(streamChatMessageSse).toHaveBeenCalledTimes(1);
    expect(streamChatMessageSse).toHaveBeenCalledWith(expect.objectContaining({
      content: "question", clientMessageId: name,
    }));
    expect(current.messages.filter((message) => message.role === "user")).toHaveLength(1);
    expect(current.messages).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: "saved-recovered", content: "recovered" }),
    ]));
    expect(current.streaming).toBe(false);
    expect(onError).not.toHaveBeenCalled();
  });

  it("follows the first send when the server says the replay is a duplicate", async () => {
    (streamChatMessageSse as jest.Mock).mockImplementationOnce(async ({ onEvent }) => {
      onEvent({ type: "duplicate" });
    });
    const saved = [
      { id: SERVER_USER_ID, role: "user" as const, content: "question", model: null, created_at: "t1" },
      { id: SERVER_REPLY_ID, role: "assistant" as const, content: "first turn's reply", model: null, created_at: "t2" },
    ];
    listMessages.mockResolvedValue({ messages: saved, has_more: false });
    await render(<Probe chatId="a" />);
    await openProbedSocket();
    await act(async () => { await current.sendMessage("question"); });
    await act(async () => { jest.advanceTimersByTime(WS_ACK_PROBE_MS + WS_PROBE_TIMEOUT_MS); });
    expect(current.streaming).toBe(true);
    await act(async () => { await jest.advanceTimersByTimeAsync(DROPPED_TURN_MAX_WAIT_MS); });
    expect(current.messages).toEqual(saved);
    expect(current.streaming).toBe(false);
    expect(streamChatMessageSse).toHaveBeenCalledTimes(1);
    expect(current.rejectedSend).toBeNull();
    expect(onError).not.toHaveBeenCalled();
  });

  it("neither drops the socket nor replays a send the user stopped while it was probed", async () => {
    await render(<Probe chatId="a" />);
    const socket = await openProbedSocket();
    await act(async () => { await current.sendMessage("question"); });
    await act(async () => { jest.advanceTimersByTime(WS_ACK_PROBE_MS); });
    expect(frames(socket).at(-1)).toEqual({ type: "ping" });
    await act(async () => { current.stopGeneration(); });
    await act(async () => { jest.advanceTimersByTime(WS_FIRST_EVENT_TIMEOUT_MS); });
    expect(socket.close).not.toHaveBeenCalled();
    expect(streamChatMessageSse).not.toHaveBeenCalled();
    expect(current.streaming).toBe(false);
    expect(onError).not.toHaveBeenCalled();
  });

  it("sends a Retry under a new name after a duplicate whose message never showed up", async () => {
    // A held claim whose turn never saved: a machine that died mid-turn keeps
    // the name for 15 min, so the same name would be told duplicate again.
    listMessages.mockResolvedValue({ messages: [], has_more: false });
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await act(async () => {
      await current.sendMessage("question");
      socket.emit({ type: "error", code: "busy" });
    });
    await act(async () => { await current.retryRejectedSend(); });
    const sent = () => frames(socket).filter((frame) => frame.type === "message");
    expect(sent()[1].client_message_id).toBe(sent()[0].client_message_id);
    await act(async () => { socket.emit({ type: "duplicate" }); });
    expect(current.streaming).toBe(true);
    for (let poll = 0; poll < DUPLICATE_TURN_POLLS; poll += 1) {
      await act(async () => { await jest.advanceTimersByTimeAsync(duplicateTurnPollMs(poll)); });
    }
    expect(current.streaming).toBe(false);
    expect(current.rejectedSend?.content).toBe("question");
    expect(onError).toHaveBeenLastCalledWith("chat.error_unreachable", "send_rejected");

    await act(async () => { await current.retryRejectedSend(); });
    expect(sent()).toHaveLength(3);
    expect(sent()[2].client_message_id).not.toBe(sent()[0].client_message_id);
    expect(current.messages.filter((message) => message.role === "user")).toHaveLength(1);
  });

  it("sends over SSE while the dead socket's wait runs, then over a new socket", async () => {
    (streamChatMessageSse as jest.Mock)
      .mockImplementationOnce(answeredSse("replayed"))
      .mockImplementationOnce(answeredSse("over SSE"));
    await render(<Probe chatId="a" />);
    await openProbedSocket();
    await act(async () => { await current.sendMessage("lost"); });
    await act(async () => { jest.advanceTimersByTime(WS_ACK_PROBE_MS + WS_PROBE_TIMEOUT_MS); });
    expect(streamChatMessageSse).toHaveBeenCalledTimes(1);

    await act(async () => { await current.sendMessage("soon after"); });
    expect(streamChatMessageSse).toHaveBeenCalledTimes(2);
    expect(FakeSocket.instances).toHaveLength(1);

    await act(async () => { jest.advanceTimersByTime(WS_RETRY_BASE_MS); });
    let sending!: Promise<unknown>;
    await act(async () => { sending = current.sendMessage("later"); });
    const next = latestSocket();
    expect(FakeSocket.instances).toHaveLength(2);
    await act(async () => { next.open(); await sending; });
    expect(frames(next).at(-1)).toMatchObject({ type: "message", content: "later" });
    expect(streamChatMessageSse).toHaveBeenCalledTimes(2);
  });

  it("opens a new socket with a refreshed token once the old one's reply and follow-ups are in", async () => {
    mockToken = "token-1";
    await render(<Probe chatId="a" />);
    const first = await openSocket();
    await act(async () => {
      await current.sendMessage("question");
      first.emit({ type: "start" });
    });
    mockToken = "token-2";
    await act(async () => { void current.connect(); });
    expect(first.close).not.toHaveBeenCalled();
    expect(FakeSocket.instances).toHaveLength(1);

    // The reply's follow-up questions come after its done, on this socket.
    await act(async () => { first.emit({ type: "done", message_id: "saved", final_content: "answer" }); });
    await act(async () => { void current.connect(); });
    expect(first.close).not.toHaveBeenCalled();
    await act(async () => {
      first.emit({ type: "related_prompts", message_id: "saved", prompts: ["Why does it work?"] });
    });
    expect(current.messages.find((message) => message.id === "saved")?.related_prompts)
      .toEqual(["Why does it work?"]);
    expect(first.close).toHaveBeenCalledTimes(1);
    const second = latestSocket();
    expect(FakeSocket.instances).toHaveLength(2);
    await act(async () => { second.open(); });
    expect(frames(second)[0]).toEqual({ token: "token-2", client_timezone: "UTC" });

    // An idle socket is replaced at the next connect after the token changes.
    mockToken = "token-3";
    await act(async () => { void current.connect(); });
    expect(second.close).toHaveBeenCalledTimes(1);
    await act(async () => { latestSocket().open(); });
    expect(frames(latestSocket())[0]).toEqual({ token: "token-3", client_timezone: "UTC" });
  });

  it("replaces a refreshed token's socket on the next intent when no follow-ups come", async () => {
    mockToken = "token-1";
    await render(<Probe chatId="a" />);
    const first = await openSocket();
    await act(async () => {
      await current.sendMessage("question");
      first.emit({ type: "start" });
    });
    mockToken = "token-2";
    await act(async () => { first.emit({ type: "done", message_id: "saved", final_content: "answer" }); });
    await act(async () => { jest.advanceTimersByTime(WS_FOLLOW_UPS_WAIT_MS); });
    expect(first.close).not.toHaveBeenCalled();
    await act(async () => { void current.connect(); });
    expect(first.close).toHaveBeenCalledTimes(1);
    await act(async () => { latestSocket().open(); });
    expect(frames(latestSocket())[0]).toEqual({ token: "token-2", client_timezone: "UTC" });
  });

  it("replaces an idle socket after a network switch and stays off it while offline", async () => {
    await render(<Probe chatId="a" />);
    const first = await openSocket();
    await network(WIFI);
    expect(first.close).not.toHaveBeenCalled();

    await network(CELLULAR);
    expect(first.close).toHaveBeenCalledTimes(1);
    expect(FakeSocket.instances).toHaveLength(2);
    expect(latestSocket().url).toMatch(/^wss:\/\/test\/a\?request_id=[\w-]+$/);

    await network({ type: "none", isConnected: false, isInternetReachable: false, details: null });
    expect(latestSocket().close).toHaveBeenCalledTimes(1);
    expect(FakeSocket.instances).toHaveLength(2);
    await network(WIFI);
    expect(FakeSocket.instances).toHaveLength(3);
  });

  it("leaves a socket the server closed for idling closed on a network switch", async () => {
    await render(<Probe chatId="a" />);
    const first = await openSocket();
    await network(WIFI);
    await act(async () => { (first.onclose as (event: { code: number }) => void)({ code: 4408 }); });
    await network(CELLULAR);
    await network(WIFI);
    expect(FakeSocket.instances).toHaveLength(1);
    expect(onError).not.toHaveBeenCalled();
  });

  it("tries the socket again at once on a new network, whatever failed on the old one", async () => {
    await render(<Probe chatId="a" />);
    await network(WIFI);
    await act(async () => { void current.connect(); });
    const stalled = latestSocket();
    await act(async () => { jest.advanceTimersByTime(WS_CONNECT_TIMEOUT_MS); });
    expect(stalled.close).toHaveBeenCalledTimes(1);
    await act(async () => { void current.connect(); });
    expect(FakeSocket.instances).toHaveLength(1);

    await network(CELLULAR);
    await act(async () => { void current.connect(); });
    expect(FakeSocket.instances).toHaveLength(2);
  });

  it("probes a turn's socket after a network switch and follows the turn if it is dead", async () => {
    const saved = [
      { id: SERVER_USER_ID, role: "user" as const, content: "question", model: null, created_at: "t1" },
      { id: SERVER_REPLY_ID, role: "assistant" as const, content: "whole reply", model: null, created_at: "t2" },
    ];
    listMessages.mockResolvedValue({ messages: saved, has_more: false });
    await render(<Probe chatId="a" />);
    await network(WIFI);
    const socket = await openProbedSocket();
    await sendAndStream(socket, "partial");
    await network(CELLULAR);
    expect(frames(socket).at(-1)).toEqual({ type: "ping" });
    expect(socket.close).not.toHaveBeenCalled();

    await act(async () => { jest.advanceTimersByTime(WS_PROBE_TIMEOUT_MS); });
    expect(socket.close).toHaveBeenCalledTimes(1);
    await act(async () => { await jest.advanceTimersByTimeAsync(DROPPED_TURN_MAX_WAIT_MS); });
    expect(current.messages).toEqual(saved);
    expect(streamChatMessageSse).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
  });

  it("keeps a turn's socket that answers the probe after a network switch", async () => {
    await render(<Probe chatId="a" />);
    await network(WIFI);
    const socket = await openProbedSocket();
    await sendAndStream(socket, "partial");
    await network(CELLULAR);
    await act(async () => {
      socket.emit({ type: "pong" });
      jest.advanceTimersByTime(WS_PROBE_TIMEOUT_MS);
      socket.emit({ type: "done", message_id: "saved", final_content: "partial and the rest" });
    });
    expect(socket.close).not.toHaveBeenCalled();
    expect(current.messages.some((message) => message.content === "partial and the rest")).toBe(true);
  });
});

describe("useChat while the opened chat's page is read", () => {
  const originalSocket = globalThis.WebSocket;
  const sentTypes = (socket: FakeSocket) => socket.send.mock.calls.map(([data]) => JSON.parse(data).type);
  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    listMessages.mockReset();
    FakeSocket.instances = [];
    mockSessionGeneration = 0;
    globalThis.WebSocket = FakeSocket as unknown as typeof WebSocket;
    resetStreamingDraftStore();
  });
  afterEach(async () => {
    await cleanup();
    jest.clearAllTimers();
    jest.useRealTimers();
    globalThis.WebSocket = originalSocket;
  });

  it("paints the turn on the tap and sends it once the page is in", async () => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    const read = beginOpenedPageRead("a");
    let sending!: Promise<unknown>;
    await act(async () => { sending = current.sendMessage("question"); });
    expect(current.messages.map((message) => message.content)).toEqual(["question", ""]);
    expect(current.streaming).toBe(true);
    expect(sentTypes(socket)).not.toContain("message");
    await act(async () => { expect(read.release()).toBe(true); await sending; });
    expect(sentTypes(socket)).toContain("message");
  });

  it("sends anyway when the page takes too long, and that page is then not merged", async () => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    const read = beginOpenedPageRead("a");
    await act(async () => { void current.sendMessage("question"); });
    await act(async () => { await jest.advanceTimersByTimeAsync(OPENED_PAGE_WAIT_MS - 1); });
    expect(sentTypes(socket)).not.toContain("message");
    await act(async () => { await jest.advanceTimersByTimeAsync(1); });
    expect(sentTypes(socket)).toContain("message");
    expect(read.release()).toBe(false);
  });

  it("never sends a turn whose chat turned out to be gone, and hands its text back", async () => {
    const stash = jest.fn();
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    const read = beginOpenedPageRead("a");
    let sending!: Promise<unknown>;
    await act(async () => {
      sending = current.sendMessage("question", { composerDraft: { text: "question", attachment: null } });
    });
    await act(async () => { read.chatGone({ stashFailedDraftForThread: stash }); await sending; });
    expect(sentTypes(socket)).not.toContain("message");
    expect(streamChatMessageSse).not.toHaveBeenCalled();
    expect(stash).toHaveBeenCalledWith("new", "question");
  });

  it("holds a regeneration until the page is in", async () => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await sendAndStream(socket);
    await act(async () => { socket.emit({ type: "done", message_id: "saved", final_content: "original" }); });
    const read = beginOpenedPageRead("a");
    let regenerating!: Promise<void>;
    await act(async () => { current.beginRegenerateUi(); regenerating = current.regenerateResponse(); });
    expect(sentTypes(socket)).not.toContain("regenerate");
    await act(async () => { read.release(); await regenerating; });
    expect(sentTypes(socket)).toContain("regenerate");
  });
  // Stop offered while the turn waits (Send is idle once it is handed over) must take it back,
  // like a send stopped before it was handed over: no bubble left that looks sent but never went out.
  it("takes back a turn stopped while it waits for the page: nothing goes out, and its sender returns the draft", async () => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    const read = beginOpenedPageRead("a");
    let sending!: Promise<boolean>;
    await act(async () => {
      sending = current.sendMessage("question", { composerDraft: { text: "question", attachment: null } });
    });
    expect(current.messages.map((message) => message.id)).toEqual([expect.stringMatching(/^local-/), "streaming"]);
    let sent: boolean | undefined;
    void sending.then((value) => { sent = value; });
    await act(async () => {
      current.stopGeneration();
      for (let i = 0; i < 10; i++) await Promise.resolve();
    });
    // At once, without waiting for the page: the bubble and dots are gone, and false has the sender return the draft.
    expect(sent).toBe(false);
    expect(current.messages).toEqual([]);
    expect(current.streaming).toBe(false);
    // The page that lands later merges as usual, and the page read does not hand the turn back a second time.
    const home = { stashFailedDraftForThread: jest.fn() };
    await act(async () => { await jest.advanceTimersByTimeAsync(OPENED_PAGE_WAIT_MS); });
    read.cancel(home);
    expect(home.stashFailedDraftForThread).not.toHaveBeenCalled();
    expect(read.release()).toBe(true);
    expect(sentTypes(socket)).not.toContain("message");
    expect(streamChatMessageSse).not.toHaveBeenCalled();
  });

  it("does not have Stop hand back a turn the page read already handed back (its chat was deleted)", async () => {
    const stash = jest.fn();
    await render(<Probe chatId="a" />);
    await openSocket();
    const read = beginOpenedPageRead("a");
    let sending!: Promise<boolean>;
    await act(async () => {
      sending = current.sendMessage("question", { composerDraft: { text: "question", attachment: null } });
    });
    // The route loader hands the turn to New Chat's composer, then New Chat stops the turn.
    let sent: boolean | undefined;
    await act(async () => {
      read.chatGone({ stashFailedDraftForThread: stash });
      current.stopGeneration();
      sent = await sending;
    });
    expect(sent).toBe(true);
    expect(stash).toHaveBeenCalledTimes(1);
    expect(stash).toHaveBeenCalledWith("new", "question");
  });

  it("never sends a regeneration stopped while it waits for the page, and that page still merges", async () => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    await sendAndStream(socket);
    await act(async () => { socket.emit({ type: "done", message_id: "saved", final_content: "original" }); });
    const read = beginOpenedPageRead("a");
    let regenerating!: Promise<void>;
    await act(async () => { current.beginRegenerateUi(); regenerating = current.regenerateResponse(); });
    let over = false;
    void regenerating.then(() => { over = true; });
    await act(async () => {
      current.stopGeneration();
      for (let i = 0; i < 10; i++) await Promise.resolve();
    });
    expect(over).toBe(true);
    expect(current.messages.map((message) => message.id)).toEqual([expect.stringMatching(/^local-/), "saved"]);
    await act(async () => { await jest.advanceTimersByTimeAsync(OPENED_PAGE_WAIT_MS); });
    expect(read.release()).toBe(true);
    expect(sentTypes(socket)).not.toContain("regenerate");
  });

  it("keeps a turn that went out when Stop comes after it was sent", async () => {
    await render(<Probe chatId="a" />);
    const socket = await openSocket();
    const read = beginOpenedPageRead("a");
    let sending!: Promise<boolean>;
    await act(async () => { sending = current.sendMessage("question"); });
    let sent: boolean | undefined;
    await act(async () => { read.release(); sent = await sending; });
    expect(sent).toBe(true);
    await act(async () => { current.stopGeneration(); });
    expect(current.messages.map((message) => message.content)).toEqual(["question"]);
    expect(sentTypes(socket).filter((type) => type === "message" || type === "cancel")).toEqual(["message", "cancel"]);
  });
});

describe("a photo or file deleted from Library", () => {
  const PHOTO = "0190a000-0000-7000-8000-0000000000aa";
  const OTHER = "0190a000-0000-7000-8000-0000000000bb";
  const row = (id: string, role: "user" | "assistant", content: string) =>
    ({ id, role, content, model: null, created_at: "now" });
  const thread = () => [
    { ...row("u1", "user", `what is this?\n\n[Image: /attachments/${PHOTO}/file]`), local_image_uri: "file:///p.jpg" },
    row("a1", "assistant", "A cat."),
    row("u2", "user", "draw a dog"),
    row("a2", "assistant", `[Image: /attachments/${OTHER}/file]`),
  ];
  afterEach(async () => { await cleanup(); });

  it("leaves the open chat the way it left the server's copy", async () => {
    await render(<Probe chatId="chat-1" />);
    await act(async () => { current.editThread(thread(), "page_refresh"); });
    await act(async () => { emitAppEvent("attachmentDeleted", { attachmentId: OTHER, chatId: "chat-1" }); });
    // The picture was the whole reply: the server deleted the row.
    expect(current.messages.map((message) => message.id)).toEqual(["u1", "a1", "u2"]);
    await act(async () => { emitAppEvent("attachmentDeleted", { attachmentId: PHOTO, chatId: "chat-1" }); });
    expect(current.messages[0]).toMatchObject({ id: "u1", content: "what is this?", local_image_uri: null });
  });

  it("leaves another chat's list alone", async () => {
    await render(<Probe chatId="chat-2" />);
    await act(async () => { current.editThread(thread(), "page_refresh"); });
    await act(async () => { emitAppEvent("attachmentDeleted", { attachmentId: OTHER, chatId: "chat-1" }); });
    expect(current.messages).toHaveLength(4);
  });
});

describe("the thread's one owner", () => {
  afterEach(async () => { await cleanup(); });
  const row = { id: "early", role: "user" as const, content: "painted early", model: null, created_at: "now" };

  /** A writer whose layout effect runs before useChat's own: a child's runs first. */
  function EarlyWriter({ editThread }: { editThread: ReturnType<typeof useChat>["editThread"] }) {
    React.useLayoutEffect(() => { editThread((rows) => [...rows, row], "cached_paint"); }, [editThread]);
    return null;
  }
  function Owner() {
    const chat = useChat("token", "chat-1", { onError });
    React.useLayoutEffect(() => { current = chat; });
    return <EarlyWriter editThread={chat.editThread} />;
  }

  it("keeps an edit made before its first layout effect, instead of dropping it", async () => {
    await render(<Owner />);
    expect(current.messages).toEqual([row]);
  });

  it("hands out no raw setter for the thread, under any name", async () => {
    let setter: unknown;
    function Control() {
      const [, set] = React.useState(0);
      React.useLayoutEffect(() => { setter = set; }, [set]);
      return null;
    }
    await render(<><Probe chatId="chat-1" /><Control /></>);
    // React's setters share one name; the check would see a setter useChat handed out.
    const setterName = (setter as { name: string }).name;
    expect(setterName).toMatch(/dispatch/i);
    const raw = Object.entries(current).filter(
      ([, value]) => typeof value === "function" && (value as { name: string }).name === setterName,
    );
    expect(raw).toEqual([]);
  });
});

// 2026-11-01: a picture still generating when the user opened another chat landed in that chat.
describe("a picture that outlives its chat", () => {
  afterEach(async () => { await cleanup(); });
  const row = (id: string, content: string) => ({ id, role: "user" as const, content, model: null, created_at: "now" });
  const saved = { user_message: row("saved-user", "Draw a cat"), assistant_message: { ...row("saved-image", "image"), role: "assistant" as const } };
  const ids = () => current.messages.map((message) => message.id);
  const scrolled = jest.fn();
  let picture: ReturnType<typeof useImageGeneration>;
  let openChat: (chatId: string | null) => void;

  /** The chat screen's two writers: the turn's thread and a picture, which makes a chat when none is open. */
  function Screen({ initial }: { initial: string | null }) {
    const [chatId, setChatId] = React.useState(initial);
    const chat = useChat("token", chatId, { onError });
    const count = React.useRef(0);
    const generation = useImageGeneration({
      token: "token",
      ensureChatId: async () => { if (chatId) return chatId; setChatId("new-1"); return "new-1"; },
      uploadReference: async () => ({ ids: [] }),
      describeFailure: (message) => ({ message, retryable: true }),
      editThread: chat.editThread,
      streaming: false, isOffline: false, onOpenUpgrade: () => {}, onScrollToLatest: scrolled,
      newMessageCountRef: count, t: (key) => key,
    });
    React.useLayoutEffect(() => { current = chat; picture = generation; openChat = setChatId; }, [chat, generation]);
    return null;
  }

  /** Starts a picture that finishes when the returned call says; `finish` runs inside the caller's act. */
  async function startPicture() {
    let resolve!: (value: typeof saved) => void;
    generateImage.mockReturnValueOnce(new Promise((done) => { resolve = done; }));
    let pending!: Promise<void>;
    await act(async () => { pending = picture.submitPrompt({ prompt: "cat", userMessage: "Draw a cat" }); });
    scrolled.mockClear();
    return async () => { resolve(saved); await pending; };
  }

  it.each([
    ["another chat", "chat-b"],
    ["a new chat", null],
  ])("leaves %s as it is, without scrolling it", async (_name, next) => {
    await render(<Screen initial="chat-a" />);
    const finish = await startPicture();
    await act(async () => { openChat(next); });
    const page = [row("b-1", "chat b")];
    await act(async () => { current.editThread(page, "opened_page"); });
    await act(finish);
    expect(current.messages).toEqual(page);
    expect(scrolled).not.toHaveBeenCalled();
  });

  it("shows once back in its chat, though the page read on return already holds it", async () => {
    await render(<Screen initial="chat-a" />);
    const finish = await startPicture();
    await act(async () => { openChat("chat-b"); });
    await act(finish);
    const page = [row("a-1", "chat a"), saved.user_message, saved.assistant_message];
    await act(async () => { openChat("chat-a"); current.editThread(page, "cached_paint"); });
    expect(ids()).toEqual(["a-1", "saved-user", "saved-image"]);
  });

  it("shows when it finishes while its chat reopens, before the view names it, over a page read before it was saved", async () => {
    await render(<Screen initial="chat-a" />);
    const finish = await startPicture();
    await act(async () => { openChat("chat-b"); });
    const painted = [row("a-1", "chat a")];
    await act(async () => {
      // The route paints chat A and sends its page read; the turn still shows chat B until the next render.
      openChat("chat-a");
      current.editThread(painted, "cached_paint");
      await finish();
    });
    await act(async () => {
      current.editThread((prev) => mergeOpenedPage(prev, painted, new Set(["a-1"])), "opened_page");
    });
    expect(ids()).toEqual(["a-1", "saved-user", "saved-image"]);
  });

  it("lands in the chat it made, though that chat reached the turn a render later", async () => {
    generateImage.mockResolvedValueOnce(saved);
    await render(<Screen initial={null} />);
    await act(async () => { await picture.submitPrompt({ prompt: "cat", userMessage: "Draw a cat" }); });
    expect(ids()).toEqual(["saved-user", "saved-image"]);
  });

  it("waits for the chat it made once the user left it for a new one", async () => {
    await render(<Screen initial={null} />);
    const finish = await startPicture();
    await act(async () => { openChat(null); });
    await act(async () => { current.editThread([], "view_cleared"); });
    await act(finish);
    expect(current.messages).toEqual([]);
  });
});
