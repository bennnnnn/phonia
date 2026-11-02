import * as FileSystem from "expo-file-system/legacy";
import * as SecureStore from "expo-secure-store";

import {
  clearSeenReminderIds,
  loadSeenReminderIds,
  saveSeenReminderIds,
} from "@/features/todos/model/reminderSeen";

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
const deleteAsync = FileSystem.deleteAsync as jest.Mock;

describe("reminderSeen", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    getInfoAsync.mockResolvedValue({ exists: false });
    (SecureStore.getItemAsync as jest.Mock).mockResolvedValue(null);
  });

  it("reads seen ids from the filesystem when present", async () => {
    getInfoAsync.mockResolvedValue({ exists: true });
    readAsStringAsync.mockResolvedValue(JSON.stringify(["a", "b"]));
    await expect(loadSeenReminderIds("user-1")).resolves.toEqual(new Set(["a", "b"]));
    expect(SecureStore.getItemAsync).not.toHaveBeenCalled();
  });

  it("reads nothing from the Keychain when no file exists (DEAD-07)", async () => {
    await expect(loadSeenReminderIds("user-1")).resolves.toEqual(new Set());
    expect(SecureStore.getItemAsync).not.toHaveBeenCalled();
  });

  it("saveSeenReminderIds writes the filesystem, not Keychain", async () => {
    await saveSeenReminderIds("user-1", new Set(["x"]));
    expect(writeAsStringAsync).toHaveBeenCalledWith(
      "file:///docs/recall.reminder-seen.user-1.json",
      JSON.stringify(["x"]),
    );
    expect(SecureStore.setItemAsync).not.toHaveBeenCalled();
  });

  it("clearSeenReminderIds deletes the file", async () => {
    await clearSeenReminderIds("user-1");
    expect(deleteAsync).toHaveBeenCalledWith("file:///docs/recall.reminder-seen.user-1.json", {
      idempotent: true,
    });
  });
});
