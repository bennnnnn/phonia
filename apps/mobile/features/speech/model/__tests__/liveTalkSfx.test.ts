const mockPlay = jest.fn();
const mockRemove = jest.fn();
const mockCreateAudioPlayer = jest.fn(() => ({
  play: mockPlay,
  remove: mockRemove,
}));
const mockNotifySuccess = jest.fn();
const mockTap = jest.fn();

jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "/tmp/",
  writeAsStringAsync: jest.fn(async () => undefined),
  EncodingType: { Base64: "base64" },
}));

jest.mock("@/lib/haptics", () => ({
  notifySuccess: () => mockNotifySuccess(),
  tap: () => mockTap(),
}));

jest.mock("@/lib/speech/voiceAudio", () => ({
  loadExpoAudio: () => ({ createAudioPlayer: mockCreateAudioPlayer }),
}));

import {
  LIVE_TALK_CUE_TONES,
  buildLiveTalkCueWavBase64,
  playLiveTalkCue,
} from "@/features/speech/model/liveTalkSfx";

describe("liveTalkSfx", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("encodes distinct rising start and falling end chimes as WAV", () => {
    const start = buildLiveTalkCueWavBase64("start");
    const end = buildLiveTalkCueWavBase64("end");
    expect(start.startsWith("UklGR")).toBe(true);
    expect(start).not.toEqual(end);
    expect(LIVE_TALK_CUE_TONES.start[0]?.hz).toBeLessThan(LIVE_TALK_CUE_TONES.start[1]?.hz ?? 0);
    expect(LIVE_TALK_CUE_TONES.end[0]?.hz).toBeGreaterThan(LIVE_TALK_CUE_TONES.end[1]?.hz ?? 0);
  });

  it("plays start with a success haptic, then releases the player before returning", async () => {
    await playLiveTalkCue("start");
    expect(mockNotifySuccess).toHaveBeenCalledTimes(1);
    expect(mockCreateAudioPlayer).toHaveBeenCalled();
    expect(mockPlay).toHaveBeenCalled();
    expect(mockRemove).toHaveBeenCalled();
  });

  it("plays end with a tap haptic and releases that player too", async () => {
    await playLiveTalkCue("end");
    expect(mockTap).toHaveBeenCalledTimes(1);
    expect(mockCreateAudioPlayer).toHaveBeenCalled();
    expect(mockPlay).toHaveBeenCalled();
    expect(mockRemove).toHaveBeenCalled();
  });
});
