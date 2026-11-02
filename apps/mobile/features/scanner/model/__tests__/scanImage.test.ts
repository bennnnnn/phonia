import { deleteAsync } from "expo-file-system/legacy";
import { ImageManipulator } from "expo-image-manipulator";

import {
  cropScanImage,
  measureScanImage,
  SCAN_JPEG_QUALITY,
  SCAN_MAX_EDGE,
  ScanFiles,
  scanResize,
} from "@/features/scanner/model/scanImage";

const mockSource = { width: 3024, height: 4032, release: jest.fn() };
const mockResult = { saveAsync: jest.fn(), release: jest.fn() };
const mockContext = {
  crop: jest.fn(),
  resize: jest.fn(),
  renderAsync: jest.fn(),
  release: jest.fn(),
};

jest.mock("expo-file-system/legacy", () => ({ deleteAsync: jest.fn(async () => undefined) }));
jest.mock("expo-image-manipulator", () => ({
  ImageManipulator: { manipulate: jest.fn(() => mockContext) },
  SaveFormat: { JPEG: "jpeg" },
}));

beforeEach(() => {
  jest.clearAllMocks();
  mockContext.renderAsync.mockReset().mockResolvedValueOnce(mockSource).mockResolvedValueOnce(mockResult);
  mockResult.saveAsync.mockResolvedValue({ uri: "file:///cache/crop.jpg", width: 2048, height: 870 });
});

describe("scanResize", () => {
  it.each([
    [{ width: 1200, height: 500 }, null],
    [{ width: SCAN_MAX_EDGE, height: 900 }, null],
    [{ width: 2480, height: 1050 }, { width: SCAN_MAX_EDGE }],
    [{ width: 900, height: 3000 }, { height: SCAN_MAX_EDGE }],
  ])("brings %j to %j", (size, expected) => {
    expect(scanResize(size)).toEqual(expected);
  });
});

describe("cropScanImage", () => {
  it("crops in the decoded image's own space, downscales and saves once", async () => {
    const cropFor = jest.fn(() => ({ originX: 10, originY: 1500, width: 2480, height: 1050 }));
    await expect(cropScanImage("file:///capture.jpg", cropFor)).resolves.toEqual({
      uri: "file:///cache/crop.jpg",
      width: 2048,
      height: 870,
    });
    expect(ImageManipulator.manipulate).toHaveBeenCalledWith("file:///capture.jpg");
    expect(cropFor).toHaveBeenCalledWith({ width: 3024, height: 4032 });
    expect(mockContext.crop).toHaveBeenCalledWith({ originX: 10, originY: 1500, width: 2480, height: 1050 });
    expect(mockContext.resize).toHaveBeenCalledWith({ width: SCAN_MAX_EDGE });
    expect(mockResult.saveAsync).toHaveBeenCalledWith({ compress: SCAN_JPEG_QUALITY, format: "jpeg" });
    expect(mockSource.release).toHaveBeenCalled();
    expect(mockResult.release).toHaveBeenCalled();
    expect(mockContext.release).toHaveBeenCalled();
  });

  it("keeps a small crop at its own size, still written again without the capture's metadata", async () => {
    await expect(
      cropScanImage("file:///capture.jpg", () => ({ originX: 0, originY: 0, width: 800, height: 300 })),
    ).resolves.toMatchObject({ uri: "file:///cache/crop.jpg" });
    expect(mockContext.resize).not.toHaveBeenCalled();
    expect(mockResult.saveAsync).toHaveBeenCalledWith({ compress: SCAN_JPEG_QUALITY, format: "jpeg" });
  });

  it("releases the context when the crop fails", async () => {
    await expect(
      cropScanImage("file:///capture.jpg", () => {
        throw new Error("Crop does not overlap the photo");
      }),
    ).rejects.toThrow("Crop does not overlap");
    expect(mockContext.release).toHaveBeenCalled();
    expect(mockSource.release).toHaveBeenCalled();
  });
});

describe("measureScanImage", () => {
  it("reports the manipulator's oriented size", async () => {
    await expect(measureScanImage("file:///photo.jpg")).resolves.toEqual({ width: 3024, height: 4032 });
    expect(mockContext.release).toHaveBeenCalled();
  });
});

describe("ScanFiles", () => {
  it("deletes what it owns, never what it handed to the composer", async () => {
    const files = new ScanFiles();
    files.track("file:///capture.jpg");
    files.track("file:///crop.jpg");
    files.handOff("file:///crop.jpg");
    files.discardAll();
    files.discard("file:///crop.jpg");
    await Promise.resolve();
    expect(deleteAsync).toHaveBeenCalledTimes(1);
    expect(deleteAsync).toHaveBeenCalledWith("file:///capture.jpg", { idempotent: true });
  });

  it("swallows a failed delete", async () => {
    jest.mocked(deleteAsync).mockRejectedValueOnce(new Error("gone"));
    const files = new ScanFiles();
    files.track("file:///capture.jpg");
    expect(() => files.discard("file:///capture.jpg")).not.toThrow();
    await Promise.resolve();
  });
});
