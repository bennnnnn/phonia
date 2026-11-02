import { speechApi } from "@/features/speech/api";
import { createRealtimeVoiceSession, type RealtimeVoiceEvent } from "@/features/speech/model/realtimeVoice";
import { requireOptionalNativeModule } from "expo-modules-core";
import * as webrtc from "react-native-webrtc";

jest.mock("react-native", () => ({
  Platform: { OS: "ios" },
  NativeModules: { WebRTCModule: {} },
  TurboModuleRegistry: { get: (name: string) => (name === "WebRTCModule" ? {} : null) },
}));
jest.mock("expo-modules-core", () => ({ requireOptionalNativeModule: jest.fn() }));
jest.mock("expo-constants", () => ({}));
jest.mock("@/lib/speech/voiceAudio", () => ({ yieldMicToWebRtc: jest.fn(async () => undefined) }));
jest.mock("@/features/speech/api", () => ({
  speechApi: { createRealtimeSession: jest.fn(), realtimeTool: jest.fn(), endRealtimeSession: jest.fn() },
}));
jest.mock("react-native-webrtc", () => ({
  mediaDevices: { getUserMedia: jest.fn() },
  RTCPeerConnection: jest.fn(),
  RTCSessionDescription: jest.fn((value) => value),
}));

/** "phone" has echo cancellation, so the user can talk over the reply; the Simulator is half duplex. */
type Device = "phone" | "simulator";

type FakeChannel = {
  readyState: string;
  send: jest.Mock;
  close: jest.Mock;
  onopen?: () => void;
  onmessage?: (message: { data?: unknown }) => void;
};

const originalFetch = globalThis.fetch;

function dial(device: Device, options: { open?: boolean; sessionCreated?: boolean } = {}) {
  (requireOptionalNativeModule as jest.Mock).mockReturnValue({ isDevice: device === "phone" });
  const mic = { kind: "audio", enabled: true, stop: jest.fn() };
  const channel: FakeChannel = { readyState: "open", send: jest.fn(), close: jest.fn() };
  const emit = (event: object) => channel.onmessage?.({ data: JSON.stringify(event) });
  const pc = {
    connectionState: "new",
    onconnectionstatechange: undefined as undefined | (() => void),
    addTrack: jest.fn(),
    createDataChannel: () => channel,
    createOffer: async () => ({ sdp: "v=0\nm=audio" }),
    setLocalDescription: async () => undefined,
    setRemoteDescription: async () => {
      if (options.open === false) return;
      channel.onopen?.();
      if (options.sessionCreated !== false) emit({ type: "session.created" });
    },
    close: jest.fn(),
    getReceivers: () => [],
  };
  (webrtc.mediaDevices.getUserMedia as jest.Mock).mockResolvedValue({ getAudioTracks: () => [mic], getTracks: () => [mic] });
  (webrtc.RTCPeerConnection as unknown as jest.Mock).mockImplementation(() => pc);
  const events: RealtimeVoiceEvent[] = [];
  const pending = createRealtimeVoiceSession({ token: "tok", chatId: "chat-1", onEvent: (event) => events.push(event) });
  const sent = () => channel.send.mock.calls.map(([value]) => JSON.parse(value) as Record<string, unknown>);
  const types = () => events.map((event) => event.type);
  const userTurn = (id: string) => {
    emit({ type: "input_audio_buffer.speech_started", item_id: id });
    emit({ type: "input_audio_buffer.speech_stopped", item_id: id });
  };
  return { pending, mic, channel, pc, events, emit, sent, types, userTurn };
}

async function start(device: Device, options: { sessionCreated?: boolean } = {}) {
  const call = dial(device, options);
  return { ...call, session: await call.pending };
}

/** Connected, past the warmup, and the assistant is answering u1 with a1. */
async function replying(device: Device) {
  const call = await start(device);
  jest.advanceTimersByTime(1_500);
  call.userTurn("u1");
  call.emit({ type: "response.created", response: { id: "a1" } });
  return call;
}

beforeEach(() => {
  jest.useFakeTimers();
  jest.clearAllMocks();
  (globalThis as unknown as { __DEV__: boolean }).__DEV__ = false;
  (speechApi.createRealtimeSession as jest.Mock).mockResolvedValue({
    client_secret: "ek_mock", call_id: "call-1", model: "mock", expires_at: 123,
  });
  globalThis.fetch = jest.fn(async () => ({ ok: true, text: async () => "v=0\nm=audio" })) as unknown as typeof fetch;
});

afterEach(() => {
  jest.clearAllTimers();
  jest.useRealTimers();
  globalThis.fetch = originalFetch;
});

describe("barge-in (echo cancellation on)", () => {
  it("interrupts the reply when the user talks over it, then starts a fresh one", async () => {
    const { emit, events, types, sent } = await replying("phone");
    emit({ type: "response.output_audio_transcript.delta", response_id: "a1", delta: "Half a sen" });
    emit({ type: "input_audio_buffer.speech_started", item_id: "u2" });
    expect(types().slice(-2)).toEqual(["response_interrupted", "speech_started"]);
    expect(events.at(-1)).toEqual({ type: "speech_started", turnId: "u2" });
    emit({ type: "input_audio_buffer.speech_stopped", item_id: "u2" });
    expect(sent().at(-1)).toEqual({ type: "response.create" });
    emit({ type: "response.created", response: { id: "a2" } });
    emit({ type: "response.output_audio_transcript.delta", response_id: "a2", delta: "New" });
    expect(events.at(-1)).toEqual({ type: "assistant_transcript", text: "New", final: false });
  });

  it("drops the interrupted reply's playback fallback", async () => {
    const { emit, types } = await replying("phone");
    emit({ type: "response.done", response: { id: "a1", status: "completed", output: [] } });
    emit({ type: "input_audio_buffer.speech_started", item_id: "u2" });
    jest.advanceTimersByTime(12_000);
    expect(types()).not.toContain("response_done");
  });

  it("finishes the reply after 12 s when playback never reports stopping", async () => {
    const { emit, types } = await replying("phone");
    emit({ type: "response.done", response: { id: "a1", status: "completed", output: [] } });
    jest.advanceTimersByTime(11_999);
    expect(types()).not.toContain("response_done");
    jest.advanceTimersByTime(1);
    expect(types().filter((type) => type === "response_done")).toHaveLength(1);
  });

  it("keeps the mic open while the assistant speaks, and mute still closes it", async () => {
    const { session, mic, emit } = await replying("phone");
    emit({ type: "response.output_audio_transcript.delta", response_id: "a1", delta: "Hello" });
    expect(mic.enabled).toBe(true);
    session.setMuted(true);
    expect(mic.enabled).toBe(false);
    session.setMuted(false);
    expect(mic.enabled).toBe(true);
  });

  it("stop cancels the reply and the buffered audio, once", async () => {
    const { session, sent, types, emit } = await replying("phone");
    session.cancelResponse();
    expect(sent().slice(-2)).toEqual([{ type: "response.cancel" }, { type: "output_audio_buffer.clear" }]);
    expect(types().at(-1)).toBe("response_interrupted");
    session.cancelResponse();
    expect(types().filter((type) => type === "response_interrupted")).toHaveLength(1);
    emit({ type: "response.output_audio_transcript.delta", response_id: "a1", delta: "late" });
    expect(types()).not.toContain("assistant_transcript");
  });
});

describe("echo drop (half duplex)", () => {
  it("closes the mic while the assistant speaks and reopens it 500 ms after playback", async () => {
    const { mic, emit, sent } = await replying("simulator");
    expect(mic.enabled).toBe(false);
    expect(sent().at(-1)).toEqual({ type: "input_audio_buffer.clear" });
    emit({ type: "response.done", response: { id: "a1", status: "completed", output: [] } });
    emit({ type: "output_audio_buffer.stopped", response_id: "a1" });
    jest.advanceTimersByTime(499);
    expect(mic.enabled).toBe(false);
    jest.advanceTimersByTime(1);
    expect(mic.enabled).toBe(true);
  });

  it("reopens the mic 12 s after response.done when playback never reports stopping", async () => {
    const { mic, emit, types } = await replying("simulator");
    emit({ type: "response.done", response: { id: "a1", status: "completed", output: [] } });
    expect(types().at(-1)).toBe("response_done");
    jest.advanceTimersByTime(11_999);
    expect(mic.enabled).toBe(false);
    jest.advanceTimersByTime(1);
    expect(mic.enabled).toBe(true);
  });

  it("treats speech during the reply as echo: clears it and starts no turn", async () => {
    const { emit, sent, types } = await replying("simulator");
    const before = types().length;
    emit({ type: "input_audio_buffer.speech_started", item_id: "echo" });
    expect(sent().at(-1)).toEqual({ type: "input_audio_buffer.clear" });
    emit({ type: "input_audio_buffer.speech_stopped", item_id: "echo" });
    emit({ type: "conversation.item.input_audio_transcription.completed", item_id: "echo", transcript: "anything" });
    expect(types().slice(before)).toEqual([]);
    expect(sent().filter((payload) => payload.type === "response.create")).toHaveLength(1);
  });

  it("cancels a reply the server starts for an echo turn", async () => {
    const { emit, sent, types } = await replying("simulator");
    emit({ type: "input_audio_buffer.speech_started", item_id: "echo" });
    emit({ type: "response.created", response: { id: "a-echo" } });
    expect(sent().slice(-2)).toEqual([{ type: "input_audio_buffer.clear" }, { type: "response.cancel" }]);
    expect(types().filter((type) => type === "response_started")).toHaveLength(1);
  });

  it("drops a transcript that repeats the last assistant line", async () => {
    const call = await replying("simulator");
    call.emit({ type: "response.output_audio_transcript.done", response_id: "a1", transcript: "The capital of France is Paris." });
    call.emit({ type: "response.done", response: { id: "a1", status: "completed", output: [] } });
    call.emit({ type: "output_audio_buffer.stopped", response_id: "a1" });
    jest.advanceTimersByTime(500);
    call.userTurn("u2");
    call.emit({ type: "conversation.item.input_audio_transcription.completed", item_id: "u2", transcript: "France is Paris" });
    expect(call.types()).not.toContain("user_transcript");
    expect(call.sent().at(-1)).toEqual({ type: "input_audio_buffer.clear" });
    call.emit({ type: "response.created", response: { id: "a2" } });
    call.emit({ type: "response.done", response: { id: "a2", status: "completed", output: [] } });
    call.emit({ type: "output_audio_buffer.stopped", response_id: "a2" });
    jest.advanceTimersByTime(500);
    call.userTurn("u3");
    call.emit({ type: "conversation.item.input_audio_transcription.completed", item_id: "u3", transcript: "And Spain?" });
    expect(call.events.at(-1)).toEqual({ type: "user_transcript", text: "And Spain?" });
  });

  it("keeps a transcript that repeats the assistant when echo cancellation is on", async () => {
    const call = await replying("phone");
    call.emit({ type: "response.output_audio_transcript.done", response_id: "a1", transcript: "Paris." });
    call.emit({ type: "response.done", response: { id: "a1", status: "completed", output: [] } });
    call.emit({ type: "output_audio_buffer.stopped", response_id: "a1" });
    call.userTurn("u2");
    call.emit({ type: "conversation.item.input_audio_transcription.completed", item_id: "u2", transcript: "Paris" });
    expect(call.events.at(-1)).toEqual({ type: "user_transcript", text: "Paris" });
  });
});

describe("turn rules", () => {
  it("ignores speech until 1.5 s after session.created", async () => {
    const { userTurn, sent, types } = await start("phone");
    jest.advanceTimersByTime(1_499);
    userTurn("early");
    expect(types()).toEqual(["connected"]);
    expect(sent()).toEqual([{ type: "input_audio_buffer.clear" }]);
    jest.advanceTimersByTime(1);
    userTurn("u1");
    expect(types()).toEqual(["connected", "speech_started", "speech_stopped"]);
    expect(sent().at(-1)).toEqual({ type: "response.create" });
  });

  it("accepts speech 2.5 s after the channel opens when session.created never arrives", async () => {
    const { userTurn, types } = await start("phone", { sessionCreated: false });
    jest.advanceTimersByTime(2_499);
    userTurn("early");
    expect(types()).toEqual(["connected"]);
    jest.advanceTimersByTime(1);
    userTurn("u1");
    expect(types()).toEqual(["connected", "speech_started", "speech_stopped"]);
  });

  it("drops muted speech and asks for no reply", async () => {
    const { session, userTurn, sent, types, mic } = await start("phone");
    jest.advanceTimersByTime(1_500);
    session.setMuted(true);
    expect(mic.enabled).toBe(false);
    userTurn("u1");
    expect(types()).toEqual(["connected"]);
    expect(sent()).toEqual([{ type: "input_audio_buffer.clear" }]);
  });

  it("asks for one reply per accepted utterance", async () => {
    const { emit, userTurn, sent } = await start("phone");
    jest.advanceTimersByTime(1_500);
    userTurn("u1");
    emit({ type: "input_audio_buffer.speech_stopped", item_id: "u1" });
    expect(sent().filter((payload) => payload.type === "response.create")).toHaveLength(1);
  });

  it("ignores silence hallucinations and transcripts of another utterance", async () => {
    const { emit, userTurn, types } = await start("phone");
    jest.advanceTimersByTime(1_500);
    userTurn("u1");
    emit({ type: "conversation.item.input_audio_transcription.completed", item_id: "u1", transcript: "Thanks for watching!" });
    emit({ type: "conversation.item.input_audio_transcription.completed", item_id: "u0", transcript: "Old words" });
    expect(types()).not.toContain("user_transcript");
  });

  it("builds the reply text from deltas, then the final transcript", async () => {
    const { emit, events } = await replying("phone");
    emit({ type: "response.output_audio_transcript.delta", response_id: "a1", delta: " Hel" });
    emit({ type: "response.audio_transcript.delta", response_id: "a1", delta: "lo" });
    emit({ type: "response.output_audio_transcript.done", response_id: "a1" });
    expect(events.slice(-3)).toEqual([
      { type: "assistant_transcript", text: "Hel", final: false },
      { type: "assistant_transcript", text: "Hello", final: false },
      { type: "assistant_transcript", text: "Hello", final: true },
    ]);
  });

  it("runs two lookups a turn, answers the rest with the limit, and skips repeated calls", async () => {
    (speechApi.realtimeTool as jest.Mock).mockResolvedValue({ content: "Found", sources: [{ title: "S", url: "https://s" }] });
    const { emit, sent, events } = await replying("phone");
    const call = (id: string) => ({ type: "function_call", name: "web_search", call_id: id, arguments: '{"query":"q"}' });
    emit({ type: "response.done", response: { id: "a1", output: [call("t1"), call("t2"), call("t3")] } });
    emit({ type: "response.done", response: { id: "a1", output: [call("t1")] } });
    for (let tick = 0; tick < 6; tick += 1) await Promise.resolve();
    expect(speechApi.realtimeTool).toHaveBeenCalledTimes(2);
    const outputs = sent().filter((payload) => payload.type === "conversation.item.create");
    expect(outputs.map((payload) => (payload.item as { call_id: string }).call_id)).toEqual(["t3", "t1", "t2"]);
    expect(JSON.stringify(outputs[0])).toContain("Voice lookup limit reached");
    expect(sent().at(-1)).toEqual({ type: "response.create" });
    expect(events.filter((event) => event.type === "search_sources")).toHaveLength(2);
  });

  it("turns a server error into an error event and reopens the half-duplex mic", async () => {
    const { emit, events, mic } = await replying("simulator");
    expect(mic.enabled).toBe(false);
    emit({ type: "error", error: { message: "Rate limited" } });
    expect(events.at(-1)).toEqual({ type: "error", message: "Rate limited" });
    expect(mic.enabled).toBe(true);
    expect(jest.getTimerCount()).toBe(0);
  });

  it("reports a failed connection", async () => {
    const { pc, events } = await start("phone");
    pc.connectionState = "failed";
    pc.onconnectionstatechange?.();
    // Fatal: the session closes, so the mic stops recording into a dead peer.
    expect(events.at(-1)).toEqual({ type: "error", message: "Realtime voice connection failed", fatal: true });
  });

  it("stops everything on close and ignores what arrives after", async () => {
    const { session, emit, types, channel, pc, mic } = await replying("simulator");
    session.close();
    expect(channel.close).toHaveBeenCalledTimes(1);
    expect(pc.close).toHaveBeenCalledTimes(1);
    expect(mic.stop).toHaveBeenCalledTimes(1);
    const before = types().length;
    emit({ type: "response.done", response: { id: "a1", output: [] } });
    pc.connectionState = "failed";
    pc.onconnectionstatechange?.();
    session.close();
    expect(types()).toHaveLength(before);
    expect(channel.close).toHaveBeenCalledTimes(1);
    expect(jest.getTimerCount()).toBe(0);
  });

  it("gives the reserved minutes back when the call never connects", async () => {
    (speechApi.endRealtimeSession as jest.Mock).mockResolvedValue({});
    const { pending, channel, pc, mic } = dial("phone", { open: false });
    const failed = expect(pending).rejects.toThrow("Realtime voice connection timed out");
    for (let tick = 0; tick < 20; tick += 1) await Promise.resolve();
    jest.advanceTimersByTime(10_000);
    await failed;
    expect(speechApi.endRealtimeSession).toHaveBeenCalledWith("tok", "call-1");
    expect([channel.close, pc.close, mic.stop].map((fn) => fn.mock.calls.length)).toEqual([1, 1, 1]);
    expect(jest.getTimerCount()).toBe(0);
  });
});
