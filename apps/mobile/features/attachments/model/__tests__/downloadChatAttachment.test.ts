import { getInfoAsync, readDirectoryAsync, deleteAsync, moveAsync } from "expo-file-system/legacy";
import * as MediaLibrary from "expo-media-library";
import { shareAsync } from "expo-sharing";
import { Platform, Share } from "react-native";

import { downloadAttachmentFile } from "@/features/attachments/model/fetchAttachmentBytes";
import {
  ensureLocalAttachmentFile,
  getCachedAttachmentFile,
  resetLocalAttachmentFileCache,
  clearLocalAttachmentFileCache,
  invalidateCachedAttachmentFile,
  removeCachedAttachmentFiles,
  saveChatAttachmentToLibrary,
  shareChatAttachment,
} from "@/features/attachments/model/downloadChatAttachment";

/** A fake cache directory: path → size and modification time (seconds). */
const mockDisk = new Map<string, { size: number; mtime: number; dir?: boolean }>();

jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/",
  getInfoAsync: jest.fn(),
  readDirectoryAsync: jest.fn(),
  deleteAsync: jest.fn(),
  moveAsync: jest.fn(),
}));

jest.mock("expo-media-library", () => ({
  requestPermissionsAsync: jest.fn(async () => ({ granted: true })),
  saveToLibraryAsync: jest.fn(async () => undefined),
}));

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

jest.mock("@/features/attachments/model/fetchAttachmentBytes", () => ({
  downloadAttachmentFile: jest.fn(),
}));

let mockGeneration = 0;
let mockUuid = 0;
jest.mock("@/lib/config", () => ({ getApiUrl: () => "https://api.test" }));
jest.mock("expo-crypto", () => ({
  randomUUID: () => `unique-${++mockUuid}`,
  CryptoDigestAlgorithm: { SHA256: "SHA-256" },
  // FNV-1a, repeated with different seeds: deterministic hex, distinct per input.
  digestStringAsync: async (_algorithm: string, value: string) =>
    [0x811c9dc5, 0x01000193, 0x2545f491, 0x9e3779b9].map((seed) => {
      let hash = seed;
      for (let i = 0; i < value.length; i++) hash = Math.imul(hash ^ value.charCodeAt(i), 16777619) >>> 0;
      return hash.toString(16).padStart(8, "0");
    }).join("").repeat(2),
}));
jest.mock("@/lib/auth", () => ({
  getSessionGeneration: () => mockGeneration,
  requireTokenSession: jest.fn(),
  SessionChangedError: class extends Error { constructor() { super("Session changed"); } },
}));

const nowSeconds = () => Math.floor(Date.now() / 1000);

function downloadWrites(path: string): void {
  mockDisk.set(path, { size: 4, mtime: nowSeconds() });
}

beforeEach(() => {
  jest.clearAllMocks();
  mockDisk.clear();
  resetLocalAttachmentFileCache();
  mockGeneration = 0;
  mockHasSharing = true;
  (Platform as { OS: string }).OS = "ios";
  jest.mocked(getInfoAsync).mockReset().mockImplementation(async (path: string) => {
    const file = mockDisk.get(path);
    return file
      ? { exists: true, isDirectory: Boolean(file.dir), uri: path, size: file.size, modificationTime: file.mtime }
      : { exists: false, isDirectory: false, uri: path };
  });
  jest.mocked(readDirectoryAsync).mockReset().mockImplementation(async () =>
    [...mockDisk.keys()].map((path) => path.slice("file:///cache/".length)));
  jest.mocked(deleteAsync).mockReset().mockImplementation(async (path: string) => { mockDisk.delete(path); });
  jest.mocked(moveAsync).mockReset().mockImplementation(async ({ from, to }) => {
    const file = mockDisk.get(from);
    if (!file) throw new Error("missing");
    mockDisk.delete(from);
    mockDisk.set(to, file);
  });
  jest.mocked(downloadAttachmentFile).mockReset().mockImplementation(async (_uri, dest) => downloadWrites(dest));
});

describe("ensureLocalAttachmentFile", () => {
  it("downloads natively once, then reuses the copy", async () => {
    const uri = "https://api.test/attachments/abc/file";
    const local = await ensureLocalAttachmentFile({ uri, token: "tok", fileName: "cat.jpg" });

    expect(downloadAttachmentFile).toHaveBeenCalledWith(uri, expect.stringMatching(/\.part$/), "tok", expect.any(AbortSignal));
    expect(local).toMatch(/^file:\/\/\/cache\/att-[0-9a-f]{16}-[0-9a-f]{8}-cat\.jpg$/);
    expect(mockDisk.has(local)).toBe(true);
    expect(getCachedAttachmentFile(uri)).toBe(local);

    await ensureLocalAttachmentFile({ uri, token: "tok", fileName: "cat.jpg" });
    expect(downloadAttachmentFile).toHaveBeenCalledTimes(1);
  });

  it("finds the copy an earlier app run wrote under the same name", async () => {
    const uri = "https://api.test/attachments/abc/file";
    const first = await ensureLocalAttachmentFile({ uri, token: "tok", fileName: "cat.jpg" });
    resetLocalAttachmentFileCache(); // A cold restart loses all in-memory ownership.
    const second = await ensureLocalAttachmentFile({ uri, token: "tok", fileName: "cat.jpg" });
    expect(second).toBe(first);
    expect(downloadAttachmentFile).toHaveBeenCalledTimes(1);
  });

  it("names a file by its URL without credentials, and keeps thumbnails apart", async () => {
    const original = await ensureLocalAttachmentFile({ uri: "https://api.test/attachments/abc/file", token: "tok" });
    const thumb = await ensureLocalAttachmentFile({ uri: "https://api.test/attachments/abc/file?w=296", token: "tok" });
    expect(thumb).not.toBe(original);
    // Same attachment, same prefix: a delete finds both after a restart.
    expect(thumb.split("-")[1]).toBe(original.split("-")[1]);
    expect(original).not.toContain("tok");
  });

  it("rejects, and leaves no partial file, when the download fails", async () => {
    jest.mocked(downloadAttachmentFile).mockImplementationOnce(async (_uri, dest) => {
      downloadWrites(dest);
      throw new Error("Could not load attachment.");
    });
    await expect(ensureLocalAttachmentFile({ uri: "https://api.test/attachments/missing/file", token: "tok" }))
      .rejects.toThrow("Could not load attachment.");
    expect(mockDisk.size).toBe(0);
  });

  it("keeps different remote files separate even when their URL suffixes match", async () => {
    const suffix = "x".repeat(100);
    const first = await ensureLocalAttachmentFile({ uri: `https://files.test/one?token=${suffix}`, token: "tok", fileName: "image.jpg" });
    const second = await ensureLocalAttachmentFile({ uri: `https://files.test/two?token=${suffix}`, token: "tok", fileName: "image.jpg" });
    expect(first).not.toBe(second);
  });

  it("redownloads a file that the operating system evicted from cache", async () => {
    const uri = "https://files.test/image.jpg";
    const local = await ensureLocalAttachmentFile({ uri, token: "tok" });
    mockDisk.delete(local);
    await ensureLocalAttachmentFile({ uri, token: "tok" });
    expect(downloadAttachmentFile).toHaveBeenCalledTimes(2);
  });

  it("never returns another account's cached local file from memory", async () => {
    const uri = "https://api.test/attachments/abc/file";
    await ensureLocalAttachmentFile({ uri, token: "tok" });
    mockGeneration++;
    expect(getCachedAttachmentFile(uri)).toBeNull();
  });

  it("shares concurrent downloads of the same attachment", async () => {
    const options = { uri: "https://files.test/image.jpg", token: "tok" };
    const [first, second] = await Promise.all([ensureLocalAttachmentFile(options), ensureLocalAttachmentFile(options)]);
    expect(first).toBe(second);
    expect(downloadAttachmentFile).toHaveBeenCalledTimes(1);
  });

  it("cancels the transfer only when every viewer waiting on it has closed", async () => {
    let transferSignal!: AbortSignal;
    jest.mocked(downloadAttachmentFile).mockImplementationOnce((_uri, _dest, _token, signal) => {
      transferSignal = signal!;
      return new Promise((_resolve, reject) => signal!.addEventListener("abort", () => reject(new Error("aborted"))));
    });
    const uri = "https://api.test/attachments/big/file";
    const card = new AbortController();
    const viewer = new AbortController();
    const fromCard = ensureLocalAttachmentFile({ uri, token: "tok", signal: card.signal });
    const fromViewer = ensureLocalAttachmentFile({ uri, token: "tok", signal: viewer.signal });
    await new Promise((resolve) => setTimeout(resolve, 0));

    card.abort();
    await expect(fromCard).rejects.toMatchObject({ name: "AbortError" });
    expect(transferSignal.aborted).toBe(false);

    viewer.abort();
    await expect(fromViewer).rejects.toMatchObject({ name: "AbortError" });
    expect(transferSignal.aborted).toBe(true);

    // The next viewer starts a fresh transfer instead of joining the canceled one.
    await expect(ensureLocalAttachmentFile({ uri, token: "tok" })).resolves.toContain("att-");
    expect(downloadAttachmentFile).toHaveBeenCalledTimes(2);
  });

  it("never cancels a share that is waiting on the same download", async () => {
    let finish!: () => void;
    let transferSignal!: AbortSignal;
    jest.mocked(downloadAttachmentFile).mockImplementationOnce((_uri, dest, _token, signal) => {
      transferSignal = signal!;
      return new Promise<void>((resolve) => { finish = () => { downloadWrites(dest); resolve(); }; });
    });
    const uri = "https://api.test/attachments/shared/file";
    const viewer = new AbortController();
    const fromViewer = ensureLocalAttachmentFile({ uri, token: "tok", signal: viewer.signal });
    const forShare = ensureLocalAttachmentFile({ uri, token: "tok" });
    viewer.abort();
    await expect(fromViewer).rejects.toMatchObject({ name: "AbortError" });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(transferSignal.aborted).toBe(false);
    finish();
    await expect(forShare).resolves.toContain("att-");
  });

  it("keeps long filenames within native limits while preserving their extension", async () => {
    const result = await ensureLocalAttachmentFile({ uri: "https://files.test/long-name", token: "tok", fileName: `${"a".repeat(250)}.pdf` });
    expect(result.split("/").pop()!.length).toBeLessThan(256);
    expect(result.endsWith(".pdf")).toBe(true);
  });

  it("removes a file when logout happens during the download", async () => {
    jest.mocked(downloadAttachmentFile).mockImplementationOnce(async (_uri, dest) => {
      downloadWrites(dest);
      mockGeneration++;
    });
    await expect(ensureLocalAttachmentFile({ uri: "https://files.test/late.jpg", token: "tok" }))
      .rejects.toThrow("Session changed");
    expect(mockDisk.size).toBe(0);
    expect(getCachedAttachmentFile("https://files.test/late.jpg")).toBeNull();
  });

  it("starts a fresh retry instead of reusing the copy on disk", async () => {
    const uri = "https://api.test/attachments/retry/file";
    const first = await ensureLocalAttachmentFile({ uri, token: "tok" });
    invalidateCachedAttachmentFile(uri);
    const retry = await ensureLocalAttachmentFile({ uri, token: "tok" });
    expect(retry).toBe(first);
    expect(downloadAttachmentFile).toHaveBeenCalledTimes(2);
    expect(getCachedAttachmentFile(uri)).toBe(retry);
  });

  it("ignores the invalidated in-flight download", async () => {
    const uri = "https://api.test/attachments/retry/file";
    let finishOld!: () => void;
    jest.mocked(downloadAttachmentFile).mockImplementationOnce((_uri, dest) =>
      new Promise<void>((resolve) => { finishOld = () => { downloadWrites(dest); resolve(); }; }));
    const first = ensureLocalAttachmentFile({ uri, token: "tok" });
    const rejected = expect(first).rejects.toThrow("Attachment changed");
    await new Promise((resolve) => setTimeout(resolve, 0));
    invalidateCachedAttachmentFile(uri);
    const retry = await ensureLocalAttachmentFile({ uri, token: "tok" });
    finishOld();
    await rejected;
    expect(getCachedAttachmentFile(uri)).toBe(retry);
    expect(mockDisk.has(retry)).toBe(true);
  });
});

describe("cache cleanup", () => {
  it("removes tracked cache files during sign-out cleanup", async () => {
    const uri = "https://files.test/logout.jpg";
    const dest = await ensureLocalAttachmentFile({ uri, token: "tok" });
    await clearLocalAttachmentFileCache();
    expect(mockDisk.has(dest)).toBe(false);
    expect(getCachedAttachmentFile(uri)).toBeNull();
  });

  it("removes prior-run attachment files without deleting unrelated files or directories", async () => {
    const oldFile = await ensureLocalAttachmentFile({ uri: "https://files.test/prior-run.pdf", token: "tok" });
    resetLocalAttachmentFileCache();
    const legacy = "file:///cache/att-https___files.test_legacy.pdf-legacy.pdf";
    mockDisk.set(legacy, { size: 1, mtime: nowSeconds() });
    mockDisk.set("file:///cache/cached-user.json", { size: 1, mtime: nowSeconds() });
    mockDisk.set("file:///cache/att-folder", { size: 0, mtime: nowSeconds(), dir: true });

    await clearLocalAttachmentFileCache();

    expect([...mockDisk.keys()].sort()).toEqual(["file:///cache/att-folder", "file:///cache/cached-user.json"]);
    expect(deleteAsync).toHaveBeenCalledWith(oldFile, { idempotent: true });
  });

  it("keeps a new session's files when its download completes during logout enumeration", async () => {
    mockDisk.set("file:///cache/att-prior-run.jpg", { size: 1, mtime: nowSeconds() });
    let finishListing!: (names: string[]) => void;
    jest.mocked(readDirectoryAsync).mockImplementationOnce(() => new Promise((resolve) => { finishListing = resolve; }));
    const cleanup = clearLocalAttachmentFileCache();
    mockGeneration++;
    const uri = "https://files.test/new-session.jpg";
    const freshFile = await ensureLocalAttachmentFile({ uri, token: "new-token" });
    finishListing(["att-prior-run.jpg", freshFile.split("/").pop()!]);

    await cleanup;

    expect(mockDisk.has("file:///cache/att-prior-run.jpg")).toBe(false);
    expect(mockDisk.has(freshFile)).toBe(true);
    expect(getCachedAttachmentFile(uri)).toBe(freshFile);
  });

  it("still removes remembered files when directory enumeration is unavailable", async () => {
    const file = await ensureLocalAttachmentFile({ uri: "https://files.test/remembered.jpg", token: "tok" });
    jest.mocked(readDirectoryAsync).mockRejectedValueOnce(new Error("Directory unavailable"));
    await clearLocalAttachmentFileCache();
    expect(deleteAsync).toHaveBeenCalledWith(file, { idempotent: true });
  });

  it("removes all cached variants when an attachment is deleted, even after a restart", async () => {
    const uri = "https://api.test/attachments/deleted/file";
    const original = await ensureLocalAttachmentFile({ uri, token: "tok" });
    const thumbnail = await ensureLocalAttachmentFile({ uri: `${uri}?w=300`, token: "tok" });
    resetLocalAttachmentFileCache();
    const unrelated = await ensureLocalAttachmentFile({ uri: "https://api.test/attachments/kept/file", token: "tok" });
    await removeCachedAttachmentFiles("deleted");
    expect(mockDisk.has(original)).toBe(false);
    expect(mockDisk.has(thumbnail)).toBe(false);
    expect(mockDisk.has(unrelated)).toBe(true);
    expect(getCachedAttachmentFile("https://api.test/attachments/kept/file")).toBe(unrelated);
  });

  it("does not restore a deleted attachment when its earlier download completes", async () => {
    const uri = "https://api.test/attachments/deleted/file";
    let finish!: () => void;
    jest.mocked(downloadAttachmentFile).mockImplementationOnce((_uri, dest) =>
      new Promise<void>((resolve) => { finish = () => { downloadWrites(dest); resolve(); }; }));
    const download = ensureLocalAttachmentFile({ uri, token: "tok" });
    const rejected = expect(download).rejects.toThrow("Attachment changed");
    await new Promise((resolve) => setTimeout(resolve, 0));
    await removeCachedAttachmentFiles("deleted");
    finish();
    await rejected;
    expect(getCachedAttachmentFile(uri)).toBeNull();
    expect(mockDisk.size).toBe(0);
  });
});

describe("share and save", () => {
  it("saves to the photo library when permission is granted", async () => {
    const result = await saveChatAttachmentToLibrary({
      uri: "http://127.0.0.1:8000/attachments/abc/file",
      token: "tok",
      fileName: "cat.jpg",
    });
    expect(result).toBe("saved");
    expect(MediaLibrary.saveToLibraryAsync).toHaveBeenCalled();
  });

  it("hands the file itself to the share sheet, with its type for Android", async () => {
    (Platform as { OS: string }).OS = "android";
    await shareChatAttachment({ uri: "http://127.0.0.1:8000/attachments/abc/file", token: "tok", fileName: "cat.png" });
    expect(shareAsync).toHaveBeenCalledWith(expect.stringMatching(/^file:\/\/.*cat\.png$/), expect.objectContaining({ mimeType: "image/png" }));
    // Android's RN Share would send the cache path as text.
    expect(Share.share).not.toHaveBeenCalled();
  });

  it("prefers the item's own content type over the file name's", async () => {
    await shareChatAttachment({
      uri: "http://127.0.0.1:8000/attachments/abc/file",
      token: "tok",
      fileName: "notes",
      contentType: "text/markdown; charset=utf-8",
    });
    expect(shareAsync).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ mimeType: "text/markdown" }));
  });

  it("falls back to a file url on iOS builds without expo-sharing", async () => {
    mockHasSharing = false;
    await shareChatAttachment({ uri: "http://127.0.0.1:8000/attachments/abc/file", token: "tok", fileName: "cat.jpg" });
    expect(Share.share).toHaveBeenCalledWith(expect.objectContaining({ url: expect.stringContaining("file://") }));
    expect(shareAsync).not.toHaveBeenCalled();
  });

  it("refuses to share a path as text on Android builds without expo-sharing", async () => {
    mockHasSharing = false;
    (Platform as { OS: string }).OS = "android";
    await expect(shareChatAttachment({ uri: "http://127.0.0.1:8000/attachments/abc/file", token: "tok" }))
      .rejects.toThrow("Sharing files needs an app update.");
    expect(Share.share).not.toHaveBeenCalled();
  });

  it("does not throw when the user dismisses the share sheet", async () => {
    jest.mocked(shareAsync).mockRejectedValueOnce(new Error("User did not share"));
    await expect(shareChatAttachment({ uri: "http://127.0.0.1:8000/attachments/abc/file", token: "tok", fileName: "cat.jpg" }))
      .resolves.toBeUndefined();
  });

  it("does not open a share sheet if the account changed while downloading", async () => {
    jest.mocked(downloadAttachmentFile).mockImplementationOnce(async (_uri, dest) => {
      downloadWrites(dest);
      mockGeneration++;
    });
    await expect(shareChatAttachment({ uri: "https://api.test/attachments/abc/file", token: "tok" }))
      .rejects.toThrow("Session changed");
    expect(shareAsync).not.toHaveBeenCalled();
    expect(Share.share).not.toHaveBeenCalled();
  });

  it("does not save to Photos after switching accounts during the permission prompt", async () => {
    jest.mocked(MediaLibrary.requestPermissionsAsync).mockImplementationOnce(async () => {
      mockGeneration++;
      return { granted: true } as MediaLibrary.PermissionResponse;
    });
    await expect(saveChatAttachmentToLibrary({ uri: "https://files.test/permission.jpg", token: "tok" }))
      .rejects.toThrow("Session changed");
    expect(MediaLibrary.saveToLibraryAsync).not.toHaveBeenCalled();
  });

  it("does not reopen a failed share sheet when Photos permission is denied", async () => {
    jest.mocked(MediaLibrary.requestPermissionsAsync).mockResolvedValueOnce({ granted: false } as MediaLibrary.PermissionResponse);
    jest.mocked(shareAsync).mockRejectedValueOnce(new Error("Share unavailable"));
    await expect(saveChatAttachmentToLibrary({ uri: "https://files.test/share-failure", token: "tok" }))
      .rejects.toThrow("Share unavailable");
    expect(shareAsync).toHaveBeenCalledTimes(1);
  });
});
