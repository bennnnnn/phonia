import { speechApi } from "@/features/speech/api";
import { createRealtimeVoiceSession, webRtcMicConstraints, type RealtimeVoiceEvent } from "@/features/speech/model/realtimeVoice";
import * as webrtc from "react-native-webrtc";

jest.mock("react-native", () => ({
  Platform: { OS: "ios" },
  NativeModules: { WebRTCModule: {} },
  TurboModuleRegistry: { get: (name: string) => (name === "WebRTCModule" ? {} : null) },
}));
jest.mock("expo-modules-core", () => ({
  requireOptionalNativeModule: () => ({ isDevice: true }),
}));
jest.mock("expo-constants", () => ({}));
jest.mock("@/lib/speech/voiceAudio", () => ({ yieldMicToWebRtc: jest.fn(async () => undefined) }));
jest.mock("@/features/speech/api", () => ({ speechApi: { createRealtimeSession: jest.fn(), realtimeTool: jest.fn() } }));
jest.mock("react-native-webrtc", () => ({
  mediaDevices: { getUserMedia: jest.fn() },
  RTCPeerConnection: jest.fn(), RTCSessionDescription: jest.fn((value) => value),
}));

describe("physical-phone Realtime turns", () => {
  const track = { kind: "audio", enabled: true, stop: jest.fn() };
  let channel: { readyState: string; send: jest.Mock; close: jest.Mock; onopen?: () => void; onmessage?: (data: unknown) => void };
  let events: RealtimeVoiceEvent[];
  const emit = (event: object) => channel.onmessage?.({ data: JSON.stringify(event) });
  const sent = () => channel.send.mock.calls.map(([value]) => JSON.parse(value));
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    (globalThis as unknown as { __DEV__: boolean }).__DEV__ = false;
    track.enabled = true;
    events = [];
    channel = { readyState: "open", send: jest.fn(), close: jest.fn() };
    (webrtc.mediaDevices.getUserMedia as jest.Mock).mockResolvedValue({
      getAudioTracks: () => [track], getTracks: () => [track],
    });
    (webrtc.RTCPeerConnection as unknown as jest.Mock).mockImplementation(() => ({
      addTrack: jest.fn(), createDataChannel: () => channel,
      createOffer: async () => ({ sdp: "v=0\nm=audio" }), setLocalDescription: async () => undefined,
      setRemoteDescription: async () => { channel.onopen?.(); emit({ type: "session.created" }); },
      close: jest.fn(), getReceivers: () => [],
    }));
    (speechApi.createRealtimeSession as jest.Mock).mockResolvedValue({ client_secret: "ek_mock", call_id: "session-mock", model: "mock", expires_at: 123 });
    globalThis.fetch = jest.fn(async () => ({ ok: true, text: async () => "v=0\nm=audio" })) as unknown as typeof fetch;
  });
  afterEach(() => { jest.clearAllTimers(); jest.useRealTimers(); globalThis.fetch = originalFetch; });

  async function connect() {
    const session = await createRealtimeVoiceSession({ token: "tok", chatId: "chat-1", onEvent: (event) => events.push(event) });
    jest.advanceTimersByTime(1600);
    emit({ type: "input_audio_buffer.speech_started", item_id: "u1" });
    emit({ type: "input_audio_buffer.speech_stopped", item_id: "u1" });
    emit({ type: "response.created", response: { id: "a1" } });
    return session;
  }

  it("leaves no timer behind once a connected session closes", async () => {
    const session = await createRealtimeVoiceSession({ token: "tok", chatId: "chat-1", onEvent: () => {} });
    session.close();
    // The connect deadline raced the open data channel and was never
    // cleared, so it outlived every successful connect by ten seconds.
    expect(jest.getTimerCount()).toBe(0);
  });

  it("uses AEC, keeps listening during playback, and ignores the cancelled reply's late events", async () => {
    const session = await connect();
    expect(webRtcMicConstraints().echoCancellation).toBe(true);
    expect(track.enabled).toBe(true);
    emit({ type: "input_audio_buffer.speech_started", item_id: "u2" });
    expect(events).toContainEqual({ type: "response_interrupted" });
    emit({ type: "response.output_audio_transcript.delta", response_id: "a1", delta: "stale" });
    emit({ type: "response.done", response: { id: "a1", status: "cancelled" } });
    expect(events.some((e) => e.type === "assistant_transcript")).toBe(false);
    expect(events.some((e) => e.type === "response_done")).toBe(false);
    session.setMuted(true);
    expect(track.enabled).toBe(false);
    session.close();
  });

  it("waits for playback before finalizing the voice transcript", async () => {
    const session = await connect();
    emit({ type: "response.done", response: { id: "a1", status: "completed", output: [] } });
    expect(events.some((e) => e.type === "response_done")).toBe(false);
    emit({ type: "output_audio_buffer.stopped", response_id: "a1" });
    expect(events.filter((e) => e.type === "response_done")).toHaveLength(1);
    session.close();
  });

  it("rejects a delayed response.created while a new utterance is in progress", async () => {
    const session = await connect();
    emit({ type: "input_audio_buffer.speech_started", item_id: "u2" });
    const count = events.filter((event) => event.type === "response_started").length;
    emit({ type: "response.created", response: { id: "delayed-old" } });
    expect(sent()).toContainEqual({ type: "response.cancel", response_id: "delayed-old" });
    expect(events.filter((event) => event.type === "response_started")).toHaveLength(count);
    emit({ type: "input_audio_buffer.speech_stopped", item_id: "u2" });
    expect(sent().at(-1)).toEqual({ type: "response.create" });
    session.close();
  });

  it("does not start a stale tool answer after the user interrupts", async () => {
    let resolveTool!: (value: { content: string }) => void;
    (speechApi.realtimeTool as jest.Mock).mockImplementation(() => new Promise((resolve) => { resolveTool = resolve; }));
    const session = await connect();
    emit({ type: "response.done", response: { id: "a1", output: [{
      type: "function_call", name: "web_search", call_id: "tool-1", arguments: '{"query":"latest score"}',
    }] } });
    expect(speechApi.realtimeTool).toHaveBeenCalledTimes(1);
    emit({ type: "input_audio_buffer.speech_started", item_id: "u2" });
    const count = sent().filter((p) => p.type === "response.create").length;
    resolveTool({ content: "Old results" });
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
    expect(sent().filter((p) => p.type === "response.create")).toHaveLength(count);
    expect(JSON.stringify(sent())).not.toContain("Old results");
    session.close();
  });
});
