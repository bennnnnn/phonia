import { readAsStringAsync } from "expo-file-system/legacy";

import { request } from "@/lib/api/client";
import { readScan } from "@/features/scanner/api";

jest.mock("expo-file-system/legacy", () => ({
  readAsStringAsync: jest.fn(async () => "aGVsbG8="),
}));
jest.mock("@/lib/api/client", () => ({
  request: jest.fn(async () => ({ reading: "2x + 3 = 7", uncertain: false, source: "mathpix" })),
}));
jest.mock("@/lib/auth", () => ({
  getSessionGeneration: jest.fn(() => 1),
  requireTokenSession: jest.fn(),
  SessionChangedError: class extends Error {},
}));

describe("readScan", () => {
  beforeEach(() => jest.clearAllMocks());

  it("posts the crop natively encoded and returns the reading", async () => {
    const reading = await readScan("tok", "math", {
      localUri: "file:///crop.jpg",
      contentType: "image/jpeg",
    });
    expect(readAsStringAsync).toHaveBeenCalledWith("file:///crop.jpg", { encoding: "base64" });
    expect(reading.reading).toBe("2x + 3 = 7");
    const [path, token, init] = jest.mocked(request).mock.calls[0]!;
    expect(path).toBe("/math/scan/read");
    expect(token).toBe("tok");
    expect(JSON.parse(String(init?.body))).toEqual({
      image_base64: "aGVsbG8=",
      content_type: "image/jpeg",
    });
  });

  it.each(["physics", "chemistry"] as const)("reads a %s crop through its own reader", async (subject) => {
    await readScan("tok", subject, { localUri: "file:///crop.jpg", contentType: "image/jpeg" });
    expect(jest.mocked(request).mock.calls[0]![0]).toBe(`/${subject}/scan/read`);
  });

  it("labels an unsupported type as JPEG, the scanner's crop format", async () => {
    await readScan("tok", "math", { localUri: "file:///crop.heic", contentType: "image/heic" });
    const init = jest.mocked(request).mock.calls[0]![2];
    expect(JSON.parse(String(init?.body)).content_type).toBe("image/jpeg");
  });
});
