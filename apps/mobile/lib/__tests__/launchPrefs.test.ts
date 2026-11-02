import * as SecureStore from "expo-secure-store";

import { resetAccentPreferenceCache } from "@/lib/accentPrefs";
import * as accentRuntime from "@/lib/accentRuntime";
import { resetAppearancePreferenceCache } from "@/lib/appearancePrefs";
import { getAppearancePreferenceSnapshot, resetAppearanceRuntime } from "@/lib/appearanceRuntime";
import i18n from "@/lib/i18n";
import { restoreLaunchPrefs } from "@/lib/launchPrefs";

/** The synchronous file system the first frame reads (`lib/syncFileRead.ts`). */
const mockSyncFiles = new Map<string, string>();
jest.mock("expo-file-system", () => ({
  Paths: { document: "file:///docs/", cache: "file:///cache/" },
  File: class {
    private readonly path: string;
    constructor(directory: string, name: string) {
      this.path = `${directory}${name}`;
    }
    get exists() {
      return mockSyncFiles.has(this.path);
    }
    textSync() {
      return mockSyncFiles.get(this.path) ?? "";
    }
  },
}));
jest.mock("expo-file-system/legacy", () => ({
  documentDirectory: "file:///docs/",
  cacheDirectory: "file:///cache/",
  getInfoAsync: jest.fn(async () => ({ exists: false })),
  readAsStringAsync: jest.fn(),
  writeAsStringAsync: jest.fn(),
  deleteAsync: jest.fn(),
}));
jest.mock("expo-secure-store", () => ({
  getItemAsync: jest.fn(async () => null),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

beforeEach(async () => {
  mockSyncFiles.clear();
  jest.clearAllMocks();
  resetAppearanceRuntime();
  resetAppearancePreferenceCache();
  resetAccentPreferenceCache();
  await i18n.changeLanguage("en");
});

describe("restoreLaunchPrefs", () => {
  it("applies the appearance, accent and the last account's language before anything renders", async () => {
    mockSyncFiles.set("file:///docs/recall.appearance-preference.txt", "dark");
    mockSyncFiles.set("file:///docs/recall.accent-preference.txt", "ocean");
    mockSyncFiles.set("file:///cache/cached-user.json", JSON.stringify({ id: "u1", plan: "free", locale: "de" }));
    const setAccent = jest.spyOn(accentRuntime, "setAccentSnapshot");

    const ready = restoreLaunchPrefs();

    // All in place synchronously: the first frame is drawn in them.
    expect(getAppearancePreferenceSnapshot()).toBe("dark");
    expect(setAccent).toHaveBeenCalledWith("ocean");
    expect(i18n.language).toBe("de");
    await expect(ready).resolves.toBeUndefined();
    expect(SecureStore.getItemAsync).not.toHaveBeenCalled();
  });

  it("keeps the defaults for a first launch", async () => {
    const setAccent = jest.spyOn(accentRuntime, "setAccentSnapshot");
    await restoreLaunchPrefs();
    expect(getAppearancePreferenceSnapshot()).toBe("system");
    expect(setAccent).toHaveBeenCalledWith("indigo");
    expect(i18n.language).toBe("en");
    // The appearance lives in its file only; the Keychain is never read (DEAD-07).
    expect(SecureStore.getItemAsync).not.toHaveBeenCalled();
  });
});
