jest.mock("expo-file-system/legacy", () => ({
  getInfoAsync: jest.fn(async () => ({ exists: true, size: 1200 })),
  readAsStringAsync: jest.fn(async () => "ZmFrZQ=="),
}));

jest.mock("expo-modules-core", () => ({
  requireOptionalNativeModule: jest.fn(() => null),
}));

jest.mock("expo-audio", () => {
  throw new Error("Cannot find native module 'ExpoAudio'");
});

import {
  isVoiceInputAvailable,
  loadExpoAudio,
  meteredRecordingOptions,
  normalizeRecordingUri,
  speechUploadFromUri,
} from "@/lib/speech/voiceAudio";

describe("voiceAudio", () => {
  it("loadExpoAudio returns null when native module is missing", () => {
    expect(loadExpoAudio()).toBeNull();
  });

  it("isVoiceInputAvailable is false when expo-audio fails to load", () => {
    expect(isVoiceInputAvailable()).toBe(false);
  });

  it("normalizes recording uri", () => {
    expect(normalizeRecordingUri("/tmp/speech.m4a")).toBe("file:///tmp/speech.m4a");
    expect(normalizeRecordingUri("file:///tmp/speech.m4a")).toBe("file:///tmp/speech.m4a");
  });

  it("builds upload metadata from uri", () => {
    expect(speechUploadFromUri("file:///cache/recording.m4a")).toEqual({
      uri: "file:///cache/recording.m4a",
      name: "recording.m4a",
      type: "audio/m4a",
    });
    expect(speechUploadFromUri("file:///cache/speech.wav")).toEqual({
      uri: "file:///cache/speech.wav",
      name: "speech.wav",
      type: "audio/wav",
    });
  });

  it("records Expo's high-quality preset with metering on", () => {
    expect(meteredRecordingOptions({ extension: ".m4a", sampleRate: 44100 })).toEqual({
      extension: ".m4a",
      sampleRate: 44100,
      isMeteringEnabled: true,
    });
  });
});
