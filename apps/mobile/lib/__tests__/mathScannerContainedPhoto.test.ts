import {
  clampScanRegion,
  containedPhotoRegion,
  defaultScanRegion,
  regionToContainedImageCrop,
  regionToImageCrop,
  scanChromeInset,
} from "@/lib/math/scannerRegion";

const inset = scanChromeInset(390, 844, { top: 47, bottom: 34 });

describe("imported scanner photo coordinates", () => {
  it.each([[1200, 700], [700, 1200], [1200, 100], [100, 1200]])(
    "keeps the complete %s×%s photo inside the viewport and default crop",
    (width, height) => {
      const frame = containedPhotoRegion(width, height, 390, 844, inset);
      expect(frame.x).toBeGreaterThanOrEqual(inset.left);
      expect(frame.y).toBeGreaterThanOrEqual(inset.top);
      expect(frame.x + frame.width).toBeLessThanOrEqual(1 - inset.right);
      expect(frame.y + frame.height).toBeLessThanOrEqual(1 - inset.bottom);
      expect(frame.width * 390 / (frame.height * 844)).toBeCloseTo(width / height, 10);
      expect(regionToContainedImageCrop(clampScanRegion(frame, inset), frame, width, height)).toEqual({
        originX: 0, originY: 0, width, height,
      });
    },
  );

  it("maps a selected visible subrectangle to the same source-image pixels", () => {
    const frame = containedPhotoRegion(1200, 700, 390, 844, inset);
    const selected = {
      x: frame.x + frame.width / 4, y: frame.y + frame.height / 4,
      width: frame.width / 2, height: frame.height / 2,
    };
    expect(regionToContainedImageCrop(selected, frame, 1200, 700)).toEqual({
      originX: 300, originY: 175, width: 600, height: 350,
    });
  });

  it("excludes blank letterbox space from a partly overlapping crop", () => {
    const frame = containedPhotoRegion(1200, 700, 390, 844, inset);
    expect(regionToContainedImageCrop({
      x: frame.x - 0.1, y: frame.y - 0.1,
      width: frame.width / 2 + 0.1, height: frame.height / 2 + 0.1,
    }, frame, 1200, 700)).toEqual({ originX: 0, originY: 0, width: 600, height: 350 });
  });

  it("rejects a blank-only selection instead of sending unrelated edge pixels", () => {
    const frame = containedPhotoRegion(1200, 700, 390, 844, inset);
    expect(() => regionToContainedImageCrop({ x: 0, y: 0, width: 0.1, height: 0.1 }, frame, 1200, 700))
      .toThrow("Crop does not overlap the photo");
  });

  it("retains the live-camera cover mapping for the same landscape dimensions", () => {
    expect(regionToImageCrop(defaultScanRegion(inset), 1200, 700, 390, 844)).toEqual({
      originX: 467, originY: 245, width: 265, height: 210,
    });
  });
});
