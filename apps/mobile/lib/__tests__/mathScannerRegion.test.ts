import {
  HANDLE_HIT_MAX,
  HANDLE_HIT_MIN,
  MAX_REGION_RATIO,
  MIN_REGION_RATIO,
  clampCameraZoom,
  clampScanRegion,
  defaultScanRegion,
  handleHitSize,
  regionToImageCrop,
  regionsClose,
  resizeScanRegionFromCorner,
  scaleScanRegion,
  scanChromeInset,
  translateScanRegion,
  viewRegionToImageRegion,
  zoomFromPinch,
} from "@/lib/math/scannerRegion";

describe("defaultScanRegion", () => {
  it("is centered and within bounds", () => {
    const region = defaultScanRegion();
    expect(region.x + region.width / 2).toBeCloseTo(0.5, 5);
    expect(region.y + region.height / 2).toBeCloseTo(0.5, 5);
    expect(region.width).toBeGreaterThanOrEqual(MIN_REGION_RATIO);
    expect(region.height).toBeGreaterThanOrEqual(MIN_REGION_RATIO);
  });
});

describe("clampScanRegion", () => {
  it("clamps size to [MIN_REGION_RATIO, MAX_REGION_RATIO]", () => {
    const tooSmall = clampScanRegion({ x: 0.5, y: 0.5, width: 0.01, height: 0.01 });
    expect(tooSmall.width).toBe(MIN_REGION_RATIO);
    expect(tooSmall.height).toBe(MIN_REGION_RATIO);

    const tooBig = clampScanRegion({ x: 0, y: 0, width: 5, height: 5 });
    expect(tooBig.width).toBe(MAX_REGION_RATIO);
    expect(tooBig.height).toBe(MAX_REGION_RATIO);
  });

  it("keeps the region fully on-screen (0..1) by clamping position", () => {
    const offLeft = clampScanRegion({ x: -0.5, y: -0.5, width: 0.4, height: 0.3 });
    expect(offLeft.x).toBe(0);
    expect(offLeft.y).toBe(0);

    const offRight = clampScanRegion({ x: 0.9, y: 0.9, width: 0.4, height: 0.3 });
    expect(offRight.x).toBe(0.6); // 1 - width
    expect(offRight.y).toBe(0.7); // 1 - height
  });

  it("stays out from under chrome insets", () => {
    const inset = { top: 0.12, right: 0, bottom: 0.22, left: 0 };
    const clamped = clampScanRegion({ x: 0, y: 0, width: 0.5, height: 0.4 }, inset);
    expect(clamped.y).toBeGreaterThanOrEqual(0.12);
    expect(clamped.y + clamped.height).toBeLessThanOrEqual(0.78 + 1e-9);
  });
});

describe("scaleScanRegion", () => {
  it("resizes around the region's own center", () => {
    const base = { x: 0.3, y: 0.4, width: 0.4, height: 0.2 };
    const scaled = scaleScanRegion(base, 2);
    const baseCx = base.x + base.width / 2;
    const baseCy = base.y + base.height / 2;
    expect(scaled.width).toBeCloseTo(0.8, 5);
    expect(scaled.height).toBeCloseTo(0.4, 5);
    expect(scaled.x + scaled.width / 2).toBeCloseTo(baseCx, 5);
    expect(scaled.y + scaled.height / 2).toBeCloseTo(baseCy, 5);
  });

  it("re-clamps after scaling so it never grows off-screen", () => {
    const base = { x: 0.4, y: 0.4, width: 0.3, height: 0.3 };
    const scaled = scaleScanRegion(base, 10);
    expect(scaled.width).toBeLessThanOrEqual(MAX_REGION_RATIO);
    expect(scaled.x).toBeGreaterThanOrEqual(0);
    expect(scaled.x + scaled.width).toBeLessThanOrEqual(1);
  });
});

describe("translateScanRegion", () => {
  it("moves the region by a ratio delta", () => {
    const base = { x: 0.3, y: 0.3, width: 0.2, height: 0.2 };
    const moved = translateScanRegion(base, 0.1, -0.05);
    expect(moved.x).toBeCloseTo(0.4, 5);
    expect(moved.y).toBeCloseTo(0.25, 5);
    expect(moved.width).toBe(base.width);
    expect(moved.height).toBe(base.height);
  });

  it("stops at the screen edge instead of moving off-screen", () => {
    const base = { x: 0.05, y: 0.05, width: 0.3, height: 0.3 };
    const moved = translateScanRegion(base, -0.5, -0.5);
    expect(moved.x).toBe(0);
    expect(moved.y).toBe(0);
  });
});

describe("resizeScanRegionFromCorner", () => {
  it("grows the bottom-right corner while keeping the opposite corner", () => {
    const base = { x: 0.2, y: 0.2, width: 0.4, height: 0.3 };
    const resized = resizeScanRegionFromCorner(base, "br", 0.1, 0.05);
    expect(resized.x).toBeCloseTo(0.2, 5);
    expect(resized.y).toBeCloseTo(0.2, 5);
    expect(resized.width).toBeCloseTo(0.5, 5);
    expect(resized.height).toBeCloseTo(0.35, 5);
  });

  it("shrinks from the top-left without inverting the rectangle", () => {
    const base = { x: 0.3, y: 0.3, width: 0.4, height: 0.4 };
    const resized = resizeScanRegionFromCorner(base, "tl", 0.2, 0.2);
    expect(resized.width).toBeGreaterThanOrEqual(MIN_REGION_RATIO);
    expect(resized.height).toBeGreaterThanOrEqual(MIN_REGION_RATIO);
    expect(resized.x + resized.width).toBeCloseTo(0.7, 5);
    expect(resized.y + resized.height).toBeCloseTo(0.7, 5);
  });

  it("stays fully on-screen when a corner is dragged off the edge", () => {
    const base = { x: 0.1, y: 0.1, width: 0.4, height: 0.4 };
    const resized = resizeScanRegionFromCorner(base, "tl", -0.5, -0.5);
    expect(resized.x).toBe(0);
    expect(resized.y).toBe(0);
    expect(resized.x + resized.width).toBeLessThanOrEqual(1);
    expect(resized.y + resized.height).toBeLessThanOrEqual(1);
  });
});

describe("regionsClose", () => {
  it("is true for the same region and false after a move", () => {
    expect(regionsClose(defaultScanRegion(), defaultScanRegion())).toBe(true);
    expect(regionsClose(translateScanRegion(defaultScanRegion(), 0.1, 0), defaultScanRegion())).toBe(false);
  });
});

describe("clampCameraZoom / zoomFromPinch", () => {
  it("clamps zoom to 0..1", () => {
    expect(clampCameraZoom(-0.2)).toBe(0);
    expect(clampCameraZoom(1.4)).toBe(1);
    expect(clampCameraZoom(0.25)).toBe(0.25);
    expect(clampCameraZoom(Number.NaN)).toBe(0);
  });

  it("maps pinch scale onto zoom without jumping to 1 on a small pinch", () => {
    expect(zoomFromPinch(0, 1)).toBe(0);
    expect(zoomFromPinch(0, 1.4)).toBeCloseTo(0.2, 5);
    expect(zoomFromPinch(0.8, 0.2)).toBe(0.4);
    expect(zoomFromPinch(0.9, 3)).toBe(1);
  });
});

describe("handleHitSize / scanChromeInset", () => {
  it("shrinks handle hits so a min-size rect stays pannable", () => {
    expect(handleHitSize(200, 200)).toBe(HANDLE_HIT_MAX);
    expect(handleHitSize(40, 40)).toBe(HANDLE_HIT_MIN);
    expect(handleHitSize(47, 47)).toBeLessThan(HANDLE_HIT_MAX);
  });

  it("converts safe-area chrome into ratio insets", () => {
    const inset = scanChromeInset(390, 844, { top: 47, bottom: 34 });
    expect(inset.top).toBeGreaterThan(0);
    expect(inset.bottom).toBeGreaterThan(0);
    expect(inset.top + inset.bottom).toBeLessThan(0.8);
  });
});

describe("regionToImageCrop", () => {
  it("maps a ratio region to pixel coordinates on the actual photo", () => {
    const crop = regionToImageCrop({ x: 0.25, y: 0.1, width: 0.5, height: 0.3 }, 1000, 2000);
    expect(crop).toEqual({ originX: 250, originY: 200, width: 500, height: 600 });
  });

  it("BUG FIX regression: cover-scale crop accounts for letterboxing when aspects differ", () => {
    // Wide photo in a tall window: cover scales by height, crops the
    // horizontal overflow. A centered full-width overlay is not the
    // full image width.
    const crop = regionToImageCrop(
      { x: 0, y: 0.4, width: 1, height: 0.2 },
      2000,
      1000,
      400,
      800,
    );
    const naive = regionToImageCrop({ x: 0, y: 0.4, width: 1, height: 0.2 }, 2000, 1000);
    expect(crop.originX).toBeGreaterThan(0);
    expect(crop.originX).not.toBe(naive.originX);
    expect(crop.width).toBeLessThan(naive.width);
    expect(crop.originX + crop.width).toBeLessThanOrEqual(2000);
  });

  it("never produces a crop that overflows the image bounds", () => {
    // A region ratio right at the edge should still round-trip to a crop
    // that fits inside the actual photo dimensions.
    const crop = regionToImageCrop({ x: 0.9, y: 0.9, width: 0.3, height: 0.3 }, 1000, 1000);
    expect(crop.originX + crop.width).toBeLessThanOrEqual(1000);
    expect(crop.originY + crop.height).toBeLessThanOrEqual(1000);
  });

  it("always produces at least a 1px crop even for a degenerate region", () => {
    const crop = regionToImageCrop({ x: 1, y: 1, width: 0.001, height: 0.001 }, 100, 100);
    expect(crop.width).toBeGreaterThanOrEqual(1);
    expect(crop.height).toBeGreaterThanOrEqual(1);
  });
});

describe("viewRegionToImageRegion", () => {
  it.each([
    // [region, image w/h, view w/h, expected]
    [{ x: 0.25, y: 0.1, width: 0.5, height: 0.3 }, 1000, 2000, 1000, 2000, { x: 0.25, y: 0.1, width: 0.5, height: 0.3 }],
    // 9:16 frame under a taller 390x844 view: cover crops the sides.
    [{ x: 0, y: 0.4, width: 1, height: 0.2 }, 360, 640, 390, 844, { x: 0.0893, y: 0.4, width: 0.8215, height: 0.2 }],
    // 4:3 photo under a 390x844 view: a full-width band is a middle strip of the photo.
    [{ x: 0, y: 0, width: 1, height: 1 }, 3000, 4000, 390, 844, { x: 0.1919, y: 0, width: 0.6161, height: 1 }],
  ])("maps %j through a cover-fitted image", (region, iw, ih, vw, vh, expected) => {
    const mapped = viewRegionToImageRegion(region, iw, ih, vw, vh);
    expect(mapped.x).toBeCloseTo(expected.x, 3);
    expect(mapped.y).toBeCloseTo(expected.y, 3);
    expect(mapped.width).toBeCloseTo(expected.width, 3);
    expect(mapped.height).toBeCloseTo(expected.height, 3);
  });

  it("is the region the capture crop cuts, in pixels", () => {
    const region = { x: 0.09, y: 0.35, width: 0.82, height: 0.3 };
    const mapped = viewRegionToImageRegion(region, 3024, 4032, 390, 844);
    const crop = regionToImageCrop(region, 3024, 4032, 390, 844);
    expect(crop.originX).toBe(Math.round(mapped.x * 3024));
    expect(crop.originY).toBe(Math.round(mapped.y * 4032));
    expect(crop.width).toBe(Math.round(mapped.width * 3024));
  });

  it("stays inside the image", () => {
    const mapped = viewRegionToImageRegion({ x: 0.9, y: 0.9, width: 0.3, height: 0.3 }, 100, 100);
    expect(mapped.x + mapped.width).toBeLessThanOrEqual(1);
    expect(mapped.y + mapped.height).toBeLessThanOrEqual(1);
  });
});
