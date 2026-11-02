import { speechApi } from "@/features/speech/api";
import { createRealtimeVoiceSession } from "@/features/speech/model/realtimeVoice";
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
jest.mock("@/features/speech/api", () => ({
  speechApi: {
    createRealtimeSession: jest.fn(),
    endRealtimeSession: jest.fn(async () => ({})),
    realtimeTool: jest.fn(),
  },
}));
jest.mock("react-native-webrtc", () => ({
  mediaDevices: { getUserMedia: jest.fn() },
  RTCPeerConnection: jest.fn(),
  RTCSessionDescription: jest.fn((value) => value),
}));

type Deferred<T> = { promise: Promise<T>; resolve: (value: T) => void; reject: (error: unknown) => void };
function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}

const flush = () => new Promise<void>((done) => setImmediate(() => done()));

describe("a Live Talk call that never connects gives its minutes back", () => {
  const track = { kind: "audio", enabled: true, stop: jest.fn() };
  const createSession = speechApi.createRealtimeSession as jest.Mock;
  const endSession = speechApi.endRealtimeSession as jest.Mock;
  let createOffer: jest.Mock;

  beforeEach(() => {
    jest.clearAllMocks();
    (globalThis as unknown as { __DEV__: boolean }).__DEV__ = false;
    (webrtc.mediaDevices.getUserMedia as jest.Mock).mockResolvedValue({
      getAudioTracks: () => [track],
      getTracks: () => [track],
    });
    createOffer = jest.fn(async () => ({ sdp: "v=0\nm=audio" }));
    (webrtc.RTCPeerConnection as unknown as jest.Mock).mockImplementation(() => ({
      addTrack: jest.fn(),
      createDataChannel: () => ({ readyState: "connecting", send: jest.fn(), close: jest.fn() }),
      createOffer,
      setLocalDescription: async () => undefined,
      setRemoteDescription: async () => undefined,
      close: jest.fn(),
      getReceivers: () => [],
    }));
  });

  it("ends the call when the offer fails before the mint has answered", async () => {
    const mint = deferred<{ client_secret: string; call_id: string }>();
    createSession.mockReturnValueOnce(mint.promise);
    createOffer.mockRejectedValueOnce(new Error("offer failed"));

    await expect(
      createRealtimeVoiceSession({ token: "tok", chatId: "chat-1", onEvent: () => {} }),
    ).rejects.toThrow("offer failed");
    // The call id was still unknown when the offer threw: nothing to end yet.
    expect(endSession).not.toHaveBeenCalled();

    mint.resolve({ client_secret: "ek_late", call_id: "call-late" });
    await flush();
    expect(endSession).toHaveBeenCalledWith("tok", "call-late");
  });

  it("ends the call when connecting fails after the mint", async () => {
    createSession.mockResolvedValueOnce({ client_secret: "ek_mock", call_id: "call-1" });
    const originalFetch = globalThis.fetch;
    globalThis.fetch = jest.fn(async () => {
      throw new Error("network down");
    }) as unknown as typeof fetch;
    try {
      await expect(
        createRealtimeVoiceSession({ token: "tok", chatId: "chat-1", onEvent: () => {} }),
      ).rejects.toThrow();
    } finally {
      globalThis.fetch = originalFetch;
    }
    await flush();
    expect(endSession).toHaveBeenCalledWith("tok", "call-1");
  });

  it("ends nothing when the mint itself failed", async () => {
    const mint = deferred<{ client_secret: string; call_id: string }>();
    createSession.mockReturnValueOnce(mint.promise);
    createOffer.mockRejectedValueOnce(new Error("offer failed"));

    await expect(
      createRealtimeVoiceSession({ token: "tok", chatId: "chat-1", onEvent: () => {} }),
    ).rejects.toThrow("offer failed");
    mint.reject(Object.assign(new Error("limit"), { status: 429 }));
    await flush();
    expect(endSession).not.toHaveBeenCalled();
  });
});

describe("a Live Talk call releases its native media stream (LEAK-06)", () => {
  const track = { kind: "audio", enabled: true, stop: jest.fn() };
  const createSession = speechApi.createRealtimeSession as jest.Mock;

  function microphone(tracks: unknown[]) {
    const release = jest.fn();
    (webrtc.mediaDevices.getUserMedia as jest.Mock).mockResolvedValue({
      getAudioTracks: () => tracks,
      getTracks: () => tracks,
      release,
    });
    return release;
  }

  beforeEach(() => {
    jest.clearAllMocks();
    (globalThis as unknown as { __DEV__: boolean }).__DEV__ = false;
    (webrtc.RTCPeerConnection as unknown as jest.Mock).mockImplementation(() => ({
      addTrack: jest.fn(),
      createDataChannel: () => ({ readyState: "connecting", send: jest.fn(), close: jest.fn() }),
      createOffer: jest.fn(async () => { throw new Error("offer failed"); }),
      setLocalDescription: async () => undefined,
      setRemoteDescription: async () => undefined,
      close: jest.fn(),
      getReceivers: () => [],
    }));
    createSession.mockResolvedValue({ client_secret: "ek_1", call_id: "call-1" });
  });

  it("on a connect that fails", async () => {
    const release = microphone([track]);
    await expect(
      createRealtimeVoiceSession({ token: "tok", chatId: "chat-1", onEvent: () => {} }),
    ).rejects.toThrow("offer failed");
    expect(track.stop).toHaveBeenCalled();
    expect(release).toHaveBeenCalledTimes(1);
  });

  // It threw webrtc_unavailable: "update the app", for a microphone that gave no audio.
  it("on a microphone with no audio track", async () => {
    const release = microphone([]);
    await expect(
      createRealtimeVoiceSession({ token: "tok", chatId: "chat-1", onEvent: () => {} }),
    ).rejects.toThrow("microphone_unavailable");
    expect(release).toHaveBeenCalledTimes(1);
  });
});
