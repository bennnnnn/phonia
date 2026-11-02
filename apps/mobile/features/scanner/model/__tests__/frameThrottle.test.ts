import { LIVE_READ_INTERVAL_MS, shouldReadFrame } from "@/features/scanner/model/frameThrottle";

describe("shouldReadFrame", () => {
  it("reads the first frame, then one per interval", () => {
    expect(shouldReadFrame(0, 1_000, LIVE_READ_INTERVAL_MS)).toBe(true);
    expect(shouldReadFrame(1_000, 1_033, LIVE_READ_INTERVAL_MS)).toBe(false);
    expect(shouldReadFrame(1_000, 1_149, LIVE_READ_INTERVAL_MS)).toBe(false);
    expect(shouldReadFrame(1_000, 1_150, LIVE_READ_INTERVAL_MS)).toBe(true);
  });

  it("at 30 fps reads about one frame in five", () => {
    let lastReadAt = 0;
    let reads = 0;
    for (let frame = 0; frame < 30; frame += 1) {
      const now = 10_000 + Math.round((frame * 1000) / 30);
      if (shouldReadFrame(lastReadAt, now, LIVE_READ_INTERVAL_MS)) {
        lastReadAt = now;
        reads += 1;
      }
    }
    expect(reads).toBeGreaterThanOrEqual(6);
    expect(reads).toBeLessThanOrEqual(7);
  });

  it("reads again when the clock went back, instead of stalling", () => {
    expect(shouldReadFrame(5_000, 4_000, LIVE_READ_INTERVAL_MS)).toBe(true);
  });
});
