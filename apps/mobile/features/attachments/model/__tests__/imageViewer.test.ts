import {
  isNearViewerEnd,
  resolveViewerIndex,
  viewerImageKey,
} from "@/features/attachments/model/imageViewer";
import {
  ZOOM_DOUBLE_TAP,
  ZOOM_MAX,
  clampPan,
  doubleTapZoom,
  focalOffset,
  isZoomed,
  maxPan,
  pinchScale,
} from "@/features/attachments/model/imageZoom";

const photos = (...ids: string[]) => ids.map((attachmentId) => ({ attachmentId }));

describe("viewer paging by photo", () => {
  it("identifies a photo by attachment, then path, then local file", () => {
    expect(viewerImageKey({ attachmentId: "a", path: "/p" })).toBe("a");
    expect(viewerImageKey({ path: "/p", localUri: "file://x" })).toBe("/p");
    expect(viewerImageKey({ localUri: "file://x" })).toBe("file://x");
    expect(viewerImageKey(undefined)).toBeNull();
  });

  it("finds the photo it showed after photos before it come or go", () => {
    expect(resolveViewerIndex(photos("a", "b", "c"), "c", 2)).toBe(2);
    expect(resolveViewerIndex(photos("b", "c"), "c", 2)).toBe(1);
    expect(resolveViewerIndex(photos("x", "a", "b", "c"), "a", 0)).toBe(1);
  });

  it("shows the next photo after the one on screen is deleted, or the one before when it was last", () => {
    // b (index 1) deleted from a, b, c: c slides into its place.
    expect(resolveViewerIndex(photos("a", "c"), "b", 1)).toBe(1);
    // c (index 2) deleted: b, the one before, shows.
    expect(resolveViewerIndex(photos("a", "b"), "c", 2)).toBe(1);
    expect(resolveViewerIndex([], "a", 0)).toBe(0);
  });

  it("asks for more within two pages of the last photo", () => {
    expect(isNearViewerEnd(0, 30)).toBe(false);
    expect(isNearViewerEnd(26, 30)).toBe(false);
    expect(isNearViewerEnd(27, 30)).toBe(true);
    expect(isNearViewerEnd(29, 30)).toBe(true);
    expect(isNearViewerEnd(0, 1)).toBe(true);
    expect(isNearViewerEnd(0, 0)).toBe(false);
  });
});

describe("photo zoom", () => {
  const content = { width: 400, height: 300 };
  const stage = { width: 400, height: 800 };

  it("counts as zoomed only past 1x", () => {
    expect(isZoomed(1)).toBe(false);
    expect(isZoomed(1.005)).toBe(false);
    expect(isZoomed(1.2)).toBe(true);
  });

  it("pinches up to the max with a little give under 1x", () => {
    expect(pinchScale(1, 10)).toBe(ZOOM_MAX);
    expect(pinchScale(2, 0.1)).toBeGreaterThan(0.8);
    expect(pinchScale(2, 0.1)).toBeLessThan(1);
    expect(pinchScale(1.5, 2)).toBe(3);
  });

  it("pans only as far as the zoomed photo still covers the stage", () => {
    // 400 wide at 2x is 800: 200 either way; 300 tall at 2x still fits in 800.
    expect(maxPan(400, 400, 2)).toBe(200);
    expect(maxPan(300, 800, 2)).toBe(0);
    expect(clampPan(500, 400, 400, 2)).toBe(200);
    expect(clampPan(-500, 400, 400, 2)).toBe(-200);
    expect(clampPan(50, 300, 800, 2)).toBe(0);
  });

  it("keeps the point under the fingers in place while pinching", () => {
    // From 1x at the centre, pinching to 2x around x=100 moves the photo left by 100.
    expect(focalOffset(0, 100, 100, 1, 2)).toBe(-100);
    // Moving both fingers by 30 pans by 30.
    expect(focalOffset(0, 100, 130, 1, 2)).toBe(-70);
    // A point stays put when the scale does not change.
    expect(focalOffset(40, 100, 100, 2, 2)).toBe(40);
  });

  it("double tap zooms toward the tapped point, then back to 1x", () => {
    const zoomedIn = doubleTapZoom(1, 100, 0, content, stage);
    expect(zoomedIn.scale).toBe(ZOOM_DOUBLE_TAP);
    expect(zoomedIn.x).toBe(clampPan(100 - 100 * ZOOM_DOUBLE_TAP, 400, 400, ZOOM_DOUBLE_TAP));
    expect(zoomedIn.x).toBeLessThan(0);
    expect(zoomedIn.y).toBe(0);
    expect(doubleTapZoom(zoomedIn.scale, 0, 0, content, stage)).toEqual({ scale: 1, x: 0, y: 0 });
  });
});
