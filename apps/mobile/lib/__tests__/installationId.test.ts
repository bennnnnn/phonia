import * as Crypto from "expo-crypto";

import { getInstallationId } from "@/lib/installationId";

jest.mock("expo-crypto", () => ({
  randomUUID: jest.fn(() => "install-uuid-1"),
}));

jest.mock("expo-file-system/legacy", () => ({
  documentDirectory: "file:///docs/",
  getInfoAsync: jest.fn(),
  readAsStringAsync: jest.fn(),
  writeAsStringAsync: jest.fn(),
}));

import {
  documentDirectory,
  getInfoAsync,
  readAsStringAsync,
  writeAsStringAsync,
} from "expo-file-system/legacy";

describe("getInstallationId", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (getInfoAsync as jest.Mock).mockResolvedValue({ exists: false });
    (writeAsStringAsync as jest.Mock).mockResolvedValue(undefined);
  });

  it("returns existing id from disk", async () => {
    (getInfoAsync as jest.Mock).mockResolvedValue({ exists: true });
    (readAsStringAsync as jest.Mock).mockResolvedValue("  existing-id  ");
    await expect(getInstallationId()).resolves.toBe("existing-id");
    expect(Crypto.randomUUID).not.toHaveBeenCalled();
  });

  it("creates and persists a new id when missing", async () => {
    await expect(getInstallationId()).resolves.toBe("install-uuid-1");
    expect(writeAsStringAsync).toHaveBeenCalledWith(
      `${documentDirectory}recall.installation-id.txt`,
      "install-uuid-1",
    );
  });
});
