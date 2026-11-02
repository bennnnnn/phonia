import * as FileSystem from "expo-file-system/legacy";

import {
  getTtsModel,
  normalizeTtsModel,
  resetTtsModelCache,
  setTtsModel,
  TTS_DEVICE_MODEL,
  TTS_FAST_MODEL,
  TTS_QUALITY_MODEL,
} from "@/features/speech/model/ttsPreference";

jest.mock("expo-secure-store", () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

jest.mock("expo-file-system/legacy", () => ({
  documentDirectory: "file:///docs/",
  getInfoAsync: jest.fn(),
  readAsStringAsync: jest.fn(),
  writeAsStringAsync: jest.fn(),
  deleteAsync: jest.fn(),
}));

const getInfoAsync = FileSystem.getInfoAsync as jest.Mock;
const readAsStringAsync = FileSystem.readAsStringAsync as jest.Mock;
const writeAsStringAsync = FileSystem.writeAsStringAsync as jest.Mock;

describe("ttsPreference", () => {
  beforeEach(() => {
    resetTtsModelCache();
    getInfoAsync.mockReset();
    readAsStringAsync.mockReset();
    writeAsStringAsync.mockReset();
  });

  it("defaults to OpenAI and preserves an explicit on-device choice", () => {
    expect(normalizeTtsModel(null)).toBe(TTS_QUALITY_MODEL);
    expect(normalizeTtsModel("nope")).toBe(TTS_QUALITY_MODEL);
    expect(normalizeTtsModel(TTS_DEVICE_MODEL)).toBe(TTS_DEVICE_MODEL);
    expect(normalizeTtsModel(TTS_FAST_MODEL)).toBe(TTS_QUALITY_MODEL);
    expect(normalizeTtsModel(TTS_QUALITY_MODEL)).toBe(TTS_QUALITY_MODEL);
  });

  it("migrates the legacy Kokoro alias to OpenAI", async () => {
    getInfoAsync.mockResolvedValue({ exists: true });
    readAsStringAsync.mockResolvedValue(TTS_FAST_MODEL);
    await expect(getTtsModel()).resolves.toBe(TTS_QUALITY_MODEL);
  });

  it("writes the selected alias", async () => {
    await setTtsModel(TTS_FAST_MODEL);
    expect(writeAsStringAsync).toHaveBeenCalledWith(
      "file:///docs/recall.tts-model.txt",
      TTS_FAST_MODEL,
    );
  });
});
