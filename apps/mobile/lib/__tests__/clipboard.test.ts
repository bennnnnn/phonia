import * as Clipboard from "expo-clipboard";

import { clipboardIsImageOnly } from "@/lib/clipboard";

jest.mock("expo-clipboard", () => ({
  getStringAsync: jest.fn(),
  hasImageAsync: jest.fn(),
}));

describe("clipboardIsImageOnly", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("checks hasImageAsync before reading text", async () => {
    (Clipboard.hasImageAsync as jest.Mock).mockResolvedValue(false);
    await expect(clipboardIsImageOnly()).resolves.toBe(false);
    expect(Clipboard.hasImageAsync).toHaveBeenCalled();
    expect(Clipboard.getStringAsync).not.toHaveBeenCalled();
  });

  it("reads text only when an image is present", async () => {
    (Clipboard.hasImageAsync as jest.Mock).mockResolvedValue(true);
    (Clipboard.getStringAsync as jest.Mock).mockResolvedValue("");
    await expect(clipboardIsImageOnly()).resolves.toBe(true);
    expect(Clipboard.getStringAsync).toHaveBeenCalled();
  });

  it("is false when the pasteboard has both image and text", async () => {
    (Clipboard.hasImageAsync as jest.Mock).mockResolvedValue(true);
    (Clipboard.getStringAsync as jest.Mock).mockResolvedValue("notes");
    await expect(clipboardIsImageOnly()).resolves.toBe(false);
  });
});
