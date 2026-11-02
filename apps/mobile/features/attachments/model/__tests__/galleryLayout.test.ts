import * as FileSystem from "expo-file-system/legacy";

import {
  getGalleryLayout,
  resetGalleryLayoutCache,
  setGalleryLayout,
} from "@/features/attachments/model/galleryLayout";

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

describe("galleryLayout", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    resetGalleryLayoutCache();
    getInfoAsync.mockResolvedValue({ exists: false });
  });

  it("defaults to grid when unset", async () => {
    await expect(getGalleryLayout()).resolves.toBe("grid");
  });

  it("persists column layout to the filesystem", async () => {
    await setGalleryLayout("column");
    expect(writeAsStringAsync).toHaveBeenCalledWith(
      "file:///docs/recall.gallery-layout.txt",
      "column",
    );
  });

  it("reads a stored column preference", async () => {
    getInfoAsync.mockResolvedValue({ exists: true });
    readAsStringAsync.mockResolvedValue("column");
    await expect(getGalleryLayout()).resolves.toBe("column");
  });
});
