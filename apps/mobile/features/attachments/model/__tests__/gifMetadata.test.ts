import { stripGifMetadata } from "@/features/attachments/model/gifMetadata";

import {
  containsText,
  GEOTAGGED_JPEG,
  gifBytes,
  gifParts,
  GPS_XMP,
} from "@/features/attachments/model/__tests__/fixtures/photoBytes";

const { header, loop, frame, xmp, comment, trailer } = gifParts;
const iccProfile = [0x21, 0xff, 0x0b, ..."ICCRGBG1012".split("").map((c) => c.charCodeAt(0)), 0x02, 0x10, 0x20, 0x00];
const photoshop = [0x21, 0xff, 0x0b, ..."MGK8BIM0000".split("").map((c) => c.charCodeAt(0)), 0x02, 0x38, 0x42, 0x00];

describe("stripGifMetadata", () => {
  it("drops XMP (with its GPS), comments and other application blocks, keeping every frame and the loop", () => {
    const tagged = gifBytes(
      header(320, 200), loop, xmp(GPS_XMP), comment("Taken at 5th Ave"), frame(10), photoshop, frame(20), trailer,
    );
    expect(containsText(tagged, "GPSLatitude")).toBe(true);

    const stripped = stripGifMetadata(tagged);

    expect(stripped).toEqual({
      width: 320, height: 200, bytes: gifBytes(header(320, 200), loop, frame(10), frame(20), trailer),
    });
    expect(containsText(stripped!.bytes, "GPS")).toBe(false);
    expect(containsText(stripped!.bytes, "5th Ave")).toBe(false);
  });

  it("keeps a GIF with nothing to drop byte for byte, colour profile included", () => {
    const clean = gifBytes(header(48, 48), loop, iccProfile, frame(5), frame(5), trailer);
    expect(stripGifMetadata(clean)?.bytes).toEqual(clean);
  });

  it("keeps a GIF87a and a frame with its own colour table", () => {
    const own = [0x2c, 0, 0, 0, 0, 1, 0, 1, 0, 0x80, 0, 0, 0, 255, 255, 255, 0x02, 0x02, 0x44, 0x01, 0x00];
    const gif87 = gifBytes(header(1, 1), own, trailer);
    gif87[4] = "7".charCodeAt(0);
    expect(stripGifMetadata(gif87)?.bytes).toEqual(gif87);
  });

  it("drops anything after the trailer", () => {
    const appended = gifBytes(header(2, 2), frame(0), trailer, comment("lat 40.7"));
    expect(stripGifMetadata(appended)?.bytes).toEqual(gifBytes(header(2, 2), frame(0), trailer));
  });

  it.each([
    ["a JPEG (Android's picker names one image/gif)", GEOTAGGED_JPEG],
    ["a cut-off frame", gifBytes(header(2, 2), frame(0)).subarray(0, 30)],
    ["no trailer", gifBytes(header(2, 2), frame(0))],
    ["a byte no block starts with", gifBytes(header(2, 2), [0x00], frame(0), trailer)],
    ["too short for a header", new Uint8Array([0x47, 0x49, 0x46])],
  ])("is null for %s", (_name, bytes) => {
    expect(stripGifMetadata(bytes)).toBeNull();
  });
});
