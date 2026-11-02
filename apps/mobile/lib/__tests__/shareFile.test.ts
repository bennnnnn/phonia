import { shareAsync } from "expo-sharing";
import { Platform, Share } from "react-native";

import { shareLocalFile, shareRoute } from "@/lib/shareFile";
import { shareFailureKey, SharingUnavailableError } from "@/lib/shareUnavailable";

jest.mock("react-native", () => ({
  Platform: { OS: "ios" },
  Share: { share: jest.fn(async () => undefined) },
}));

// expo-sharing is loaded only when its native module is in the build.
let mockHasSharing = true;
jest.mock("expo-modules-core", () => ({
  requireOptionalNativeModule: (name: string) => (name === "ExpoSharing" && mockHasSharing ? {} : null),
}));
jest.mock("expo-sharing", () => ({ shareAsync: jest.fn(async () => undefined) }));

beforeEach(() => {
  jest.clearAllMocks();
  mockHasSharing = true;
  (Platform as { OS: string }).OS = "ios";
});

it.each([
  ["ios", true, "expo-sharing"],
  ["android", true, "expo-sharing"],
  ["ios", false, "rn-share"],
  ["android", false, "unavailable"],
] as const)("on %s with expo-sharing=%s shares through %s", (platform, hasSharing, route) => {
  expect(shareRoute(platform, hasSharing)).toBe(route);
});

it("hands the file, its type and its title to expo-sharing", async () => {
  (Platform as { OS: string }).OS = "android";
  await shareLocalFile("file:///cache/a.pdf", {
    title: "a.pdf",
    mimeType: "application/pdf",
    uti: "com.adobe.pdf",
  });
  expect(shareAsync).toHaveBeenCalledWith("file:///cache/a.pdf", {
    dialogTitle: "a.pdf",
    mimeType: "application/pdf",
    UTI: "com.adobe.pdf",
  });
  expect(Share.share).not.toHaveBeenCalled();
});

it("falls back to a file url on iOS builds without expo-sharing", async () => {
  mockHasSharing = false;
  await shareLocalFile("file:///cache/a.pdf", { title: "a.pdf" });
  expect(Share.share).toHaveBeenCalledWith({ url: "file:///cache/a.pdf", title: "a.pdf" });
});

it("refuses to share a path as text on Android builds without expo-sharing", async () => {
  mockHasSharing = false;
  (Platform as { OS: string }).OS = "android";
  const error = await shareLocalFile("file:///cache/a.pdf", { title: "a.pdf" }).catch((failure: unknown) => failure);
  expect(error).toBeInstanceOf(SharingUnavailableError);
  expect(shareFailureKey(error, "common.share_failed")).toBe("common.share_needs_update");
  expect(Share.share).not.toHaveBeenCalled();
});

it("keeps the caller's line for any other share failure", () => {
  expect(shareFailureKey(new Error("Sharing files needs an app update."), "common.share_failed")).toBe("common.share_failed");
  expect(shareFailureKey(new Error("boom"), null)).toBeNull();
});

it("treats a dismissed sheet as done", async () => {
  jest.mocked(shareAsync).mockRejectedValueOnce(new Error("User did not share"));
  await expect(shareLocalFile("file:///cache/a.pdf", { title: "a.pdf" })).resolves.toBeUndefined();
});
