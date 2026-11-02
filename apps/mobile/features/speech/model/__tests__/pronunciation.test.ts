import { deleteAsync, writeAsStringAsync } from "expo-file-system/legacy";

import { speakPlainText, stopSpeaking } from "@/features/speech/model/pronunciation";

type StatusListener = (status: { didJustFinish?: boolean; playing?: boolean }) => void;
type FakePlayer = {
  play: jest.Mock;
  pause: jest.Mock;
  remove: jest.Mock;
  addListener: jest.Mock;
  playing: boolean;
  currentTime: number;
  duration: number;
  emit: StatusListener;
};

const mockPlayers: FakePlayer[] = [];
let mockTtsModel = "speech-tts-model";
const mockAppStateHandlers = new Set<(state: string) => void>();

jest.mock("react-native", () => ({
  AppState: {
    addEventListener: (_event: string, handler: (state: string) => void) => {
      mockAppStateHandlers.add(handler);
      return { remove: () => mockAppStateHandlers.delete(handler) };
    },
  },
}));
jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/",
  EncodingType: { Base64: "base64" },
  writeAsStringAsync: jest.fn(async () => undefined),
  deleteAsync: jest.fn(async () => undefined),
}));
jest.mock("expo-speech", () => ({ speak: jest.fn(), stop: jest.fn() }));
jest.mock("@/lib/api/client", () => ({
  requestRaw: jest.fn(async () => ({
    ok: true,
    json: async () => ({ audio_base64: "QUJD", content_type: "audio/mpeg" }),
  })),
}));
jest.mock("@/lib/speech/voiceAudio", () => ({
  preparePlaybackAudioMode: jest.fn(async () => undefined),
  loadExpoAudio: () => ({
    createAudioPlayer: () => {
      let listener: StatusListener = () => {};
      const player: FakePlayer = {
        play: jest.fn(),
        pause: jest.fn(),
        remove: jest.fn(),
        addListener: jest.fn((_event: string, next: StatusListener) => {
          listener = next;
          return { remove: jest.fn() };
        }),
        playing: false,
        currentTime: 0,
        duration: 0,
        emit: (status) => listener(status),
      };
      mockPlayers.push(player);
      return player;
    },
  }),
}));
jest.mock("@/lib/markdown/plain", () => ({ markdownToSpeechText: (text: string) => text }));
jest.mock("@/features/speech/model/ttsLead", () => ({
  splitTtsChunks: (text: string) => text.split("|"),
}));
jest.mock("@/features/speech/model/ttsPreference", () => ({
  TTS_DEVICE_MODEL: "device",
  TTS_QUALITY_MODEL: "speech-tts-model",
  TTS_FAST_MODEL: "speech-tts-fast-model",
  getTtsModel: async () => mockTtsModel,
}));
jest.mock("@/features/speech/model/speechRate", () => ({
  getSpeechRate: async () => 1,
  currentSpeechRate: () => 1,
}));

async function flush(): Promise<void> {
  for (let i = 0; i < 30; i += 1) await Promise.resolve();
}

describe("cloud read-aloud lifetime", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    mockPlayers.length = 0;
    mockTtsModel = "speech-tts-model";
  });
  afterEach(() => {
    stopSpeaking();
    jest.clearAllTimers();
    jest.useRealTimers();
  });

  it("releases each clip's player and cache file when the clip ends", async () => {
    const speaking = speakPlainText("hello", "en-US", { token: "tok", preferCloud: true });
    await flush();
    expect(mockPlayers).toHaveLength(1);
    const [player] = mockPlayers;
    player.emit({ playing: true });
    player.emit({ didJustFinish: true });
    await expect(speaking).resolves.toEqual({ ok: true });
    // A finished player kept the audio session in playback until the next
    // tap, and every clip left a recall-tts-*.mp3 behind in the cache.
    expect(player.remove).toHaveBeenCalledTimes(1);
    const path = jest.mocked(writeAsStringAsync).mock.calls[0]?.[0];
    expect(path).toMatch(/^file:\/\/\/cache\/recall-tts-\d+\.mp3$/);
    expect(deleteAsync).toHaveBeenCalledWith(path, { idempotent: true });
  });

  it("stops reading, instead of starting the next clip, when the app goes to the background", async () => {
    const speaking = speakPlainText("first|second", "en-US", { token: "tok", preferCloud: true });
    await flush();
    expect(mockPlayers).toHaveLength(1);
    const [first] = mockPlayers;
    first.emit({ playing: true });

    for (const handler of [...mockAppStateHandlers]) handler("background");
    // expo-audio pauses players natively in the background. The queue read
    // that pause as the end of the clip and played the next one.
    first.playing = false;
    first.emit({ playing: false });
    await flush();
    jest.advanceTimersByTime(1_000);
    await flush();

    expect(mockPlayers).toHaveLength(1);
    expect(first.remove).toHaveBeenCalled();
    await expect(speaking).resolves.toEqual({ ok: true });
  });

  it("keeps reading across an inactive blip", async () => {
    const speaking = speakPlainText("first|second", "en-US", { token: "tok", preferCloud: true });
    await flush();
    const [first] = mockPlayers;
    first.emit({ playing: true });
    for (const handler of [...mockAppStateHandlers]) handler("inactive");
    expect(first.remove).not.toHaveBeenCalled();
    first.emit({ didJustFinish: true });
    await flush();
    expect(mockPlayers).toHaveLength(2);
    mockPlayers[1].emit({ didJustFinish: true });
    await expect(speaking).resolves.toEqual({ ok: true });
  });
});

describe("the on-device voice switch", () => {
  const { requestRaw } = jest.requireMock<{ requestRaw: jest.Mock }>("@/lib/api/client");
  const { speak } = jest.requireMock<{ speak: jest.Mock }>("expo-speech");

  beforeEach(() => {
    jest.clearAllMocks();
    mockPlayers.length = 0;
  });
  afterEach(() => {
    stopSpeaking();
    mockTtsModel = "speech-tts-model";
  });

  it("reads with the phone's voice for a paid user who switched it on", async () => {
    mockTtsModel = "device";
    void speakPlainText("hello", "en-US", { token: "tok", preferCloud: true });
    await flush();
    expect(requestRaw).not.toHaveBeenCalled();
    expect(speak).toHaveBeenCalledWith("hello", expect.anything());
  });

  it("uses the cloud voice for a paid user who left it off", async () => {
    void speakPlainText("hello", "en-US", { token: "tok", preferCloud: true });
    await flush();
    expect(requestRaw).toHaveBeenCalled();
    expect(speak).not.toHaveBeenCalled();
  });
});
