const platform = { OS: "ios" };

jest.mock("react-native", () => ({
  Platform: platform,
  Share: {
    share: jest.fn(),
    sharedAction: "sharedAction",
    dismissedAction: "dismissedAction",
  },
}));

jest.mock("expo-print", () => ({
  printToFileAsync: jest.fn(),
}));

import { Platform, Share } from "react-native";

import { presentShareSheet } from "@/lib/share";

describe("share sheet", () => {
  beforeEach(() => {
    platform.OS = "ios";
    jest.mocked(Share.share).mockReset();
    jest.mocked(Share.share).mockResolvedValue({ action: Share.sharedAction });
  });

  it("opens the native share sheet with message and iOS subject", async () => {
    await presentShareSheet({ message: "Hello thread", title: "My chat" });
    expect(Share.share).toHaveBeenCalledWith(
      { message: "Hello thread", title: "My chat" },
      { subject: "My chat" },
    );
  });

  it("uses dialogTitle on Android", async () => {
    Platform.OS = "android";
    await presentShareSheet({ message: "Hello thread", title: "My chat" });
    expect(Share.share).toHaveBeenCalledWith(
      { message: "Hello thread", title: "My chat" },
      { dialogTitle: "My chat" },
    );
  });

  it("does not throw when the user dismisses the sheet", async () => {
    jest.mocked(Share.share).mockRejectedValueOnce(new Error("User did not share"));
    await expect(
      presentShareSheet({ message: "Hello thread", title: "My chat" }),
    ).resolves.toBeUndefined();
  });

  it("rejects an empty payload instead of opening a blank sheet", async () => {
    await expect(presentShareSheet({ message: "   " })).rejects.toThrow("share_empty");
    expect(Share.share).not.toHaveBeenCalled();
  });
});
