import { Share } from "react-native";

import {
  deleteAsync,
  EncodingType,
  writeAsStringAsync,
} from "expo-file-system/legacy";

import { SharingUnavailableError } from "@/lib/shareUnavailable";

jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "/cache/",
  deleteAsync: jest.fn(async () => undefined),
  EncodingType: { UTF8: "utf8" },
  writeAsStringAsync: jest.fn(),
}));

jest.mock("react-native", () => ({
  Share: { share: jest.fn() },
}));

jest.mock("@/lib/shareFile", () => ({ shareLocalFile: jest.fn() }));

import { formatExportJsonForShare, shareAccountExport } from "@/lib/exportData";

const { shareLocalFile } = jest.requireMock<typeof import("@/lib/shareFile")>("@/lib/shareFile");

describe("formatExportJsonForShare", () => {
  it("pretty-prints small valid JSON", () => {
    const raw = '{"user":{"email":"a@b.com"},"chats":[],"memories":[]}';
    expect(formatExportJsonForShare(raw)).toBe(
      JSON.stringify(JSON.parse(raw), null, 2),
    );
  });

  it("returns large payloads unchanged", () => {
    const raw = `{"data":"${"x".repeat(600_000)}"}`;
    expect(formatExportJsonForShare(raw)).toBe(raw);
  });

  it("returns invalid JSON unchanged", () => {
    const raw = "{not json";
    expect(formatExportJsonForShare(raw)).toBe(raw);
  });
});

describe("shareAccountExport", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("writes to cache and hands the file to the share sheet on every platform", async () => {
    await shareAccountExport('{"ok":true}');

    expect(writeAsStringAsync).toHaveBeenCalledWith(
      expect.stringMatching(/^\/cache\/recall-export-\d+\.json$/),
      '{"ok":true}',
      { encoding: EncodingType.UTF8 },
    );
    // React Native's Share ignores `url` on Android: the file must go through shareLocalFile.
    expect(shareLocalFile).toHaveBeenCalledWith(
      expect.stringMatching(/^\/cache\/recall-export-\d+\.json$/),
      { title: "recall-export.json", mimeType: "application/json" },
    );
    expect(Share.share).not.toHaveBeenCalled();
  });

  it("deletes the file once the share sheet closes", async () => {
    await shareAccountExport('{"ok":true}');
    const written = jest.mocked(writeAsStringAsync).mock.calls[0]![0];
    expect(deleteAsync).toHaveBeenCalledWith(written, { idempotent: true });
    expect(jest.mocked(deleteAsync).mock.invocationCallOrder[0]).toBeGreaterThan(
      (shareLocalFile as jest.Mock).mock.invocationCallOrder[0]!,
    );
  });

  it("lets a build that cannot share files fail, so the screen can say so", async () => {
    const unavailable = new SharingUnavailableError();
    (shareLocalFile as jest.Mock).mockRejectedValueOnce(unavailable);
    await expect(shareAccountExport("{}")).rejects.toBe(unavailable);
    expect(deleteAsync).toHaveBeenCalledWith(expect.stringMatching(/recall-export-/), { idempotent: true });
  });
});
