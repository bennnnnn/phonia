import {
  containsText,
  GEOTAGGED_JPEG,
  gifBytes,
  gifParts,
  GPS_XMP,
  jpegHasGps,
} from "@/features/attachments/model/__tests__/fixtures/photoBytes";
// lib/ tests run under ts-jest/node — react-native is ESM and cannot load
// as CJS.
jest.mock("react-native", () => ({
  Linking: { openSettings: jest.fn() },
}));

import { File } from "expo-file-system";
import { api } from "@/lib/api";
import { pendingFromLibraryItem } from "@/features/attachments/model/pendingFromLibraryItem";
import { ApiRequestError, requestRaw } from "@/lib/api/client";
import { Linking } from "react-native";
import {
  discardDraftAttachment,
  pickDocument,
  pickFromCamera,
  pickFromPhotoLibrary,
  pickImageDocument,
  uploadChatAttachment,
  NativePickerBusyError,
} from "@/features/attachments/model/attachments";
import { IMAGE_JPEG_QUALITY, MAX_ATTACHMENT_BYTES } from "@/features/attachments/model/attachmentLimits";
import { discardLocalCopy } from "@/features/attachments/model/localAttachmentFile";
import * as DocumentPicker from "expo-document-picker";
import * as ImagePicker from "expo-image-picker";
import { ImageManipulator } from "expo-image-manipulator";

jest.mock("@/ui/overlay/dialogs", () => ({ confirmDialog: jest.fn(async () => true) }));
const confirmDialog = jest.requireMock<{ confirmDialog: jest.Mock }>("@/ui/overlay/dialogs").confirmDialog;
jest.mock("@/lib/i18n", () => ({ __esModule: true, default: { t: (key: string) => key } }));

const mockRead = jest.fn();
let mockGeneration = 0;
jest.mock("expo-file-system", () => ({ File: jest.fn(), Paths: { cache: { uri: "file:///cache/" } } }));
jest.mock("expo-file-system/legacy", () => ({ getInfoAsync: jest.fn(async () => ({ exists: true, size: 3 })) }));
jest.mock("expo-document-picker", () => ({ getDocumentAsync: jest.fn() }));
jest.mock("expo-image-picker", () => ({
  requestMediaLibraryPermissionsAsync: jest.fn(async () => ({ granted: true, canAskAgain: true })),
  getMediaLibraryPermissionsAsync: jest.fn(async () => ({ granted: true, canAskAgain: true })),
  requestCameraPermissionsAsync: jest.fn(async () => ({ granted: true, canAskAgain: true })),
  launchImageLibraryAsync: jest.fn(),
  launchCameraAsync: jest.fn(),
}));
// Decoded size of the next image the manipulator renders, and every resize asked of it.
let mockDecoded = { width: 100, height: 100 };
const mockResize = jest.fn();
const mockSave = jest.fn();
jest.mock("expo-image-manipulator", () => {
  const image = (width: number, height: number) => ({
    width, height, release: jest.fn(),
    saveAsync: (options: unknown) => mockSave(options, { width, height }),
  });
  const context = (size: { width: number; height: number }) => ({
    release: jest.fn(),
    renderAsync: async () => image(size.width, size.height),
    resize(target: { width?: number; height?: number }) {
      mockResize(target);
      const scale = (target.width ?? 0) / size.width || (target.height ?? 0) / size.height;
      return context({ width: Math.round(size.width * scale), height: Math.round(size.height * scale) });
    },
  });
  return {
    SaveFormat: { JPEG: "jpeg", PNG: "png", WEBP: "webp" },
    ImageManipulator: {
      manipulate: jest.fn((source: string | { width: number; height: number }) =>
        context(typeof source === "string" ? mockDecoded : source)),
    },
  };
});
jest.mock("@/lib/api", () => ({ api: {
  presignAttachment: jest.fn(), confirmAttachment: jest.fn(), cancelAttachment: jest.fn(),
} }));
jest.mock("@/lib/api/client", () => ({
  requestRaw: jest.fn(),
  ApiRequestError: jest.requireActual("@/lib/api/errorBody").ApiRequestError,
}));
jest.mock("@/lib/config", () => ({ getApiUrl: () => "https://api.test" }));
jest.mock("@/lib/auth", () => ({
  getSessionGeneration: () => mockGeneration,
  requireTokenSession: jest.fn(),
  SessionChangedError: class extends Error { constructor() { super("Session changed"); } },
}));
jest.mock("@/features/attachments/model/downloadChatAttachment", () => ({
  ensureLocalAttachmentFile: jest.fn(async () => "file:///cache/library-notes.pdf"),
}));
jest.mock("@/features/attachments/model/galleryListCache", () => ({ invalidateGalleryCache: jest.fn() }));

const mockFetch = jest.fn();
const originalFetch = globalThis.fetch;
const pending = { localUri: "file:///picked.pdf", contentType: "application/pdf", fileName: "picked.pdf", kind: "file" as const };
const MiB = 1024 * 1024;
// Byte size per file (3 bytes unless set), bytes per file, and the files deleted.
let mockSizes: Record<string, number> = {};
let mockBytes: Record<string, Uint8Array> = {};
const mockDeleted: string[] = [];
beforeEach(() => {
  jest.clearAllMocks();
  mockGeneration = 0;
  mockDecoded = { width: 100, height: 100 };
  mockSizes = {};
  mockBytes = {};
  mockDeleted.length = 0;
  mockSave.mockImplementation(async (options: { format: string }, size: { width: number; height: number }) => ({
    uri: `file:///cache/ImageManipulator/out-${mockSave.mock.calls.length}.${options.format === "jpeg" ? "jpg" : options.format}`,
    ...size,
  }));
  mockFetch.mockReset().mockResolvedValue({ ok: true, arrayBuffer: async () => new Uint8Array([1, 2, 3]).buffer });
  mockRead.mockReset().mockResolvedValue(new Uint8Array([1, 2, 3]).buffer);
  jest.mocked(File).mockImplementation((...uris) => {
    const uri = String(uris[0]);
    return {
      exists: !mockDeleted.includes(uri),
      size: mockSizes[uri] ?? mockBytes[uri]?.length ?? 3,
      arrayBuffer: () => mockRead(uri),
      bytes: async () => mockBytes[uri] ?? new Uint8Array([1, 2, 3]),
      write: (bytes: Uint8Array) => { mockBytes[uri] = bytes; },
      delete: () => { mockDeleted.push(uri); },
    } as unknown as File;
  });
  jest.mocked(api.presignAttachment).mockResolvedValue({ attachment_id: "a1", upload_url: "/ignored", api_upload: true, storage_key: "key", headers: {} });
  jest.mocked(requestRaw).mockResolvedValue({ ok: true } as Response);
  globalThis.fetch = mockFetch as unknown as typeof fetch;
});
afterAll(() => { globalThis.fetch = originalFetch; });

it("reads picked native files with Expo File and uploads API bytes through refresh-aware requestRaw", async () => {
  await expect(uploadChatAttachment("token", pending)).resolves.toBe("a1");
  expect(mockRead).toHaveBeenCalledTimes(1);
  expect(requestRaw).toHaveBeenCalledWith("/attachments/a1/upload", "token", expect.objectContaining({ method: "PUT", body: expect.any(ArrayBuffer) }), true, expect.any(Number));
  expect(mockFetch).not.toHaveBeenCalled();
});

it("never adds Recall authorization to a storage URL sharing only the API host prefix", async () => {
  jest.mocked(api.presignAttachment).mockResolvedValue({ attachment_id: "a1", upload_url: "https://api.test.external.test/upload", api_upload: false, storage_key: "key", headers: {} });
  await uploadChatAttachment("token", pending);
  const remote = mockFetch.mock.calls.find(([url]) => url === "https://api.test.external.test/upload");
  expect(remote?.[1].headers).not.toHaveProperty("Authorization");
  expect(api.confirmAttachment).toHaveBeenCalledWith("token", "a1");
});

it("does not continue an upload after account change during native file reading", async () => {
  mockRead.mockImplementationOnce(async () => { mockGeneration++; return new ArrayBuffer(3); });
  await expect(uploadChatAttachment("token", pending)).rejects.toThrow("Session changed");
  expect(requestRaw).not.toHaveBeenCalled();
  expect(mockFetch).not.toHaveBeenCalled();
});

it("does not upload changed bytes with a stale presigned size", async () => {
  mockRead.mockResolvedValueOnce(new ArrayBuffer(9));
  await expect(uploadChatAttachment("token", pending)).rejects.toMatchObject({ reason: "changed" });
  expect(requestRaw).not.toHaveBeenCalled();
});

it("keeps cleanup best effort when an upload fails", async () => {
  jest.mocked(requestRaw).mockRejectedValueOnce(new Error("Upload offline"));
  jest.mocked(api.cancelAttachment).mockRejectedValueOnce(new Error("Cleanup offline"));
  await expect(uploadChatAttachment("token", pending)).rejects.toThrow("Upload offline");
  expect(api.cancelAttachment).toHaveBeenCalledWith("token", "a1");
});

it("converts a HEIC photo when the picker omits MIME metadata", async () => {
  jest.mocked(ImagePicker.launchImageLibraryAsync).mockResolvedValue({ canceled: false, assets: [{ uri: "file:///photo.HEIC", fileName: "photo.HEIC", width: 10, height: 10 }] });
  await expect(pickFromPhotoLibrary()).resolves.toEqual({
    contentType: "image/jpeg", localUri: "file:///cache/ImageManipulator/out-1.jpg", fileName: "photo.jpg", kind: "image",
  });
  expect(mockSave).toHaveBeenCalledWith({ format: "jpeg", compress: 0.8 }, expect.anything());
  expect(ImagePicker.launchImageLibraryAsync).toHaveBeenCalledWith({
    mediaTypes: ["images"], quality: 0.85, allowsEditing: false,
  });
});

it("uses square editing and preserves source dimensions for profile preparation", async () => {
  jest.mocked(ImagePicker.launchImageLibraryAsync).mockResolvedValue({
    canceled: false,
    assets: [{ uri: "file:///photo.HEIC", fileName: "photo.HEIC", width: 1000, height: 1000 }],
  });
  await expect(pickFromPhotoLibrary({ squareCrop: true })).resolves.toMatchObject({
    localUri: "file:///photo.HEIC",
    contentType: "image/heic",
    kind: "image",
    imageSize: { width: 1000, height: 1000 },
  });
  expect(ImagePicker.launchImageLibraryAsync).toHaveBeenCalledWith({
    mediaTypes: ["images"], quality: 0.85, allowsEditing: true, aspect: [1, 1],
  });
  expect(ImageManipulator.manipulate).not.toHaveBeenCalled();
});

it("opens Photos even when library permission is denied", async () => {
  jest.mocked(ImagePicker.getMediaLibraryPermissionsAsync).mockResolvedValueOnce({
    granted: false,
    canAskAgain: false,
  } as ImagePicker.MediaLibraryPermissionResponse);
  jest.mocked(ImagePicker.launchImageLibraryAsync).mockResolvedValue({ canceled: true, assets: null });
  await expect(pickFromPhotoLibrary()).resolves.toBeNull();
  expect(ImagePicker.getMediaLibraryPermissionsAsync).not.toHaveBeenCalled();
  expect(ImagePicker.launchImageLibraryAsync).toHaveBeenCalled();
  expect(Linking.openSettings).not.toHaveBeenCalled();
});

it("still requires library permission for the square crop editor", async () => {
  jest.mocked(ImagePicker.getMediaLibraryPermissionsAsync).mockResolvedValueOnce({
    granted: false,
    canAskAgain: false,
  } as ImagePicker.MediaLibraryPermissionResponse);
  await expect(pickFromPhotoLibrary({ squareCrop: true })).rejects.toMatchObject({
    name: "PhotoLibraryPermissionError",
    needsSettings: true,
  });
  expect(ImagePicker.launchImageLibraryAsync).not.toHaveBeenCalled();
});

it("opens the camera without a permission round trip when access is already granted", async () => {
  jest.mocked(ImagePicker.launchCameraAsync).mockResolvedValue({ canceled: true, assets: null });
  await expect(pickFromCamera()).resolves.toBeNull();
  expect(ImagePicker.requestCameraPermissionsAsync).not.toHaveBeenCalled();
  expect(ImagePicker.launchCameraAsync).toHaveBeenCalled();
});

it("asks for camera permission only after the system rejects the launch", async () => {
  jest.mocked(ImagePicker.launchCameraAsync)
    .mockRejectedValueOnce(new Error("Missing camera or camera roll permission"))
    .mockResolvedValueOnce({ canceled: true, assets: null });
  jest.mocked(ImagePicker.requestCameraPermissionsAsync).mockResolvedValue({
    granted: true,
    canAskAgain: true,
  } as ImagePicker.CameraPermissionResponse);
  await expect(pickFromCamera()).resolves.toBeNull();
  expect(ImagePicker.requestCameraPermissionsAsync).toHaveBeenCalledTimes(1);
  expect(ImagePicker.launchCameraAsync).toHaveBeenCalledTimes(2);
  expect(Linking.openSettings).not.toHaveBeenCalled();
});

it.each([
  [true, 1],
  [false, 0],
])("asks before opening Settings when camera access cannot be requested again (open=%p)", async (open, opened) => {
  confirmDialog.mockClear().mockResolvedValueOnce(open);
  jest.mocked(Linking.openSettings).mockClear();
  jest.mocked(ImagePicker.launchCameraAsync).mockRejectedValue(
    new Error("Missing camera or camera roll permission"),
  );
  jest.mocked(ImagePicker.requestCameraPermissionsAsync).mockResolvedValue({
    granted: false,
    canAskAgain: false,
  } as ImagePicker.CameraPermissionResponse);
  // The dialog said what is needed; the pick ends quietly instead of a second error.
  await expect(pickFromCamera()).resolves.toBeNull();
  expect(confirmDialog).toHaveBeenCalledWith(
    expect.objectContaining({ title: "chat.camera_permission", confirmLabel: "chat.location_open_settings" }),
  );
  expect(Linking.openSettings).toHaveBeenCalledTimes(opened);
  expect(ImagePicker.launchCameraAsync).toHaveBeenCalledTimes(1);
});

it("throws instead of silently no-oping when a native picker is already open", async () => {
  let release!: (value: ImagePicker.ImagePickerResult) => void;
  jest.mocked(ImagePicker.launchImageLibraryAsync).mockImplementation(
    () =>
      new Promise((resolve) => {
        release = resolve;
      }),
  );
  const first = pickFromPhotoLibrary();
  for (
    let i = 0;
    i < 50 && jest.mocked(ImagePicker.launchImageLibraryAsync).mock.calls.length === 0;
    i += 1
  ) {
    await Promise.resolve();
  }
  await expect(pickFromPhotoLibrary()).rejects.toBeInstanceOf(NativePickerBusyError);
  release({ canceled: true, assets: null });
  await expect(first).resolves.toBeNull();
});

it("refuses an unknown document type when it is picked, not as a JPEG and not at Send", async () => {
  jest.mocked(DocumentPicker.getDocumentAsync).mockResolvedValue({ canceled: false, assets: [{ uri: "file:///cache/DocumentPicker/archive.bin", name: "archive.bin", lastModified: 0 }] });
  await expect(pickDocument()).rejects.toMatchObject({ reason: "unsupported_type" });
  expect(mockDeleted).toEqual(["file:///cache/DocumentPicker/archive.bin"]);
});

it("opens scanner images through Files without requesting photo permission", async () => {
  jest.mocked(DocumentPicker.getDocumentAsync).mockResolvedValue({
    canceled: false,
    assets: [{ uri: "file:///problem.png", name: "problem.png", mimeType: "image/png", lastModified: 0 }],
  });
  await expect(pickImageDocument()).resolves.toMatchObject({
    contentType: "image/png",
    kind: "image",
  });
  expect(DocumentPicker.getDocumentAsync).toHaveBeenCalledWith({
    type: ["image/*"],
    copyToCacheDirectory: true,
    multiple: false,
  });
  expect(ImagePicker.requestMediaLibraryPermissionsAsync).not.toHaveBeenCalled();
});


it("reuploads a restored Library document after its rejected server ID is removed", async () => {
  jest.mocked(File).mockImplementation((...uris) => {
    if (uris[0] !== "file:///cache/library-notes.pdf") throw new Error("Not a local file");
    return { exists: true, size: 3, arrayBuffer: mockRead } as unknown as File;
  });
  const librarySelection = await pendingFromLibraryItem({
    id: "rejected-id", content_type: "application/pdf", original_filename: "notes.pdf", download_url: "/attachments/rejected-id/file",
  }, "token");
  expect(librarySelection.existingAttachmentId).toBe("rejected-id");
  const restoredDraft = { ...librarySelection, existingAttachmentId: undefined };

  await expect(uploadChatAttachment("token", restoredDraft)).resolves.toBe("a1");

  expect(File).toHaveBeenCalledWith("file:///cache/library-notes.pdf");
  expect(api.presignAttachment).toHaveBeenCalledWith("token", {
    content_type: "application/pdf", size_bytes: 3, filename: "notes.pdf",
  });
  expect(requestRaw).toHaveBeenCalledWith("/attachments/a1/upload", "token", expect.objectContaining({ method: "PUT", body: expect.any(ArrayBuffer) }), true, expect.any(Number));
});

describe("every picked photo leaves without its metadata, as something the API takes", () => {
  type Asset = { uri: string; mimeType?: string; width?: number; height?: number; name: string };
  const library = (asset: Asset) => {
    jest.mocked(ImagePicker.launchImageLibraryAsync).mockResolvedValue({
      canceled: false, assets: [{ ...asset, fileName: asset.name, width: asset.width ?? 0, height: asset.height ?? 0 }],
    } as ImagePicker.ImagePickerResult);
    return pickFromPhotoLibrary();
  };
  const camera = (asset: Asset) => {
    jest.mocked(ImagePicker.launchCameraAsync).mockResolvedValue({
      canceled: false, assets: [{ ...asset, fileName: asset.name, width: asset.width ?? 0, height: asset.height ?? 0 }],
    } as ImagePicker.ImagePickerResult);
    return pickFromCamera();
  };
  const files = (asset: Asset) => {
    jest.mocked(DocumentPicker.getDocumentAsync).mockResolvedValue({
      canceled: false, assets: [{ uri: asset.uri, name: asset.name, mimeType: asset.mimeType, lastModified: 0 }],
    });
    return pickDocument();
  };
  const scannerFiles = (asset: Asset) => {
    jest.mocked(DocumentPicker.getDocumentAsync).mockResolvedValue({
      canceled: false, assets: [{ uri: asset.uri, name: asset.name, mimeType: asset.mimeType, lastModified: 0 }],
    });
    return pickImageDocument();
  };
  const cases: {
    name: string;
    via: (asset: Asset) => Promise<unknown>;
    asset: Asset;
    decoded?: { width: number; height: number };
    bytes?: number;
    resize: { width?: number; height?: number } | null;
    /** The format the manipulator writes. */
    saved: "jpeg" | "png" | "webp";
    contentType: string;
    extension: string;
  }[] = [
    { name: "a small library JPEG is written again, not sent with its EXIF", via: library,
      asset: { uri: "file:///cache/ImagePicker/s.jpg", mimeType: "image/jpeg", width: 1200, height: 900, name: "s.jpg" },
      decoded: { width: 1200, height: 900 }, resize: null, saved: "jpeg", contentType: "image/jpeg", extension: "jpg" },
    { name: "a small camera JPEG is written again", via: camera,
      asset: { uri: "file:///cache/ImagePicker/t.jpg", mimeType: "image/jpeg", width: 2048, height: 1536, name: "t.jpg" },
      decoded: { width: 2048, height: 1536 }, resize: null, saved: "jpeg", contentType: "image/jpeg", extension: "jpg" },
    { name: "a small Files JPEG is written again", via: files,
      asset: { uri: "file:///cache/DocumentPicker/u.jpeg", mimeType: "image/jpeg", name: "u.jpeg" },
      decoded: { width: 640, height: 480 }, resize: null, saved: "jpeg", contentType: "image/jpeg", extension: "jpg" },
    { name: "a scanner photo from Files is written again", via: scannerFiles,
      asset: { uri: "file:///cache/DocumentPicker/v.jpg", mimeType: "image/jpeg", name: "v.jpg" },
      decoded: { width: 900, height: 1200 }, resize: null, saved: "jpeg", contentType: "image/jpeg", extension: "jpg" },
    { name: "a full-size camera frame is scaled to 2048 wide", via: camera,
      asset: { uri: "file:///cache/ImagePicker/a.jpg", mimeType: "image/jpeg", width: 4032, height: 3024, name: "a.jpg" },
      decoded: { width: 4032, height: 3024 }, resize: { width: 2048 }, saved: "jpeg", contentType: "image/jpeg", extension: "jpg" },
    { name: "a tall library photo is scaled to 2048 high", via: library,
      asset: { uri: "file:///cache/ImagePicker/b.jpg", mimeType: "image/jpeg", width: 3000, height: 4000, name: "b.jpg" },
      decoded: { width: 3000, height: 4000 }, resize: { height: 2048 }, saved: "jpeg", contentType: "image/jpeg", extension: "jpg" },
    { name: "a small PNG stays a PNG, transparency and all", via: library,
      asset: { uri: "file:///cache/ImagePicker/c.png", mimeType: "image/png", width: 1000, height: 800, name: "c.png" },
      decoded: { width: 1000, height: 800 }, resize: null, saved: "png", contentType: "image/png", extension: "png" },
    { name: "a WEBP stays a WEBP", via: library,
      asset: { uri: "file:///cache/ImagePicker/g.webp", mimeType: "image/webp", width: 2000, height: 1500, name: "g.webp" },
      bytes: 12 * MiB, decoded: { width: 2000, height: 1500 }, resize: null, saved: "webp", contentType: "image/webp", extension: "webp" },
    { name: "a file only named a GIF (Android's picker writes a JPEG) becomes a JPEG", via: library,
      asset: { uri: "file:///cache/ImagePicker/h.gif", mimeType: "image/gif", width: 480, height: 270, name: "h.gif" },
      decoded: { width: 480, height: 270 }, resize: null, saved: "jpeg", contentType: "image/jpeg", extension: "jpg" },
    { name: "a TIFF the API does not take becomes a JPEG", via: files,
      asset: { uri: "file:///cache/DocumentPicker/e.tiff", mimeType: "image/tiff", name: "e.tiff" },
      decoded: { width: 800, height: 600 }, resize: null, saved: "jpeg", contentType: "image/jpeg", extension: "jpg" },
    { name: "a large HEIC from Files is scaled and becomes a JPEG", via: files,
      asset: { uri: "file:///cache/DocumentPicker/f.heic", name: "f.heic" },
      decoded: { width: 4000, height: 3000 }, resize: { width: 2048 }, saved: "jpeg", contentType: "image/jpeg", extension: "jpg" },
  ];

  it.each(cases)("$name", async ({ via, asset, decoded, bytes, resize, saved, contentType, extension }) => {
    if (decoded) mockDecoded = decoded;
    if (bytes) mockSizes[asset.uri] = bytes;
    const picked = await via(asset) as { localUri: string; contentType: string; fileName: string };
    expect(ImageManipulator.manipulate).toHaveBeenCalledWith(asset.uri);
    expect(mockSave).toHaveBeenCalledTimes(1);
    expect(mockSave).toHaveBeenCalledWith({ format: saved, compress: IMAGE_JPEG_QUALITY }, expect.anything());
    expect(picked.contentType).toBe(contentType);
    if (resize) expect(mockResize).toHaveBeenCalledWith(resize);
    else expect(mockResize).not.toHaveBeenCalled();
    expect(picked.localUri).toMatch(/^file:\/\/\/cache\/ImageManipulator\//);
    expect(picked.fileName).toBe(`${asset.name.replace(/\.[^.]+$/, "")}.${extension}`);
    // The picker's copy is the intermediate: it goes once the re-encode replaces it.
    expect(mockDeleted).toEqual([asset.uri]);
    // The re-encode is this pick's own copy: it goes once nothing needs it.
    discardLocalCopy(picked.localUri);
    expect(mockDeleted).toEqual([asset.uri, picked.localUri]);
  });

  it("uploads the re-encode of a small geotagged photo, never the picked file with its GPS", async () => {
    const uri = "file:///cache/ImagePicker/geotagged.jpg";
    expect(jpegHasGps(GEOTAGGED_JPEG)).toBe(true);
    mockBytes[uri] = GEOTAGGED_JPEG;
    // What the manipulator writes: the pixels' JPEG, no APP1 segment.
    const reencoded = new Uint8Array([0xff, 0xd8, 0xff, 0xdb, 0x00, 0x02, 0xff, 0xd9]);
    mockBytes["file:///cache/ImageManipulator/out-1.jpg"] = reencoded;
    mockRead.mockImplementation(async (read: string) => (mockBytes[read] ?? new Uint8Array(3)).slice().buffer);
    mockDecoded = { width: 16, height: 8 };

    const picked = await library({ uri, mimeType: "image/jpeg", width: 16, height: 8, name: "geotagged.jpg" });
    await uploadChatAttachment("token", picked as NonNullable<Awaited<ReturnType<typeof pickFromPhotoLibrary>>>);

    const sent = new Uint8Array(jest.mocked(requestRaw).mock.calls[0]![2]!.body as ArrayBuffer);
    expect(sent).toEqual(reencoded);
    expect(jpegHasGps(sent)).toBe(false);
    expect(api.presignAttachment).toHaveBeenCalledWith("token", {
      content_type: "image/jpeg", size_bytes: reencoded.length, filename: "geotagged.jpg",
    });
  });

  it("sends a PNG too large as a PNG as a JPEG, and removes the PNG", async () => {
    mockDecoded = { width: 2048, height: 2048 };
    mockSizes["file:///cache/ImageManipulator/out-1.png"] = MAX_ATTACHMENT_BYTES + 1;
    const picked = await library({
      uri: "file:///cache/ImagePicker/big.png", mimeType: "image/png", width: 2048, height: 2048, name: "big.png",
    });
    expect(picked).toMatchObject({
      localUri: "file:///cache/ImageManipulator/out-2.jpg", contentType: "image/jpeg", fileName: "big.jpg",
    });
    expect(mockSave.mock.calls.map(([options]) => options)).toEqual([
      { format: "png", compress: IMAGE_JPEG_QUALITY }, { format: "jpeg", compress: IMAGE_JPEG_QUALITY },
    ]);
    expect(mockDeleted.sort()).toEqual(["file:///cache/ImageManipulator/out-1.png", "file:///cache/ImagePicker/big.png"]);
  });
});

describe("a GIF keeps its frames and loses its metadata", () => {
  const { header, loop, frame, xmp, comment, trailer } = gifParts;
  const pickGif = (uri: string, bytes: Uint8Array) => {
    mockBytes[uri] = bytes;
    jest.mocked(DocumentPicker.getDocumentAsync).mockResolvedValue({
      canceled: false, assets: [{ uri, name: "wave.gif", mimeType: "image/gif", lastModified: 0 }],
    });
    return pickDocument();
  };

  it("drops its XMP and comments in its own copy, and uploads that copy", async () => {
    const uri = "file:///cache/DocumentPicker/wave.gif";
    const tagged = gifBytes(header(480, 270), loop, xmp(GPS_XMP), comment("home"), frame(8), frame(8), trailer);
    mockRead.mockImplementation(async (read: string) => (mockBytes[read] ?? new Uint8Array(3)).slice().buffer);

    const picked = await pickGif(uri, tagged);
    expect(picked).toEqual({ localUri: uri, contentType: "image/gif", fileName: "wave.gif", kind: "image" });
    expect(ImageManipulator.manipulate).not.toHaveBeenCalled();
    const clean = gifBytes(header(480, 270), loop, frame(8), frame(8), trailer);
    expect(mockBytes[uri]).toEqual(clean);

    await uploadChatAttachment("token", picked!);
    const sent = new Uint8Array(jest.mocked(requestRaw).mock.calls[0]![2]!.body as ArrayBuffer);
    expect(sent).toEqual(clean);
    expect(containsText(sent, "GPS")).toBe(false);
  });

  it("re-encodes a GIF too large to send as it is to a still JPEG", async () => {
    mockDecoded = { width: 3000, height: 200 };
    const picked = await pickGif("file:///cache/DocumentPicker/wide.gif", gifBytes(header(3000, 200), frame(0), trailer));
    expect(picked).toMatchObject({ contentType: "image/jpeg", fileName: "wave.jpg" });
    expect(mockResize).toHaveBeenCalledWith({ width: 2048 });
  });

  it("never rewrites a GIF that is not this pick's own copy", async () => {
    const uri = "file:///documents/wave.gif";
    const tagged = gifBytes(header(10, 10), comment("home"), frame(0), trailer);
    const picked = await pickGif(uri, tagged);
    expect(mockBytes[uri]).toBe(tagged);
    expect(picked).toMatchObject({ contentType: "image/jpeg", localUri: "file:///cache/ImageManipulator/out-1.jpg" });
  });
});

describe("the size cap is checked when a file is picked", () => {
  const document = (uri: string, mimeType: string) =>
    jest.mocked(DocumentPicker.getDocumentAsync).mockResolvedValue({
      canceled: false, assets: [{ uri, name: uri.split("/").pop()!, mimeType, lastModified: 0 }],
    });

  it("refuses an oversized PDF before Send and removes the picker's copy", async () => {
    const uri = "file:///cache/DocumentPicker/big.pdf";
    mockSizes[uri] = MAX_ATTACHMENT_BYTES + 1;
    document(uri, "application/pdf");
    await expect(pickDocument()).rejects.toMatchObject({ reason: "too_large" });
    expect(mockDeleted).toEqual([uri]);
  });

  it("accepts a file exactly at the cap", async () => {
    const uri = "file:///cache/DocumentPicker/edge.pdf";
    mockSizes[uri] = MAX_ATTACHMENT_BYTES;
    document(uri, "application/pdf");
    await expect(pickDocument()).resolves.toMatchObject({ localUri: uri, kind: "file" });
  });

  it("refuses a photo still over the cap after re-encoding, and removes both copies", async () => {
    const uri = "file:///cache/ImagePicker/huge.jpg";
    mockSizes[uri] = 30 * MiB;
    mockSizes["file:///cache/ImageManipulator/out-1.jpg"] = MAX_ATTACHMENT_BYTES + 1;
    mockDecoded = { width: 2048, height: 2048 };
    jest.mocked(ImagePicker.launchCameraAsync).mockResolvedValue({
      canceled: false, assets: [{ uri, mimeType: "image/jpeg", fileName: "huge.jpg", width: 2048, height: 2048 }],
    } as ImagePicker.ImagePickerResult);
    await expect(pickFromCamera()).rejects.toMatchObject({ reason: "too_large" });
    expect(mockDeleted.sort()).toEqual(["file:///cache/ImageManipulator/out-1.jpg", uri]);
  });

  it.each([
    ["image/png", "unreadable"],
    ["image/svg+xml", "unsupported_type"],
  ])("names a %s that will not decode as %s", async (mimeType, reason) => {
    jest.mocked(ImageManipulator.manipulate).mockImplementationOnce(() => ({
      renderAsync: async () => { throw new Error("decode failed"); }, release: jest.fn(),
    }) as never);
    document("file:///cache/DocumentPicker/bad", mimeType);
    await expect(pickDocument()).rejects.toMatchObject({ reason });
  });

  it("refuses an oversized restored draft at upload, before presign", async () => {
    mockSizes[pending.localUri] = MAX_ATTACHMENT_BYTES + 1;
    await expect(uploadChatAttachment("token", pending)).rejects.toMatchObject({ reason: "too_large" });
    expect(api.presignAttachment).not.toHaveBeenCalled();
  });
});

describe("upload failures carry a reason, not English", () => {
  it.each([
    [400, { detail: { code: "unsupported_type", message: "Unsupported content type" } }, "unsupported_type"],
    [400, { detail: { code: "invalid_size", message: "Invalid file size" } }, "too_large"],
    [429, { detail: { code: "daily_limit", message: "Daily image upload limit reached." } }, "daily_limit"],
  ])("maps a presign %s %p to %s", async (status, body, reason) => {
    jest.mocked(api.presignAttachment).mockRejectedValueOnce(new ApiRequestError(status, JSON.stringify(body)));
    await expect(uploadChatAttachment("token", pending)).rejects.toMatchObject({ reason });
    expect(api.cancelAttachment).not.toHaveBeenCalled();
  });

  it("names a refused storage upload and cancels its row", async () => {
    jest.mocked(requestRaw).mockResolvedValueOnce({ ok: false } as Response);
    await expect(uploadChatAttachment("token", pending)).rejects.toMatchObject({ reason: "upload_failed" });
    expect(api.cancelAttachment).toHaveBeenCalledWith("token", "a1");
  });
});

describe("discardDraftAttachment", () => {
  const picked = async () => {
    jest.mocked(DocumentPicker.getDocumentAsync).mockResolvedValue({
      canceled: false, assets: [{ uri: "file:///cache/DocumentPicker/notes.pdf", name: "notes.pdf", mimeType: "application/pdf", lastModified: 0 }],
    });
    return (await pickDocument())!;
  };

  it("removes the picker's copy and cancels the draft's own unlinked upload", async () => {
    const draft = { ...(await picked()), existingAttachmentId: "up-1", uploadedForDraft: true };
    jest.mocked(api.cancelAttachment).mockRejectedValueOnce(new Error("offline"));
    discardDraftAttachment("token", draft);
    expect(mockDeleted).toEqual(["file:///cache/DocumentPicker/notes.pdf"]);
    expect(api.cancelAttachment).toHaveBeenCalledWith("token", "up-1");
  });

  it.each([
    ["a Library pick's row", { existingAttachmentId: "lib-1" }, "token"],
    ["anything without the session's token", { existingAttachmentId: "up-1", uploadedForDraft: true }, null],
  ])("never cancels %s", async (_name, fields, token) => {
    discardDraftAttachment(token, { ...(await picked()), ...fields });
    expect(api.cancelAttachment).not.toHaveBeenCalled();
  });

  it.each([
    ["a Library download in the cache", "file:///cache/attachments/lib-1.pdf"],
    ["a file outside the cache directory", "file:///documents/notes.pdf"],
  ])("never deletes %s", (_name, localUri) => {
    discardDraftAttachment("token", { ...pending, localUri, existingAttachmentId: "lib-1" });
    expect(mockDeleted).toEqual([]);
  });

  it("deletes a copy once, however many drafts held it", async () => {
    const draft = await picked();
    discardDraftAttachment(null, draft);
    discardDraftAttachment(null, { ...draft });
    expect(mockDeleted).toEqual(["file:///cache/DocumentPicker/notes.pdf"]);
  });
});
