const mockSetAudioModeAsync = jest.fn(async (_mode: unknown) => undefined);
const mockRelease = jest.fn();
const mockPrepare = jest.fn(async (_preset: unknown) => undefined);
const mockRecord = jest.fn();

jest.mock("expo-file-system/legacy", () => ({
  deleteAsync: jest.fn(async () => undefined),
  getInfoAsync: jest.fn(async () => ({ exists: true, size: 1200 })),
  readAsStringAsync: jest.fn(async () => "ZmFrZQ=="),
}));

jest.mock("expo-modules-core", () => ({
  requireOptionalNativeModule: jest.fn(() => ({})),
}));

jest.mock("expo-audio", () => ({
  setAudioModeAsync: (mode: unknown) => mockSetAudioModeAsync(mode),
  RecordingPresets: { HIGH_QUALITY: { extension: ".m4a" } },
  AudioModule: {
    AudioRecorder: class {
      isRecording = false;
      prepareToRecordAsync = (preset: unknown) => mockPrepare(preset);
      record = () => mockRecord();
      release = () => mockRelease();
    },
  },
}));

import { startVoiceRecording } from "@/lib/speech/voiceAudio";

describe("startVoiceRecording when the mic cannot start", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it.each([
    ["prepare throws", () => mockPrepare.mockRejectedValueOnce(new Error("mic busy"))],
    [
      "record throws",
      () =>
        mockRecord.mockImplementationOnce(() => {
          throw new Error("mic busy");
        }),
    ],
  ])("releases the recorder and restores playback mode when %s", async (_name, arrange) => {
    arrange();

    await expect(startVoiceRecording()).rejects.toThrow("mic busy");

    expect(mockRelease).toHaveBeenCalledTimes(1);
    expect(mockSetAudioModeAsync).toHaveBeenLastCalledWith({
      allowsRecording: false,
      playsInSilentMode: true,
    });
  });

  it("keeps the recorder when recording starts", async () => {
    const recorder = await startVoiceRecording();

    expect(recorder).not.toBeNull();
    expect(mockRelease).not.toHaveBeenCalled();
    expect(mockSetAudioModeAsync).toHaveBeenLastCalledWith({
      allowsRecording: true,
      playsInSilentMode: true,
    });
  });
});
