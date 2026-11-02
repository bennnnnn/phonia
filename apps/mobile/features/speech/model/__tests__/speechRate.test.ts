import * as FileSystem from "expo-file-system/legacy";

import {
  currentSpeechRate,
  getSpeechRate,
  normalizeSpeechRate,
  resetSpeechRateCache,
  setSpeechRate,
} from "@/features/speech/model/speechRate";

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

describe("speechRate", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    resetSpeechRateCache();
  });

  it.each([
    ["1.25", 1.25],
    ["0.75", 0.75],
    ["3", 1],
    ["fast", 1],
    [null, 1],
  ])("normalizes %p to %p", (raw, expected) => {
    expect(normalizeSpeechRate(raw)).toBe(expected);
  });

  it("is normal speed until the saved one is read", async () => {
    getInfoAsync.mockResolvedValue({ exists: true });
    readAsStringAsync.mockResolvedValue("1.5");
    expect(currentSpeechRate()).toBe(1);
    await expect(getSpeechRate()).resolves.toBe(1.5);
    expect(currentSpeechRate()).toBe(1.5);
  });

  it("saves a new speed and uses it at once", async () => {
    await setSpeechRate(0.75);
    expect(currentSpeechRate()).toBe(0.75);
    expect(writeAsStringAsync).toHaveBeenCalledWith("file:///docs/recall.speech-rate.txt", "0.75");
  });
});
