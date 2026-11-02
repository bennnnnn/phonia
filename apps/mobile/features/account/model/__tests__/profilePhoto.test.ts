import { File } from "expo-file-system";
import { ImageManipulator } from "expo-image-manipulator";

import { pickFromPhotoLibrary, type PendingAttachment } from "@/features/attachments/model/attachments";
import { discardProfilePhoto, pickProfilePhoto } from "@/features/account/model/profilePhoto";

const mockDelete = jest.fn();
const mockImage = { saveAsync: jest.fn(), release: jest.fn() };
const mockContext = {
  crop: jest.fn(),
  resize: jest.fn(),
  renderAsync: jest.fn(),
  release: jest.fn(),
};

jest.mock("expo-file-system", () => ({ File: jest.fn() }));
jest.mock("expo-image-manipulator", () => ({
  ImageManipulator: { manipulate: jest.fn(() => mockContext) },
  SaveFormat: { JPEG: "jpeg" },
}));
jest.mock("@/features/attachments/model/attachments", () => ({ pickFromPhotoLibrary: jest.fn() }));

const selected: PendingAttachment = {
  localUri: "file:///library/original.png",
  contentType: "image/png",
  fileName: "original.png",
  kind: "image",
  imageSize: { width: 1200, height: 800 },
};
const preview: PendingAttachment = {
  localUri: "file:///cache/profile-preview.jpg",
  contentType: "image/jpeg",
  fileName: "profile.jpg",
  kind: "image",
};

beforeEach(() => {
  jest.clearAllMocks();
  jest.mocked(pickFromPhotoLibrary).mockResolvedValue(selected);
  jest.mocked(File).mockImplementation((...uris) => ({
    exists: true,
    size: 1024,
    delete: () => mockDelete(uris[0]),
  }) as unknown as File);
  mockContext.renderAsync.mockResolvedValue(mockImage);
  mockImage.saveAsync.mockResolvedValue({ uri: preview.localUri, width: 512, height: 512 });
});

afterEach(() => {
  discardProfilePhoto(preview);
});

it("prepares a square JPEG preview without changing the original", async () => {
  await expect(pickProfilePhoto()).resolves.toEqual({
    ...preview,
    fileName: expect.stringMatching(/^profile-\d+\.jpg$/),
  });
  expect(pickFromPhotoLibrary).toHaveBeenCalledWith({ squareCrop: true });
  expect(mockContext.crop).toHaveBeenCalledWith({
    originX: 200, originY: 0, width: 800, height: 800,
  });
  expect(mockContext.resize).toHaveBeenCalledWith({ width: 512, height: 512 });
  expect(mockImage.saveAsync).toHaveBeenCalledWith({ format: "jpeg", compress: 0.8 });
  expect(mockImage.release).toHaveBeenCalledTimes(1);
  expect(mockContext.release).toHaveBeenCalledTimes(1);
  expect(mockDelete).not.toHaveBeenCalled();
});

it("keeps a small square photo at its original dimensions, still written again without its metadata", async () => {
  jest.mocked(pickFromPhotoLibrary).mockResolvedValue({
    ...selected, imageSize: { width: 200, height: 200 },
  });
  mockImage.saveAsync.mockResolvedValue({ uri: preview.localUri, width: 200, height: 200 });
  await expect(pickProfilePhoto()).resolves.toMatchObject({ localUri: preview.localUri });
  expect(mockContext.crop).not.toHaveBeenCalled();
  expect(mockContext.resize).not.toHaveBeenCalled();
  expect(mockImage.saveAsync).toHaveBeenCalledWith({ format: "jpeg", compress: 0.8 });
});

it("returns cancellation without preparing or deleting any file", async () => {
  jest.mocked(pickFromPhotoLibrary).mockResolvedValue(null);
  await expect(pickProfilePhoto()).resolves.toBeNull();
  expect(ImageManipulator.manipulate).not.toHaveBeenCalled();
  expect(File).not.toHaveBeenCalled();
});

it("preserves picker permission errors for the editor", async () => {
  const error = Object.assign(new Error("PHOTO_LIBRARY_PERMISSION"), { needsSettings: true });
  jest.mocked(pickFromPhotoLibrary).mockRejectedValue(error);
  await expect(pickProfilePhoto()).rejects.toBe(error);
  expect(ImageManipulator.manipulate).not.toHaveBeenCalled();
});

it.each([0, Number.NaN, 31 * 1024 * 1024])(
  "rejects invalid or oversized source files before decoding: %s bytes",
  async (size) => {
    jest.mocked(File).mockImplementation(() => ({ exists: true, size }) as File);
    await expect(pickProfilePhoto()).rejects.toThrow(/PROFILE_PHOTO_/);
    expect(ImageManipulator.manipulate).not.toHaveBeenCalled();
    expect(mockDelete).not.toHaveBeenCalled();
  },
);

it.each([
  { width: 0, height: 100 },
  { width: 10_000, height: 10_000 },
  { width: 20_000, height: 10 },
])("rejects invalid or huge source dimensions before decoding: %j", async (imageSize) => {
  jest.mocked(pickFromPhotoLibrary).mockResolvedValue({ ...selected, imageSize });
  await expect(pickProfilePhoto()).rejects.toThrow(/PROFILE_PHOTO_/);
  expect(ImageManipulator.manipulate).not.toHaveBeenCalled();
});

it("releases the native context when image preparation fails", async () => {
  mockContext.renderAsync.mockRejectedValue(new Error("Decode failed"));
  await expect(pickProfilePhoto()).rejects.toThrow("Decode failed");
  expect(mockContext.release).toHaveBeenCalledTimes(1);
  expect(mockImage.release).not.toHaveBeenCalled();
  expect(mockDelete).not.toHaveBeenCalled();
});

it("cleans an invalid generated preview while keeping the selected original", async () => {
  mockImage.saveAsync.mockResolvedValue({ uri: preview.localUri, width: 512, height: 400 });
  await expect(pickProfilePhoto()).rejects.toThrow("PROFILE_PHOTO_INVALID");
  expect(mockDelete).toHaveBeenCalledWith(preview.localUri);
  expect(mockDelete).not.toHaveBeenCalledWith(selected.localUri);
});

it("only discards previews it generated, once", async () => {
  const photo = await pickProfilePhoto();
  discardProfilePhoto(selected);
  expect(mockDelete).not.toHaveBeenCalled();
  discardProfilePhoto(photo!);
  discardProfilePhoto(photo!);
  expect(mockDelete).toHaveBeenCalledTimes(1);
  expect(mockDelete).toHaveBeenCalledWith(preview.localUri);
});

it("does not delete the original if an encoder returns the source URI", async () => {
  mockImage.saveAsync.mockResolvedValue({ uri: selected.localUri, width: 512, height: 512 });
  await expect(pickProfilePhoto()).rejects.toThrow("PROFILE_PHOTO_INVALID");
  expect(mockDelete).not.toHaveBeenCalled();
});
